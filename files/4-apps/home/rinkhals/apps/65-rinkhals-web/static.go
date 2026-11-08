package main

import (
	"bytes"
	"compress/gzip"
	"crypto/sha1"
	"encoding/hex"
	"io/fs"
	"mime"
	"net/http"
	"path"
	"strconv"
	"strings"
	"sync"
)

// staticHandler serves the embedded web UI.
//
// http.FileServer on an embed.FS sends every file uncompressed and with no
// Last-Modified or ETag (embedded files have no modification time), so the
// browser downloaded the whole UI again on every visit: hundreds of KB of
// JavaScript over the printer's Wi-Fi. This adds:
//   - long-lived caching for SvelteKit's content-hashed _app/immutable files
//   - an ETag (and 304 answers) for everything else
//   - gzip for text files, compressed once and kept in memory
//
// Paths it cannot resolve to a file (directories without index.html, missing
// files) still go to http.FileServer, so redirects and 404s behave as before.
type staticHandler struct {
	files    fs.FS
	fallback http.Handler

	mu    sync.Mutex
	cache map[string]*staticFile
}

type staticFile struct {
	data    []byte
	gzipped []byte // nil when not worth compressing
	etag    string
	ctype   string
}

func newStaticHandler(files fs.FS) *staticHandler {
	return &staticHandler{
		files:    files,
		fallback: http.FileServer(http.FS(files)),
		cache:    map[string]*staticFile{},
	}
}

var compressibleTypes = []string{"text/", "application/javascript", "application/json", "image/svg+xml", "application/manifest+json"}

func (h *staticHandler) resolve(urlPath string) string {
	name := strings.TrimPrefix(path.Clean("/"+urlPath), "/")
	if name == "" {
		return "index.html"
	}
	if info, err := fs.Stat(h.files, name); err == nil && info.IsDir() {
		// Let FileServer add the trailing-slash redirect, as before
		if !strings.HasSuffix(urlPath, "/") {
			return ""
		}
		return path.Join(name, "index.html")
	}
	return name
}

func (h *staticHandler) load(name string) *staticFile {
	h.mu.Lock()
	f, ok := h.cache[name]
	h.mu.Unlock()
	if ok {
		return f
	}

	// Read and compress without holding the lock: the first page load after a
	// start asks for a dozen bundles at once, and compressing them one after
	// another on a single core delayed even the small files. Two requests for
	// the same new file may both compress it; the result is identical.
	data, err := fs.ReadFile(h.files, name)
	if err != nil {
		// Misses are not cached: a client probing random paths must not grow
		// memory on a printer with very little of it
		return nil
	}

	sum := sha1.Sum(data)
	f = &staticFile{
		data:  data,
		etag:  `"` + hex.EncodeToString(sum[:8]) + `"`,
		ctype: mime.TypeByExtension(path.Ext(name)),
	}
	if f.ctype == "" {
		f.ctype = http.DetectContentType(data)
	}
	if len(data) > 1024 && isCompressible(f.ctype) {
		var b bytes.Buffer
		zw, _ := gzip.NewWriterLevel(&b, gzip.BestCompression)
		zw.Write(data)
		zw.Close()
		if b.Len() < len(data) {
			f.gzipped = b.Bytes()
		}
	}

	h.mu.Lock()
	if existing, ok := h.cache[name]; ok {
		f = existing
	} else {
		h.cache[name] = f
	}
	h.mu.Unlock()
	return f
}

func isCompressible(ctype string) bool {
	for _, prefix := range compressibleTypes {
		if strings.HasPrefix(ctype, prefix) {
			return true
		}
	}
	return false
}

func acceptsGzip(r *http.Request) bool {
	for _, part := range strings.Split(r.Header.Get("Accept-Encoding"), ",") {
		token := strings.TrimSpace(strings.SplitN(part, ";", 2)[0])
		if token == "gzip" && !strings.Contains(part, "q=0") {
			return true
		}
	}
	return false
}

func (h *staticHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet && r.Method != http.MethodHead {
		h.fallback.ServeHTTP(w, r)
		return
	}

	name := h.resolve(r.URL.Path)
	var f *staticFile
	if name != "" {
		f = h.load(name)
	}
	if f == nil {
		h.fallback.ServeHTTP(w, r)
		return
	}

	header := w.Header()
	if strings.HasPrefix(name, "_app/immutable/") {
		header.Set("Cache-Control", "public, max-age=31536000, immutable")
	} else {
		header.Set("Cache-Control", "no-cache")
	}
	header.Set("ETag", f.etag)
	header.Set("Content-Type", f.ctype)
	if f.gzipped != nil {
		header.Add("Vary", "Accept-Encoding")
	}

	if match := r.Header.Get("If-None-Match"); match != "" && strings.Contains(match, f.etag) {
		w.WriteHeader(http.StatusNotModified)
		return
	}

	body := f.data
	if f.gzipped != nil && acceptsGzip(r) {
		header.Set("Content-Encoding", "gzip")
		body = f.gzipped
	}
	header.Set("Content-Length", strconv.Itoa(len(body)))
	w.WriteHeader(http.StatusOK)
	if r.Method == http.MethodGet {
		w.Write(body)
	}
}

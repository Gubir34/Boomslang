package main

import (
	"bytes"
	"compress/gzip"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"testing/fstest"
)

func testStaticFS() fstest.MapFS {
	js := strings.Repeat("console.log('boomslang');\n", 200)
	return fstest.MapFS{
		"index.html":                       {Data: []byte("<!doctype html><title>Boomslang</title>" + strings.Repeat(" ", 2000))},
		"apps/index.html":                  {Data: []byte("<!doctype html><title>Apps</title>")},
		"_app/immutable/nodes/0.abc123.js": {Data: []byte(js)},
		"assets/logo.png":                  {Data: []byte("\x89PNG\r\n\x1a\n" + strings.Repeat("x", 4000))},
	}
}

func get(h http.Handler, path string, headers map[string]string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(http.MethodGet, path, nil)
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func TestImmutableAssetsAreCachedForAYearAndGzipped(t *testing.T) {
	h := newStaticHandler(testStaticFS())
	rec := get(h, "/_app/immutable/nodes/0.abc123.js", map[string]string{"Accept-Encoding": "gzip, deflate"})

	if rec.Code != http.StatusOK {
		t.Fatalf("status %d", rec.Code)
	}
	if got := rec.Header().Get("Cache-Control"); got != "public, max-age=31536000, immutable" {
		t.Fatalf("Cache-Control = %q", got)
	}
	if rec.Header().Get("Content-Encoding") != "gzip" {
		t.Fatal("expected a gzipped response")
	}
	if !strings.HasPrefix(rec.Header().Get("Content-Type"), "text/javascript") &&
		!strings.HasPrefix(rec.Header().Get("Content-Type"), "application/javascript") {
		t.Fatalf("Content-Type = %q", rec.Header().Get("Content-Type"))
	}
	zr, err := gzip.NewReader(bytes.NewReader(rec.Body.Bytes()))
	if err != nil {
		t.Fatal(err)
	}
	plain, _ := io.ReadAll(zr)
	if string(plain) != string(testStaticFS()["_app/immutable/nodes/0.abc123.js"].Data) {
		t.Fatal("gzipped body does not match the file")
	}
}

func TestClientsWithoutGzipGetThePlainFile(t *testing.T) {
	h := newStaticHandler(testStaticFS())
	rec := get(h, "/_app/immutable/nodes/0.abc123.js", nil)
	if rec.Header().Get("Content-Encoding") != "" {
		t.Fatal("must not gzip without Accept-Encoding")
	}
	if rec.Body.String() != string(testStaticFS()["_app/immutable/nodes/0.abc123.js"].Data) {
		t.Fatal("plain body does not match the file")
	}
}

func TestPagesRevalidateWithETag(t *testing.T) {
	h := newStaticHandler(testStaticFS())
	first := get(h, "/", nil)
	if first.Code != http.StatusOK || !strings.Contains(first.Body.String(), "Boomslang") {
		t.Fatalf("index: %d %q", first.Code, first.Body.String())
	}
	if first.Header().Get("Cache-Control") != "no-cache" {
		t.Fatalf("Cache-Control = %q", first.Header().Get("Cache-Control"))
	}
	etag := first.Header().Get("ETag")
	if etag == "" {
		t.Fatal("missing ETag")
	}
	second := get(h, "/", map[string]string{"If-None-Match": etag})
	if second.Code != http.StatusNotModified || second.Body.Len() != 0 {
		t.Fatalf("expected 304 with no body, got %d (%d bytes)", second.Code, second.Body.Len())
	}
}

func TestDirectoriesAndMissingFilesBehaveLikeFileServer(t *testing.T) {
	h := newStaticHandler(testStaticFS())

	if rec := get(h, "/apps/", nil); rec.Code != http.StatusOK || !strings.Contains(rec.Body.String(), "Apps") {
		t.Fatalf("/apps/: %d %q", rec.Code, rec.Body.String())
	}
	if rec := get(h, "/apps", nil); rec.Code != http.StatusMovedPermanently {
		t.Fatalf("/apps should redirect like FileServer, got %d", rec.Code)
	}
	if rec := get(h, "/nope.js", nil); rec.Code != http.StatusNotFound {
		t.Fatalf("missing file: %d", rec.Code)
	}
	if rec := get(h, "/../../etc/passwd", nil); rec.Code != http.StatusNotFound {
		t.Fatalf("path traversal: %d", rec.Code)
	}
}

func TestBinaryFilesAreNotGzipped(t *testing.T) {
	h := newStaticHandler(testStaticFS())
	rec := get(h, "/assets/logo.png", map[string]string{"Accept-Encoding": "gzip"})
	if rec.Header().Get("Content-Encoding") != "" || rec.Header().Get("Content-Type") != "image/png" {
		t.Fatalf("png: encoding %q type %q", rec.Header().Get("Content-Encoding"), rec.Header().Get("Content-Type"))
	}
}

func TestMissingFilesAreNotCached(t *testing.T) {
	h := newStaticHandler(testStaticFS())
	for i := 0; i < 50; i++ {
		get(h, "/missing-"+strings.Repeat("x", i)+".js", nil)
	}
	h.mu.Lock()
	n := len(h.cache)
	h.mu.Unlock()
	if n != 0 {
		t.Fatalf("expected no cache entries for missing files, got %d", n)
	}
}

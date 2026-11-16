package main

import (
	"crypto/rand"
	_ "embed"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"os/exec"
	"runtime"
	"strings"
	"sync"
	"time"
)

//go:embed index.html
var indexHTML []byte

// The window: a small web server on this computer that the default browser
// opens. Nothing extra to install, the same file on Windows and Linux.
//
// Because any web page you have open could also talk to a local server, it
// only answers requests that carry a random token (given in the address it
// opens), come with a local Host header, and, when the browser says where
// they come from, come from this page.

type gui struct {
	token    string
	origin   string // http://127.0.0.1:<port>
	releases func() ([]release, error)
	drives   func() ([]drive, error)

	mu       sync.Mutex
	cache    []release
	job      jobState
	lastPing time.Time
}

type jobState struct {
	State   string   `json:"state"` // idle, running, done, failed
	Percent int      `json:"percent"`
	Log     []string `json:"log"`
	Error   string   `json:"error,omitempty"`
	Path    string   `json:"path,omitempty"`
	Eject   string   `json:"eject,omitempty"`
}

type releaseInfo struct {
	Tag     string `json:"tag"`
	Title   string `json:"title"`
	Test    bool   `json:"test"`
	Date    string `json:"date"`
	Size    int64  `json:"size"`
	Default bool   `json:"default"`
}

type driveInfo struct {
	ID       string   `json:"id"`
	Text     string   `json:"text"`
	Blocking []string `json:"blocking"`
	Warnings []string `json:"warnings"`
}

func newGUI() *gui {
	token := make([]byte, 16)
	rand.Read(token)
	return &gui{
		token:    hex.EncodeToString(token),
		releases: func() ([]release, error) { return fetchReleases(releasesAPI) },
		drives:   listDrives,
		job:      jobState{State: "idle"},
	}
}

func (g *gui) handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/", g.page)
	mux.HandleFunc("/api/state", g.guard(g.state))
	mux.HandleFunc("/api/releases", g.guard(g.releaseList))
	mux.HandleFunc("/api/drives", g.guard(g.driveList))
	mux.HandleFunc("/api/install", g.guard(g.install))
	mux.HandleFunc("/api/job", g.guard(g.jobStatus))
	mux.HandleFunc("/api/ping", g.guard(func(w http.ResponseWriter, r *http.Request) {
		g.mu.Lock()
		g.lastPing = time.Now()
		g.mu.Unlock()
		w.WriteHeader(http.StatusNoContent)
	}))
	return mux
}

func (g *gui) localHost(r *http.Request) bool {
	host, _, err := net.SplitHostPort(r.Host)
	return err == nil && (host == "127.0.0.1" || host == "localhost")
}

func (g *gui) page(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" || !g.localHost(r) || r.URL.Query().Get("t") != g.token {
		http.Error(w, "Open the address the Boomslang USB installer printed.", http.StatusForbidden)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'")
	w.Write(indexHTML)
}

func (g *gui) guard(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !g.localHost(r) || r.Header.Get("X-Token") != g.token {
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		if origin := r.Header.Get("Origin"); origin != "" && origin != g.origin {
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		next(w, r)
	}
}

func writeJSON(w http.ResponseWriter, value any) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(value)
}

func fail(w http.ResponseWriter, code int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(map[string]string{"error": message})
}

func (g *gui) allReleases(refresh bool) ([]release, error) {
	g.mu.Lock()
	cached := g.cache
	g.mu.Unlock()
	if cached != nil && !refresh {
		return cached, nil
	}
	releases, err := g.releases()
	if err != nil {
		return nil, err
	}
	g.mu.Lock()
	g.cache = releases
	g.mu.Unlock()
	return releases, nil
}

func (g *gui) state(w http.ResponseWriter, r *http.Request) {
	type model struct{ Code, Name string }
	models := make([]model, len(modelNames))
	for i, m := range modelNames {
		models[i] = model{m.Code, m.Name}
	}
	writeJSON(w, map[string]any{"version": version, "models": models})
}

// releaseList is what can be installed on a model: the newest stable release
// first (preselected), then newer test versions.
func (g *gui) releaseList(w http.ResponseWriter, r *http.Request) {
	model := strings.ToUpper(r.URL.Query().Get("model"))
	if _, ok := modelGroups[model]; !ok {
		fail(w, http.StatusBadRequest, "unknown model")
		return
	}
	releases, err := g.allReleases(r.URL.Query().Get("refresh") == "1")
	if err != nil {
		fail(w, http.StatusBadGateway, err.Error())
		return
	}
	var out []releaseInfo
	seen := map[string]bool{}
	for _, channel := range []string{"release", "release-preview", "beta", "alpha"} {
		rel := pickRelease(releases, model, channel, "")
		if rel == nil || seen[rel.Tag] {
			continue
		}
		seen[rel.Tag] = true
		date := ""
		if len(rel.Published) >= 10 {
			date = rel.Published[:10]
		}
		out = append(out, releaseInfo{Tag: rel.Tag, Title: rel.title(), Test: rel.rank() < channelRank("release"),
			Date: date, Size: rel.usbAsset(model).Size, Default: len(out) == 0})
	}
	writeJSON(w, out)
}

func driveID(d drive) string { return d.Device }

func (g *gui) driveList(w http.ResponseWriter, r *http.Request) {
	drives, err := g.drives()
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	out := []driveInfo{}
	for _, d := range drives {
		blocking, warnings := d.problems(0)
		// The page reads .length: an empty list, never null
		if blocking == nil {
			blocking = []string{}
		}
		if warnings == nil {
			warnings = []string{}
		}
		out = append(out, driveInfo{ID: driveID(d), Text: d.describe(), Blocking: blocking, Warnings: warnings})
	}
	writeJSON(w, out)
}

type installRequest struct {
	Model   string   `json:"model"`
	Tag     string   `json:"tag"`
	Drive   string   `json:"drive"`
	Folders []string `json:"folders"`
}

func (g *gui) install(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		fail(w, http.StatusMethodNotAllowed, "POST only")
		return
	}
	var req installRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096)).Decode(&req); err != nil {
		fail(w, http.StatusBadRequest, "unreadable request")
		return
	}
	model := strings.ToUpper(req.Model)
	if _, ok := modelGroups[model]; !ok {
		fail(w, http.StatusBadRequest, "unknown model")
		return
	}
	releases, err := g.allReleases(false)
	if err != nil {
		fail(w, http.StatusBadGateway, err.Error())
		return
	}
	rel := pickRelease(releases, model, "alpha", req.Tag)
	if rel == nil {
		fail(w, http.StatusBadRequest, fmt.Sprintf("there is no release %q with a package for the %s", req.Tag, model))
		return
	}
	drives, err := g.drives()
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	target := matchDrive(drives, req.Drive)
	if target == nil {
		fail(w, http.StatusBadRequest, "that USB drive is not there any more; refresh the list")
		return
	}
	folders := []string{usbFolder}
	if model == "K2P" && len(req.Folders) > 0 {
		folders = nil
		for _, f := range req.Folders {
			if f != usbFolder && f != usbFolderK2P {
				fail(w, http.StatusBadRequest, "unknown folder")
				return
			}
			folders = append(folders, f)
		}
	}

	g.mu.Lock()
	if g.job.State == "running" {
		g.mu.Unlock()
		fail(w, http.StatusConflict, "an installation is already running")
		return
	}
	g.job = jobState{State: "running", Log: []string{}}
	g.mu.Unlock()

	go g.runJob(rel, rel.usbAsset(model), *target, folders)
	writeJSON(w, map[string]bool{"started": true})
}

func (g *gui) update(change func(*jobState)) {
	g.mu.Lock()
	change(&g.job)
	g.mu.Unlock()
}

func (g *gui) runJob(rel *release, pkg *asset, target drive, folders []string) {
	failWith := func(err error) {
		g.update(func(j *jobState) { j.State, j.Error = "failed", err.Error() })
	}
	logf := func(format string, args ...any) {
		line := fmt.Sprintf(format, args...)
		g.update(func(j *jobState) { j.Log = append(j.Log, line) })
	}
	if target.Root == "" {
		logf("Mounting %s...", target.Device)
		root, err := mountDrive(target)
		if err != nil {
			failWith(err)
			return
		}
		target.Root, target.Free = root, freeSpace(root)
	}
	if blocking, _ := target.problems(pkg.Size); len(blocking) > 0 {
		failWith(fmt.Errorf("%s cannot be used: %s", target.Device, strings.Join(blocking, "; ")))
		return
	}
	logf("Downloading Boomslang %s...", rel.title())
	err := writePackage(pkg, "", "", target, folders, reporter{
		logf: logf,
		progress: func(done, total int64) {
			if total > 0 {
				g.update(func(j *jobState) { j.Percent = int(done * 100 / total) })
			}
		},
	})
	if err != nil {
		failWith(err)
		return
	}
	g.update(func(j *jobState) {
		j.State, j.Percent, j.Eject = "done", 100, ejectHint
		j.Path = target.Root + usbFolder
	})
}

func (g *gui) jobStatus(w http.ResponseWriter, r *http.Request) {
	g.mu.Lock()
	job := g.job
	job.Log = append([]string{}, g.job.Log...)
	g.mu.Unlock()
	writeJSON(w, job)
}

// idleFor reports how long the page has been silent, once it has been open.
// The page pings every few seconds, so closing the tab ends the program.
func (g *gui) idleFor() (time.Duration, bool) {
	g.mu.Lock()
	defer g.mu.Unlock()
	if g.lastPing.IsZero() || g.job.State == "running" {
		return 0, false
	}
	return time.Since(g.lastPing), true
}

func openBrowser(address string) error {
	switch runtime.GOOS {
	case "windows":
		return exec.Command("rundll32", "url.dll,FileProtocolHandler", address).Start()
	case "darwin":
		return exec.Command("open", address).Start()
	default:
		return exec.Command("xdg-open", address).Start()
	}
}

// runGUI serves the page and opens it. It returns when the page is closed.
func runGUI() error {
	g := newGUI()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return fmt.Errorf("could not start the window: %w", err)
	}
	g.origin = "http://" + listener.Addr().String()
	address := g.origin + "/?t=" + url.QueryEscape(g.token)

	server := &http.Server{Handler: g.handler(), ReadHeaderTimeout: 10 * time.Second}
	go server.Serve(listener)

	fmt.Println("Boomslang USB installer is open in your browser.")
	fmt.Println("If it did not open, go to:", address)
	fmt.Println("Close the browser tab, or this window, to quit.")
	if err := openBrowser(address); err != nil {
		fmt.Println("(Could not open the browser by itself:", err.Error()+")")
	}
	started := time.Now()
	for {
		time.Sleep(2 * time.Second)
		if idle, opened := g.idleFor(); opened && idle > 20*time.Second {
			return nil
		} else if !opened && g.lastPingZero() && time.Since(started) > 10*time.Minute {
			return fmt.Errorf("the browser page never opened; use --cli for the console version")
		}
	}
}

func (g *gui) lastPingZero() bool {
	g.mu.Lock()
	defer g.mu.Unlock()
	return g.lastPing.IsZero()
}

package main

import (
	"archive/zip"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func testPackage(t *testing.T) ([]byte, string) {
	t.Helper()
	var buffer bytes.Buffer
	w := zip.NewWriter(&buffer)
	f, _ := w.Create("update_swu/setup.tar.gz")
	f.Write(bytes.Repeat([]byte("boomslang"), 5000))
	w.Close()
	sum := sha256.Sum256(buffer.Bytes())
	return buffer.Bytes(), hex.EncodeToString(sum[:])
}

type guiFixture struct {
	g      *gui
	server *httptest.Server
	stick  string
}

func newFixture(t *testing.T, packageURL, digest string, size int64) *guiFixture {
	t.Helper()
	stick := t.TempDir()
	g := newGUI()
	g.releases = func() ([]release, error) {
		return []release{
			{Tag: "2611-5-alpha", Prerelease: true, Published: "2026-11-16T10:00:00Z",
				Assets: []asset{{Name: "update-ks1.swu", Size: size, URL: packageURL, Digest: digest}}},
			{Tag: "2611-2-release", Published: "2026-11-10T10:00:00Z",
				Assets: []asset{{Name: "update-ks1.swu", Size: size, URL: packageURL, Digest: digest}}},
		}, nil
	}
	g.drives = func() ([]drive, error) {
		return []drive{
			{Device: "E:", Root: stick, Label: "PRINTER", FS: "FAT32", Table: "mbr", Free: 4 << 30, Size: 8 << 30},
			{Device: "F:", Root: t.TempDir(), Label: "BIG", FS: "exFAT", Table: "gpt", Free: 4 << 30, Size: 64 << 30},
		}, nil
	}
	server := httptest.NewServer(g.handler())
	t.Cleanup(server.Close)
	g.origin = server.URL
	return &guiFixture{g: g, server: server, stick: stick}
}

func (f *guiFixture) call(t *testing.T, method, path, body string, headers map[string]string) (int, map[string]any, []any) {
	t.Helper()
	req, _ := http.NewRequest(method, f.server.URL+path, strings.NewReader(body))
	req.Header.Set("X-Token", f.g.token)
	for k, v := range headers {
		if v == "" {
			req.Header.Del(k)
		} else {
			req.Header.Set(k, v)
		}
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var object map[string]any
	var list []any
	var raw bytes.Buffer
	raw.ReadFrom(resp.Body)
	if json.Unmarshal(raw.Bytes(), &object) != nil {
		json.Unmarshal(raw.Bytes(), &list)
	}
	return resp.StatusCode, object, list
}

func TestGUIRefusesRequestsWithoutTheToken(t *testing.T) {
	f := newFixture(t, "http://unused", "", 1)
	for _, path := range []string{"/api/state", "/api/drives", "/api/job", "/api/releases?model=KS1"} {
		if code, _, _ := f.call(t, "GET", path, "", map[string]string{"X-Token": ""}); code != http.StatusForbidden {
			t.Errorf("%s without a token: %d", path, code)
		}
		if code, _, _ := f.call(t, "GET", path, "", map[string]string{"X-Token": "wrong"}); code != http.StatusForbidden {
			t.Errorf("%s with a wrong token: %d", path, code)
		}
	}
	if code, _, _ := f.call(t, "POST", "/api/install", `{}`, map[string]string{"X-Token": ""}); code != http.StatusForbidden {
		t.Errorf("install without a token: %d", code)
	}
	// another web page in the browser (it has the wrong Origin) is turned away even with a token
	if code, _, _ := f.call(t, "GET", "/api/state", "", map[string]string{"Origin": "https://evil.example"}); code != http.StatusForbidden {
		t.Errorf("a foreign origin: %d", code)
	}
	// a rebinding attack arrives with another Host header
	req, _ := http.NewRequest("GET", f.server.URL+"/api/state", nil)
	req.Host = "evil.example"
	req.Header.Set("X-Token", f.g.token)
	if resp, err := http.DefaultClient.Do(req); err != nil || resp.StatusCode != http.StatusForbidden {
		t.Errorf("a foreign Host header: %v %v", resp, err)
	}
	// the page itself needs the token in its address
	resp, _ := http.Get(f.server.URL + "/")
	if resp.StatusCode != http.StatusForbidden {
		t.Errorf("page without token: %d", resp.StatusCode)
	}
	resp, _ = http.Get(f.server.URL + "/?t=" + f.g.token)
	if resp.StatusCode != http.StatusOK || !strings.Contains(resp.Header.Get("Content-Type"), "text/html") {
		t.Errorf("page with token: %d %s", resp.StatusCode, resp.Header.Get("Content-Type"))
	}
	if code, _, _ := f.call(t, "GET", "/api/state", "", nil); code != http.StatusOK {
		t.Errorf("a correct request was refused: %d", code)
	}
}

func TestGUIListsReleasesAndDrives(t *testing.T) {
	f := newFixture(t, "http://unused", "", 71<<20)
	code, _, list := f.call(t, "GET", "/api/releases?model=KS1", "", nil)
	if code != 200 || len(list) != 2 {
		t.Fatalf("releases: %d %v", code, list)
	}
	first, second := list[0].(map[string]any), list[1].(map[string]any)
	if first["tag"] != "2611-2-release" || first["default"] != true || first["test"] != false {
		t.Errorf("the stable release must come first and be preselected: %v", first)
	}
	if second["tag"] != "2611-5-alpha" || second["test"] != true || second["title"] != "2611 5 Alpha" {
		t.Errorf("then the test version, marked as such: %v", second)
	}
	if code, _, _ := f.call(t, "GET", "/api/releases?model=NOPE", "", nil); code != http.StatusBadRequest {
		t.Errorf("unknown model: %d", code)
	}
	_, _, drives := f.call(t, "GET", "/api/drives", "", nil)
	if len(drives) != 2 || len(drives[0].(map[string]any)["blocking"].([]any)) != 0 || len(drives[1].(map[string]any)["blocking"].([]any)) != 2 {
		t.Errorf("a FAT32 MBR drive is usable, exFAT on GPT is refused with two reasons: %v", drives)
	}
}

func waitForJob(t *testing.T, f *guiFixture) map[string]any {
	t.Helper()
	for i := 0; i < 200; i++ {
		_, job, _ := f.call(t, "GET", "/api/job", "", nil)
		if job["state"] != "running" {
			return job
		}
		time.Sleep(25 * time.Millisecond)
	}
	t.Fatal("the job never finished")
	return nil
}

func TestGUIInstallWritesTheVerifiedPackage(t *testing.T) {
	data, sum := testPackage(t)
	source := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.Write(data) }))
	defer source.Close()
	f := newFixture(t, source.URL+"/update-ks1.swu", "sha256:"+sum, int64(len(data)))

	code, _, _ := f.call(t, "POST", "/api/install", `{"model":"ks1","tag":"2611-2-release","drive":"E:"}`, nil)
	if code != 200 {
		t.Fatalf("install: %d", code)
	}
	job := waitForJob(t, f)
	if job["state"] != "done" || job["percent"].(float64) != 100 {
		t.Fatalf("job: %v", job)
	}
	written, err := os.ReadFile(filepath.Join(f.stick, usbFolder, usbFileName))
	if err != nil || !bytes.Equal(written, data) {
		t.Fatalf("the drive does not hold the package: %v", err)
	}
	if !strings.Contains(job["eject"].(string), "drive") {
		t.Errorf("the page must say how to remove the drive: %v", job["eject"])
	}
}

func TestGUIInstallRefusesWhatItShould(t *testing.T) {
	data, sum := testPackage(t)
	source := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.Write(data) }))
	defer source.Close()
	f := newFixture(t, source.URL, "sha256:"+sum, int64(len(data)))

	for name, body := range map[string]string{
		"unknown model":   `{"model":"X1","tag":"2611-2-release","drive":"E:"}`,
		"unknown release": `{"model":"KS1","tag":"2699-1-release","drive":"E:"}`,
		"unknown drive":   `{"model":"KS1","tag":"2611-2-release","drive":"Z:"}`,
		"broken request":  `not json`,
		"unknown folder":  `{"model":"K2P","tag":"2611-2-release","drive":"E:","folders":["../etc"]}`,
	} {
		if code, _, _ := f.call(t, "POST", "/api/install", body, nil); code != http.StatusBadRequest {
			t.Errorf("%s: %d", name, code)
		}
	}
	if code, _, _ := f.call(t, "GET", "/api/install", "", nil); code != http.StatusMethodNotAllowed {
		t.Errorf("GET install: %d", code)
	}
	// a drive the printer can't read is refused when the job starts, and nothing is written
	f.call(t, "POST", "/api/install", `{"model":"KS1","tag":"2611-2-release","drive":"F:"}`, nil)
	job := waitForJob(t, f)
	if job["state"] != "failed" || !strings.Contains(job["error"].(string), "FAT32") {
		t.Errorf("exFAT drive: %v", job)
	}
}

func TestGUIInstallStopsOnAChecksumMismatch(t *testing.T) {
	data, _ := testPackage(t)
	source := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.Write(data) }))
	defer source.Close()
	f := newFixture(t, source.URL, "sha256:"+strings.Repeat("0", 64), int64(len(data)))
	f.call(t, "POST", "/api/install", `{"model":"KS1","tag":"2611-2-release","drive":"E:"}`, nil)
	job := waitForJob(t, f)
	if job["state"] != "failed" || !strings.Contains(job["error"].(string), "checksum") {
		t.Fatalf("job: %v", job)
	}
	if entries, _ := os.ReadDir(f.stick); len(entries) != 0 {
		t.Fatalf("a failed download must leave the drive untouched, found %v", entries)
	}
}

func TestGUIOnlyOneJobAtATime(t *testing.T) {
	data, sum := testPackage(t)
	release := make(chan struct{})
	source := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { <-release; w.Write(data) }))
	defer source.Close()
	f := newFixture(t, source.URL, "sha256:"+sum, int64(len(data)))
	body := `{"model":"KS1","tag":"2611-2-release","drive":"E:"}`
	if code, _, _ := f.call(t, "POST", "/api/install", body, nil); code != 200 {
		t.Fatalf("first install: %d", code)
	}
	if code, _, _ := f.call(t, "POST", "/api/install", body, nil); code != http.StatusConflict {
		t.Errorf("a second install while one runs: %d", code)
	}
	close(release)
	waitForJob(t, f)
}

func TestGUIQuitsWhenThePageIsClosed(t *testing.T) {
	f := newFixture(t, "http://unused", "", 1)
	if _, opened := f.g.idleFor(); opened {
		t.Error("before the page has opened there is nothing to time out")
	}
	f.call(t, "GET", "/api/ping", "", nil)
	if idle, opened := f.g.idleFor(); !opened || idle > time.Second {
		t.Errorf("after a ping: %v %v", idle, opened)
	}
	f.g.mu.Lock()
	f.g.job.State = "running"
	f.g.lastPing = time.Now().Add(-time.Hour)
	f.g.mu.Unlock()
	if _, opened := f.g.idleFor(); opened {
		t.Error("a running install must never be cut short by a closed tab")
	}
}

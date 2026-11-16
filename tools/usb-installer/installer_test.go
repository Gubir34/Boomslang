package main

import (
	"archive/zip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func rel(tag string, prerelease bool, names ...string) release {
	r := release{Tag: tag, Prerelease: prerelease}
	for _, n := range names {
		r.Assets = append(r.Assets, asset{Name: n, URL: "https://example/" + tag + "/" + n, Size: 10})
	}
	return r
}

var all = []string{"update-k2p-k3.swu", "update-k2p-k3-compressed.swu", "update-k3m.swu", "update-ks1.swu",
	"update-ks1-compressed.swu", "update-ks1m.swu", "installer-ks1.swu", "tools-ks1.zip"}

func TestUSBAssetIsAlwaysTheStandardPackage(t *testing.T) {
	r := rel("2611-3-alpha", true, all...)
	cases := map[string]string{"KS1": "update-ks1.swu", "ks1m": "update-ks1m.swu", "K3": "update-k2p-k3.swu",
		"K3V2": "update-k2p-k3.swu", "K2P": "update-k2p-k3.swu", "K3M": "update-k3m.swu"}
	for model, want := range cases {
		if a := r.usbAsset(model); a == nil || a.Name != want {
			t.Errorf("%s: got %v, want %s", model, a, want)
		}
	}
	// only a compressed package: nothing to put on a USB drive
	if a := rel("x", false, "update-ks1-compressed.swu").usbAsset("KS1"); a != nil {
		t.Errorf("a compressed package must never be chosen for USB, got %s", a.Name)
	}
	// the S1 Max falls back to the S1 package on releases without its own
	if a := rel("x", false, "update-ks1.swu").usbAsset("KS1M"); a == nil || a.Name != "update-ks1.swu" {
		t.Errorf("KS1M fallback: got %v", a)
	}
	if a := r.usbAsset("NOPE"); a != nil {
		t.Errorf("unknown model got %s", a.Name)
	}
}

func TestPickRelease(t *testing.T) {
	releases := []release{
		rel("2611-5-alpha", true, all...),
		rel("2611-4-beta", true, all...),
		rel("2611-2-release", false, all...),
		rel("2611-6-release", false, "update-k3m.swu"), // newest, but nothing for a KS1
		rel("20261109_05_test", true, all...),
		rel("20261101_01", false, all...),
		{Tag: "2611-9-release", Draft: true, Assets: []asset{{Name: "update-ks1.swu"}}},
	}
	cases := []struct{ channel, tag, want string }{
		{"release", "", "2611-2-release"},
		{"beta", "", "2611-4-beta"},
		{"alpha", "", "2611-5-alpha"},
		{"release-preview", "", "2611-2-release"},
		{"alpha", "20261101_01", "20261101_01"}, // an exact version, whatever its age
		{"release", "2611-5-ALPHA", "2611-5-alpha"},
		{"release", "2611-9-release", ""}, // a draft is not a release
		{"release", "nope", ""},
	}
	for _, c := range cases {
		got := ""
		if r := pickRelease(releases, "KS1", c.channel, c.tag); r != nil {
			got = r.Tag
		}
		if got != c.want {
			t.Errorf("channel %q tag %q: got %q, want %q", c.channel, c.tag, got, c.want)
		}
	}
	if r := pickRelease(releases, "K3M", "release", ""); r == nil || r.Tag != "2611-6-release" {
		t.Errorf("K3M: got %v", r)
	}
}

func TestReleaseTitlesAndOrder(t *testing.T) {
	if got := rel("2611-3-alpha", true).title(); got != "2611 3 Alpha" {
		t.Errorf("title: %q", got)
	}
	if got := rel("261-12-release-preview", true).title(); got != "261 12 Release Preview" {
		t.Errorf("title: %q", got)
	}
	if got := rel("20261109_05_test", true).title(); got != "20261109_05_test" {
		t.Errorf("title: %q", got)
	}
	newer := [][2]string{{"2611-4-beta", "2611-3-alpha"}, {"2612-1-alpha", "2611-999-release"}, {"271-1-alpha", "2612-9-release"},
		{"2611-1-alpha", "20261231_09"}, {"2611-3-release", "2611-3-alpha"}, {"20261109_02", "20261109_01"}}
	for _, pair := range newer {
		if !tagNewer(pair[0], pair[1]) || tagNewer(pair[1], pair[0]) {
			t.Errorf("%s should be newer than %s", pair[0], pair[1])
		}
	}
}

func writeZip(t *testing.T, path string, names ...string) {
	t.Helper()
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	w := zip.NewWriter(file)
	for _, name := range names {
		f, _ := w.Create(name)
		f.Write([]byte("data for " + name))
	}
	w.Close()
	file.Close()
}

func TestCheckPackage(t *testing.T) {
	dir := t.TempDir()
	standard := filepath.Join(dir, "standard.swu")
	writeZip(t, standard, "update_swu/setup.tar.gz", "update_swu/setup.tar.gz.md5")
	if err := checkPackage(standard); err != nil {
		t.Errorf("standard package refused: %v", err)
	}
	compressed := filepath.Join(dir, "compressed.swu")
	writeZip(t, compressed, "update_swu/setup.tar.xz", "update_swu/setup.tar.xz.md5")
	if err := checkPackage(compressed); err == nil || !strings.Contains(err.Error(), "compressed") {
		t.Errorf("a compressed package must be refused with the reason, got %v", err)
	}
	other := filepath.Join(dir, "other.zip")
	writeZip(t, other, "readme.txt")
	if err := checkPackage(other); err == nil {
		t.Error("a zip without the setup archive must be refused")
	}
	junk := filepath.Join(dir, "junk.swu")
	os.WriteFile(junk, []byte("<html>Not Found</html>"), 0644)
	if err := checkPackage(junk); err == nil {
		t.Error("a file that is not a zip must be refused")
	}
}

func TestDownloadChecksumAndPlacement(t *testing.T) {
	body := []byte(strings.Repeat("boomslang update package ", 20000))
	want := sha256.Sum256(body)
	wantHex := hex.EncodeToString(want[:])
	saved := retryPause
	retryPause = func(int) {}
	defer func() { retryPause = saved }()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/ok":
			w.Write(body)
		case "/short":
			w.Header().Set("Content-Length", "999999")
			w.Write(body[:100])
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()

	dir := t.TempDir()
	path := filepath.Join(dir, "download.swu")
	var last int64
	sum, err := download(server.URL+"/ok", path, int64(len(body)), func(done, total int64) { last = done })
	if err != nil || sum != wantHex || last != int64(len(body)) {
		t.Fatalf("download: sum %s err %v progress %d", sum, err, last)
	}
	if !digestMatches("sha256:"+strings.ToUpper(wantHex), sum) || digestMatches("sha256:"+strings.Repeat("0", 64), sum) || !digestMatches("", sum) {
		t.Fatal("digest comparison is wrong")
	}
	if _, err := download(server.URL+"/missing", filepath.Join(dir, "missing.swu"), 0, nil); err == nil {
		t.Fatal("a 404 must be an error")
	}
	if _, err := download(server.URL+"/short", filepath.Join(dir, "short.swu"), 0, nil); err == nil {
		t.Fatal("a download that stops early must be an error")
	}

	usb := filepath.Join(dir, "usb")
	os.MkdirAll(filepath.Join(usb, usbFolder), 0755)
	os.WriteFile(filepath.Join(usb, usbFolder, usbFileName), []byte("an older package"), 0644)
	target, err := placeOnDrive(path, usb, usbFolder, wantHex)
	if err != nil {
		t.Fatal(err)
	}
	if target != filepath.Join(usb, usbFolder, usbFileName) {
		t.Fatalf("written to %s", target)
	}
	if got, _ := sha256File(target); got != wantHex {
		t.Fatal("the file on the drive is not the download")
	}
	if _, err := os.Stat(target + ".part"); err == nil {
		t.Fatal("the temporary file was left behind")
	}
	// A copy that does not match (a failing stick) leaves the old file alone
	if _, err := placeOnDrive(path, usb, "other", strings.Repeat("0", 64)); err == nil {
		t.Fatal("a mismatch after writing must be an error")
	}
	if entries, _ := os.ReadDir(filepath.Join(usb, "other")); len(entries) != 0 {
		t.Fatalf("a failed write left files behind: %v", entries)
	}
}

func TestDownloadResumesAfterADroppedConnection(t *testing.T) {
	body := []byte(strings.Repeat("0123456789abcdef", 60000)) // 960 KB
	want := sha256.Sum256(body)
	saved := retryPause
	retryPause = func(int) {}
	defer func() { retryPause = saved }()

	for name, honourRange := range map[string]bool{"server continues from the offset": true, "server ignores the range": false} {
		requests, ranges := 0, []string{}
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			requests++
			ranges = append(ranges, r.Header.Get("Range"))
			from := 0
			if honourRange && r.Header.Get("Range") != "" {
				fmt.Sscanf(r.Header.Get("Range"), "bytes=%d-", &from)
				w.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", from, len(body)-1, len(body)))
				w.Header().Set("Content-Length", fmt.Sprint(len(body)-from))
				w.WriteHeader(http.StatusPartialContent)
			} else {
				w.Header().Set("Content-Length", fmt.Sprint(len(body)))
			}
			if requests <= 2 {
				// the first two connections die part of the way through
				w.Write(body[from : from+300000])
				w.(http.Flusher).Flush()
				hijacked, _, _ := w.(http.Hijacker).Hijack()
				hijacked.Close()
				return
			}
			w.Write(body[from:])
		}))
		path := filepath.Join(t.TempDir(), "download.swu")
		sum, err := download(server.URL, path, int64(len(body)), nil)
		server.Close()
		if err != nil {
			t.Fatalf("%s: %v", name, err)
		}
		if sum != hex.EncodeToString(want[:]) {
			t.Fatalf("%s: the file is not what the server holds", name)
		}
		if got, _ := sha256File(path); got != sum {
			t.Fatalf("%s: the file on disk differs from the reported checksum", name)
		}
		if requests != 3 || ranges[0] != "" || ranges[1] == "" {
			t.Fatalf("%s: expected 3 requests, the later ones with a Range, got %d %v", name, requests, ranges)
		}
	}
}

func TestDownloadKeepsGoingWhileItMovesForward(t *testing.T) {
	// Every connection dies after 100 KB, far more often than downloadAttempts
	body := []byte(strings.Repeat("x", 1000000))
	saved := retryPause
	retryPause = func(int) {}
	defer func() { retryPause = saved }()
	requests := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests++
		from := 0
		fmt.Sscanf(r.Header.Get("Range"), "bytes=%d-", &from)
		if from > 0 {
			w.Header().Set("Content-Length", fmt.Sprint(len(body)-from))
			w.WriteHeader(http.StatusPartialContent)
		} else {
			w.Header().Set("Content-Length", fmt.Sprint(len(body)))
		}
		end := from + 100000
		if end > len(body) {
			end = len(body)
		}
		w.Write(body[from:end])
		if end < len(body) {
			w.(http.Flusher).Flush()
			conn, _, _ := w.(http.Hijacker).Hijack()
			conn.Close()
		}
	}))
	defer server.Close()
	if _, err := download(server.URL, filepath.Join(t.TempDir(), "x"), int64(len(body)), nil); err != nil {
		t.Fatalf("a download that moves forward on every try must finish: %v (after %d requests)", err, requests)
	}
	if requests != 10 {
		t.Fatalf("expected 10 requests of 100 KB, got %d", requests)
	}
}

func TestDownloadGivesUpOnWhatRetryingCannotFix(t *testing.T) {
	saved := retryPause
	retryPause = func(int) {}
	defer func() { retryPause = saved }()
	requests := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests++
		http.NotFound(w, r)
	}))
	defer server.Close()
	if _, err := download(server.URL, filepath.Join(t.TempDir(), "x"), 0, nil); err == nil || requests != 1 {
		t.Fatalf("a 404 must fail at once, got %v after %d requests", err, requests)
	}
}

func TestDriveProblems(t *testing.T) {
	const need = 71 << 20
	good := drive{Device: "E:", FS: "FAT32", Table: "mbr", Free: 4 << 30}
	if blocking, warnings := good.problems(need); len(blocking)+len(warnings) != 0 {
		t.Errorf("a good drive has problems: %v %v", blocking, warnings)
	}
	if blocking, _ := (drive{FS: "vfat", Table: "dos", Free: 4 << 30}).problems(need); len(blocking) != 0 {
		t.Errorf("Linux names for FAT32 and MBR must be accepted: %v", blocking)
	}
	for name, d := range map[string]drive{
		"exFAT":      {FS: "exfat", Table: "dos", Free: 4 << 30},
		"NTFS":       {FS: "NTFS", Table: "mbr", Free: 4 << 30},
		"GPT":        {FS: "vfat", Table: "gpt", Free: 4 << 30},
		"full drive": {FS: "vfat", Table: "dos", Free: 10 << 20},
	} {
		if blocking, _ := d.problems(need); len(blocking) != 1 {
			t.Errorf("%s: expected one blocking problem, got %v", name, blocking)
		}
	}
	// What can't be checked is a warning, not a refusal
	if blocking, warnings := (drive{FS: "vfat", Table: "", Free: -1}).problems(need); len(blocking) != 0 || len(warnings) != 1 {
		t.Errorf("unknown partition table: %v %v", blocking, warnings)
	}
}

func TestMatchDrive(t *testing.T) {
	drives := []drive{{Device: "/dev/sdb1", Root: "/run/media/me/USB"}, {Device: "E:", Root: `E:\`}}
	for name, want := range map[string]string{"/dev/sdb1": "/dev/sdb1", "/run/media/me/USB/": "/dev/sdb1", "e": "E:", "E:": "E:", `E:\`: "E:"} {
		if d := matchDrive(drives, name); d == nil || d.Device != want {
			t.Errorf("%q: got %v, want %s", name, d, want)
		}
	}
	if d := matchDrive(drives, "/dev/sda1"); d != nil {
		t.Errorf("an unknown drive matched %v", d)
	}
}

func TestFetchReleases(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/limited" {
			http.Error(w, `{"message":"API rate limit exceeded"}`, http.StatusForbidden)
			return
		}
		json.NewEncoder(w).Encode([]release{rel("2611-3-alpha", true, "update-ks1.swu")})
	}))
	defer server.Close()
	releases, err := fetchReleases(server.URL + "/ok")
	if err != nil || len(releases) != 1 || releases[0].Tag != "2611-3-alpha" {
		t.Fatalf("got %v, %v", releases, err)
	}
	if _, err := fetchReleases(server.URL + "/limited"); err == nil || !strings.Contains(err.Error(), "rate limit") {
		t.Fatalf("the reason GitHub gives must be shown, got %v", err)
	}
}

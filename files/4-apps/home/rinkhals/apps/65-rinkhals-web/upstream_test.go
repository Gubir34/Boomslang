package main

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestFirmwareListed(t *testing.T) {
	notes := "| Kobra S1 | `2.7.0.9` `2.7.2.7` |\n| Kobra 3 | 2.4.6.7 |\nFixed in 2.5.1."
	cases := map[string]bool{
		"2.7.2.7": true, "2.4.6.7": true, "2.5.1": true,
		"2.7.3.7": false,
		"2.7.2":   false, // inside 2.7.2.7
		"7.2.7":   false, // inside 2.7.2.7
		"":        false,
	}
	for fw, want := range cases {
		if got := firmwareListed(notes, fw); got != want {
			t.Errorf("firmwareListed(%q) = %v, want %v", fw, got, want)
		}
	}
	if firmwareListed("", "2.7.2.7") {
		t.Error("empty notes list nothing")
	}
}

func upstreamReleases() []ghReleaseEntry {
	asset := func(name string) ghReleaseAsset {
		return ghReleaseAsset{Name: name, Size: 100, BrowserDownloadURL: "https://github.com/rinkhals-community/Rinkhals/releases/download/t/" + name}
	}
	return []ghReleaseEntry{
		{TagName: "20261105_01_test", Prerelease: true, Assets: []ghReleaseAsset{asset("update-ks1.swu")}},
		{TagName: "20261103_01", Draft: true, Assets: []ghReleaseAsset{asset("update-ks1.swu")}},
		{TagName: "20261102_01", Assets: []ghReleaseAsset{asset("update-k3m.swu")}}, // nothing for a KS1
		{TagName: "20261101_01", Body: "| Kobra S1 | 2.7.0.9 2.7.2.7 |", Assets: []ghReleaseAsset{asset("update-ks1.swu"), asset("update-k2p-k3.swu")}},
		{TagName: "20261001_01", Assets: []ghReleaseAsset{asset("update-ks1.swu")}},
	}
}

func TestPickUpstreamRelease(t *testing.T) {
	r := pickUpstreamRelease(upstreamReleases(), "KS1", "2.7.3.7")
	if r == nil || r.Tag != "20261101_01" || !strings.HasSuffix(r.AssetURL, "/update-ks1.swu") {
		t.Fatalf("unexpected release %+v", r)
	}
	if r.FirmwareListed || !strings.Contains(r.Warnings[0], "NOT listed") {
		t.Fatalf("2.7.3.7 is not in the notes, the first warning must say so: %v", r.Warnings)
	}
	if r := pickUpstreamRelease(upstreamReleases(), "KS1", "2.7.2.7"); !r.FirmwareListed {
		t.Fatal("2.7.2.7 is listed")
	}
	// S1 Max falls back to the KS1 package, as with Boomslang's own releases
	if r := pickUpstreamRelease(upstreamReleases(), "KS1M", "2.7.2.1"); r == nil || !strings.HasSuffix(r.AssetURL, "/update-ks1.swu") {
		t.Fatalf("unexpected KS1M release %+v", r)
	}
	if r := pickUpstreamRelease(upstreamReleases(), "NOPE", "1.0"); r != nil {
		t.Fatalf("unknown model got %+v", r)
	}
}

func TestUpstreamAssetURLs(t *testing.T) {
	ok := "https://github.com/rinkhals-community/Rinkhals/releases/download/20261101_01/update-ks1.swu"
	if err := validateAssetURL("upstream", ok); err != nil {
		t.Fatal(err)
	}
	for _, bad := range []string{
		"https://github.com/someone/Rinkhals/releases/download/x/update-ks1.swu",
		"https://github.com/Gubir34/Boomslang/releases/download/x/update-ks1.swu",
		"http://github.com/rinkhals-community/Rinkhals/releases/download/x/update-ks1.swu",
		"https://evil.example/rinkhals-community/Rinkhals/releases/download/x/update-ks1.swu",
		"https://objects.githubusercontent.com/rinkhals-community/Rinkhals/releases/download/x/u.swu",
	} {
		if err := validateAssetURL("upstream", bad); err == nil {
			t.Errorf("%s should be refused", bad)
		}
	}
	// and a Rinkhals URL is not accepted as a Boomslang release
	if err := validateAssetURL("rinkhals", ok); err == nil {
		t.Error("an upstream URL must not pass as a Boomslang release")
	}
}

func TestUpstreamPreflightNeedsTheTypedWord(t *testing.T) {
	post := func(body string) int {
		w := httptest.NewRecorder()
		handleInstallPreflight(w, httptest.NewRequest(http.MethodPost, "/api/firmware/install/preflight", bytes.NewBufferString(body)))
		return w.Code
	}
	url := `"asset_url":"https://github.com/rinkhals-community/Rinkhals/releases/download/20261101_01/update-ks1.swu"`
	if code := post(`{"source":"upstream","version":"20261101_01",` + url + `}`); code != http.StatusBadRequest {
		t.Fatalf("without the word: got %d", code)
	}
	if code := post(`{"source":"upstream","version":"20261101_01",` + url + `,"confirm":"rinkhals please"}`); code != http.StatusBadRequest {
		t.Fatalf("with the wrong word: got %d", code)
	}
	// With the word it gets past the check (Moonraker is not running here,
	// which counts as not printing, so a token is minted)
	if code := post(`{"source":"upstream","version":"20261101_01",` + url + `,"confirm":"RINKHALS"}`); code != http.StatusOK {
		t.Fatalf("with the word: got %d", code)
	}
}

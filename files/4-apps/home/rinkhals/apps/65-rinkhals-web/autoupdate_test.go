package main

import (
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

const testAsset = "https://github.com/Gubir34/Boomslang/releases/download/x/update-ks1.swu"

func TestPickAutoUpdate(t *testing.T) {
	releases := []RinkhalsRelease{
		{Tag: "20261114_01_test", IsPrerelease: true, AssetURL: testAsset},
		{Tag: "20261112_02", AssetURL: testAsset},
		{Tag: "20261113_01", AssetURL: ""}, // no package for this printer
		{Tag: "20261110_01", AssetURL: testAsset},
	}
	cases := []struct{ name, current, mode, tried, want string }{
		{"stable picks newest stable", "20261110_01", "stable", "", "20261112_02"},
		{"test picks newest of all", "20261110_01", "test", "", "20261114_01_test"},
		{"off installs nothing", "20261110_01", "off", "", ""},
		{"unknown mode installs nothing", "20261110_01", "weird", "", ""},
		{"up to date", "20261112_02", "stable", "", ""},
		{"newer local build is never downgraded", "20261120_01", "test", "", ""},
		{"dev build is never updated", "abc1234", "stable", "", ""},
		{"tried tag is skipped", "20261110_01", "stable", "20261112_02", ""},
		{"tried test tag falls back to stable", "20261110_01", "test", "20261114_01_test", "20261112_02"},
	}
	check(t, releases, cases)
}

func TestPickAutoUpdateChannels(t *testing.T) {
	releases := []RinkhalsRelease{
		{Tag: "2611-5-alpha", IsPrerelease: true, AssetURL: testAsset},
		{Tag: "2611-4-beta", IsPrerelease: true, AssetURL: testAsset},
		{Tag: "2611-3-release-preview", IsPrerelease: true, AssetURL: testAsset},
		{Tag: "2611-2-release", AssetURL: testAsset},
		{Tag: "20261116_02", AssetURL: testAsset},
	}
	check(t, releases, []struct{ name, current, mode, tried, want string }{
		{"alpha takes everything", "2611-1-alpha", "alpha", "", "2611-5-alpha"},
		{"beta skips alpha", "2611-1-alpha", "beta", "", "2611-4-beta"},
		{"release preview", "2611-1-alpha", "release-preview", "", "2611-3-release-preview"},
		{"release only", "2611-1-alpha", "release", "", "2611-2-release"},
		{"old stable means release", "2611-1-alpha", "stable", "", "2611-2-release"},
		{"old test means alpha", "2611-1-alpha", "test", "", "2611-5-alpha"},
		{"dated install moves to the names", "20261116_01_test", "release", "", "2611-2-release"},
		{"nothing newer", "2611-5-alpha", "alpha", "", ""},
	})
}

func check(t *testing.T, releases []RinkhalsRelease, cases []struct{ name, current, mode, tried, want string }) {
	t.Helper()
	for _, c := range cases {
		got := pickAutoUpdate(releases, c.current, c.mode, c.tried)
		tag := ""
		if got != nil {
			tag = got.Tag
		}
		if tag != c.want {
			t.Errorf("%s: got %q, want %q", c.name, tag, c.want)
		}
	}
}

// stubAutoUpdate replaces the network, printer and installer for one test.
func stubAutoUpdate(t *testing.T, idle []bool, releases []RinkhalsRelease) (installs *int, tried string) {
	t.Helper()
	dir := t.TempDir()
	tried = filepath.Join(dir, "tried")
	calls := 0
	installs = new(int)

	saved := []interface{}{autoUpdateSleep, autoUpdatePrinterIdle, autoUpdateFetchCatalog, autoUpdateRunInstall, autoUpdateCurrent, autoUpdateTriedPath}
	savedNotice, savedNow, savedHours := autoUpdateNoticePath, autoUpdateNow, autoUpdateHours
	autoUpdateNoticePath = filepath.Join(dir, "notice")
	autoUpdateHours = func() string { return "any" }
	t.Cleanup(func() { autoUpdateNoticePath, autoUpdateNow, autoUpdateHours = savedNotice, savedNow, savedHours })
	t.Cleanup(func() {
		autoUpdateSleep = saved[0].(func(time.Duration))
		autoUpdatePrinterIdle = saved[1].(func() bool)
		autoUpdateFetchCatalog = saved[2].(func() (*RinkhalsCatalog, error))
		autoUpdateRunInstall = saved[3].(func(*preflightToken, bool))
		autoUpdateCurrent = saved[4].(func() string)
		autoUpdateTriedPath = saved[5].(string)
		firmwareInstallMu.Lock()
		installCurrent = nil
		firmwareInstallMu.Unlock()
	})

	autoUpdateTriedPath = tried
	autoUpdateSleep = func(time.Duration) {}
	autoUpdateCurrent = func() string { return "20261110_01" }
	autoUpdateFetchCatalog = func() (*RinkhalsCatalog, error) { return &RinkhalsCatalog{Releases: releases}, nil }
	autoUpdatePrinterIdle = func() bool {
		v := idle[len(idle)-1]
		if calls < len(idle) {
			v = idle[calls]
		}
		calls++
		return v
	}
	autoUpdateRunInstall = func(token *preflightToken, dryRun bool) {
		*installs++
		if dryRun {
			t.Error("automatic installs must not be dry runs")
		}
		err := token.BeforeApply()
		firmwareInstallMu.Lock()
		setInstallState(func(s *installRunState) {
			s.State = installStateFailed
			if err != nil {
				s.Error = err.Error()
			}
		})
		firmwareInstallMu.Unlock()
	}
	return installs, tried
}

var newerStable = []RinkhalsRelease{{Tag: "20261112_02", AssetURL: testAsset}}

func TestAutoUpdateWaitsForIdlePrinter(t *testing.T) {
	installs, tried := stubAutoUpdate(t, []bool{true, false}, newerStable)
	if err := autoUpdateOnce(); err == nil || !strings.Contains(err.Error(), "idle") {
		t.Fatalf("expected to wait for the printer, got %v", err)
	}
	if *installs != 0 {
		t.Fatal("must not install while the printer is busy")
	}
	if _, err := os.Stat(tried); err == nil {
		t.Fatal("a skipped update must not be marked as tried")
	}
}

func TestAutoUpdateStopsWhenPrintStartsDuringDownload(t *testing.T) {
	// idle, idle again 2 minutes later, then busy right before update.sh
	installs, tried := stubAutoUpdate(t, []bool{true, true, false}, newerStable)
	autoUpdateOnce()
	if *installs != 1 {
		t.Fatalf("expected one install attempt, got %d", *installs)
	}
	if _, err := os.Stat(tried); err == nil {
		t.Fatal("an install stopped before update.sh must be retried later, not marked as tried")
	}
}

func TestAutoUpdateTriesEachReleaseOnce(t *testing.T) {
	installs, tried := stubAutoUpdate(t, []bool{true}, newerStable)
	autoUpdateOnce()
	data, _ := os.ReadFile(tried)
	if strings.TrimSpace(string(data)) != "20261112_02" {
		t.Fatalf("tried tag not recorded, file has %q", data)
	}
	if err := autoUpdateOnce(); err != nil {
		t.Fatalf("second check should find nothing to do, got %v", err)
	}
	if *installs != 1 {
		t.Fatalf("release installed %d times automatically, want 1", *installs)
	}
}

func at(hour, minute int) time.Time {
	return time.Date(2026, 11, 16, hour, minute, 0, 0, time.UTC)
}

func TestUpdateWindow(t *testing.T) {
	cases := []struct {
		spec string
		hour int
		want bool
	}{
		{"any", 14, true}, {"", 3, true}, {"nonsense", 3, true}, {"25-30", 3, true}, {"04-04", 9, true},
		{"02-06", 2, true}, {"02-06", 5, true}, {"02-06", 6, false}, {"02-06", 1, false}, {"2-6", 3, true},
		{"22-06", 23, true}, {"22-06", 0, true}, {"22-06", 5, true}, {"22-06", 6, false}, {"22-06", 12, false},
		{"20-24", 23, true}, {"20-24", 0, false},
	}
	for _, c := range cases {
		if got := inUpdateWindow(c.spec, at(c.hour, 30)); got != c.want {
			t.Errorf("inUpdateWindow(%q, %02d:30) = %v, want %v", c.spec, c.hour, got, c.want)
		}
	}
	if got := untilUpdateWindow("02-06", at(23, 30)); got != 150*time.Minute {
		t.Errorf("23:30 to 02:00 = %v", got)
	}
	if got := untilUpdateWindow("02-06", at(7, 0)); got != 19*time.Hour {
		t.Errorf("07:00 to 02:00 = %v", got)
	}
	if got := untilUpdateWindow("02-06", at(3, 0)); got != 0 {
		t.Errorf("inside the window = %v", got)
	}
}

func TestAutoUpdateWaitsForTheUpdateHours(t *testing.T) {
	installs, tried := stubAutoUpdate(t, []bool{true}, newerStable)
	autoUpdateHours = func() string { return "02-06" }
	autoUpdateNow = func() time.Time { return at(14, 0) }
	err := autoUpdateOnce()
	var wait *autoUpdateWait
	if !errors.As(err, &wait) || wait.until != 12*time.Hour+time.Minute {
		t.Fatalf("expected to wait 12h for 02:00, got %v", err)
	}
	if *installs != 0 {
		t.Fatal("must not install outside the update hours")
	}
	if _, err := os.Stat(tried); err == nil {
		t.Fatal("a postponed update must not be marked as tried")
	}

	autoUpdateNow = func() time.Time { return at(3, 0) }
	autoUpdateOnce()
	if *installs != 1 {
		t.Fatalf("expected the install inside the update hours, got %d", *installs)
	}
}

func TestAutoUpdateLeavesANoticeForTheTouchScreen(t *testing.T) {
	stubAutoUpdate(t, []bool{true}, newerStable)
	autoUpdateOnce()
	data, err := os.ReadFile(autoUpdateNoticePath)
	if err != nil {
		t.Fatal(err)
	}
	var notice map[string]string
	if json.Unmarshal(data, &notice) != nil || notice["from"] != "20261110_01" || notice["to"] != "20261112_02" {
		t.Fatalf("unexpected notice %s", data)
	}
}

func TestAutoUpdateSkipsWhileAnotherInstallRuns(t *testing.T) {
	installs, _ := stubAutoUpdate(t, []bool{true}, newerStable)
	firmwareInstallMu.Lock()
	installCurrent = &installRunState{State: installStateDownload}
	firmwareInstallMu.Unlock()
	if err := autoUpdateOnce(); err == nil {
		t.Fatal("expected an error while another install runs")
	}
	if *installs != 0 {
		t.Fatal("must not start a second install")
	}
}

func TestAutoUpdateCatalogError(t *testing.T) {
	installs, _ := stubAutoUpdate(t, []bool{true}, nil)
	autoUpdateFetchCatalog = func() (*RinkhalsCatalog, error) { return nil, errors.New("offline") }
	if err := autoUpdateOnce(); err == nil {
		t.Fatal("expected the catalog error to be reported")
	}
	if *installs != 0 {
		t.Fatal("must not install without a catalog")
	}
}

func TestAcceptsGzipQuality(t *testing.T) {
	cases := map[string]bool{
		"gzip":                 true,
		"gzip, deflate, br":    true,
		"br;q=1.0, gzip;q=0.5": true,
		"gzip;q=0":             false,
		"gzip;q=0.0, deflate":  false,
		"deflate, br":          false,
		"":                     false,
	}
	for header, want := range cases {
		r, _ := http.NewRequest("GET", "/", nil)
		r.Header.Set("Accept-Encoding", header)
		if got := acceptsGzip(r); got != want {
			t.Errorf("Accept-Encoding %q: got %v, want %v", header, got, want)
		}
	}
}

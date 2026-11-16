package main

import "testing"

func releaseAssets(names ...string) []ghReleaseAsset {
	out := make([]ghReleaseAsset, 0, len(names))
	for _, n := range names {
		out = append(out, ghReleaseAsset{Name: n, BrowserDownloadURL: "https://github.com/Gubir34/Boomslang/releases/download/x/" + n})
	}
	return out
}

func TestPickUpdateAssetMatchesExactNames(t *testing.T) {
	// k3m listed before k2p-k3 and ks1m before ks1: a substring match would pick the wrong one
	assets := releaseAssets("installer-ks1.swu", "update-k3m.swu", "update-k2p-k3.swu", "update-ks1m.swu", "update-ks1.swu", "tools-ks1.zip")
	cases := map[string]string{
		"K3":   "update-k2p-k3.swu",
		"K3V2": "update-k2p-k3.swu",
		"K2P":  "update-k2p-k3.swu",
		"K3M":  "update-k3m.swu",
		"KS1":  "update-ks1.swu",
		"KS1M": "update-ks1m.swu",
	}
	for model, want := range cases {
		group, _ := modelToAssetGroup(model)
		got := pickUpdateAsset(assets, model, group)
		if got == nil || got.Name != want {
			t.Errorf("%s: got %v, want %s", model, got, want)
		}
	}
}

func TestPickUpdateAssetS1MaxFallsBackToKS1Package(t *testing.T) {
	assets := releaseAssets("update-k2p-k3.swu", "update-ks1.swu")
	group, _ := modelToAssetGroup("KS1M")
	if got := pickUpdateAsset(assets, "KS1M", group); got == nil || got.Name != "update-ks1.swu" {
		t.Fatalf("got %v", got)
	}
}

func TestPickUpdateAssetPrefersCompressed(t *testing.T) {
	assets := releaseAssets("update-k3m.swu", "update-k3m-compressed.swu", "update-k2p-k3.swu",
		"update-k2p-k3-compressed.swu", "update-ks1.swu", "update-ks1-compressed.swu", "update-ks1m.swu")
	cases := []struct {
		model      string
		compressed bool
		want       string
	}{
		{"K3", true, "update-k2p-k3-compressed.swu"},
		{"K3", false, "update-k2p-k3.swu"},
		{"K3M", true, "update-k3m-compressed.swu"},
		{"KS1", true, "update-ks1-compressed.swu"},
		// No update-ks1m-compressed.swu here: the S1 Max takes the KS1
		// compressed package (same content and password) before a standard one
		{"KS1M", true, "update-ks1-compressed.swu"},
		{"KS1M", false, "update-ks1m.swu"},
	}
	for _, c := range cases {
		group, _ := modelToAssetGroup(c.model)
		got := pickUpdateAssetPreferring(assets, c.model, group, c.compressed)
		if got == nil || got.Name != c.want {
			t.Errorf("%s compressed=%v: got %v, want %s", c.model, c.compressed, got, c.want)
		}
	}
}

func TestPickUpdateAssetCompressedFallsBackOnOlderReleases(t *testing.T) {
	group, _ := modelToAssetGroup("KS1")
	if got := pickUpdateAssetPreferring(releaseAssets("update-ks1.swu"), "KS1", group, true); got == nil || got.Name != "update-ks1.swu" {
		t.Fatalf("got %v", got)
	}
}

func TestPickUpdateAssetNoPackage(t *testing.T) {
	if got := pickUpdateAsset(releaseAssets("installer-ks1.swu"), "KS1", "ks1"); got != nil {
		t.Fatalf("expected nil, got %v", got)
	}
}

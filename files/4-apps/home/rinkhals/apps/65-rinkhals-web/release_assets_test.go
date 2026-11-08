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

func TestPickUpdateAssetNoPackage(t *testing.T) {
	if got := pickUpdateAsset(releaseAssets("installer-ks1.swu"), "KS1", "ks1"); got != nil {
		t.Fatalf("expected nil, got %v", got)
	}
}

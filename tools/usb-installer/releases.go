package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// Boomslang releases and the update package of each printer model.
//
// Release names are {YY}{M} {N} {Channel} with the tag 2611-3-alpha (see
// build/release-name.sh in the repository); dated tags (20261108_04) are
// older releases. The same rules as the printer's own updater are used, so
// "newest" means the same thing here and on the printer.

const releasesAPI = "https://api.github.com/repos/Gubir34/Boomslang/releases?per_page=30"

// Model code -> the name group of its update package (update-<group>.swu).
// The S1 Max prefers its own package and falls back to the S1 one, which has
// the same content.
var modelGroups = map[string][]string{
	"K2P":  {"k2p-k3"},
	"K3":   {"k2p-k3"},
	"K3V2": {"k2p-k3"},
	"K3M":  {"k3m"},
	"KS1":  {"ks1"},
	"KS1M": {"ks1m", "ks1"},
}

var modelNames = []struct{ Code, Name string }{
	{"KS1", "Kobra S1"},
	{"KS1M", "Kobra S1 Max"},
	{"K3", "Kobra 3"},
	{"K3V2", "Kobra 3 V2"},
	{"K3M", "Kobra 3 Max"},
	{"K2P", "Kobra 2 Pro"},
}

var channels = []string{"alpha", "beta", "release-preview", "release"} // least to most stable

var channelNames = map[string]string{
	"alpha": "Alpha", "beta": "Beta", "release-preview": "Release Preview", "release": "Release",
}

type asset struct {
	Name   string `json:"name"`
	Size   int64  `json:"size"`
	URL    string `json:"browser_download_url"`
	Digest string `json:"digest"` // "sha256:<hex>" when GitHub has one
}

type release struct {
	Tag        string  `json:"tag_name"`
	Name       string  `json:"name"`
	Prerelease bool    `json:"prerelease"`
	Draft      bool    `json:"draft"`
	Published  string  `json:"published_at"`
	Assets     []asset `json:"assets"`
}

var (
	namePattern  = regexp.MustCompile(`^(\d{2})(1[0-2]|[1-9])-(\d{1,3})-(alpha|beta|release-preview|release)$`)
	datedPattern = regexp.MustCompile(`^(\d{8})_(\d+)`)
)

func channelRank(channel string) int {
	for i, c := range channels {
		if c == channel {
			return i
		}
	}
	return -1
}

// tagKey sorts releases: named ones after dated ones, then by year, month,
// number and channel. nil for anything that is not a release tag.
func tagKey(tag string) []int {
	if m := namePattern.FindStringSubmatch(strings.ToLower(strings.TrimSpace(tag))); m != nil {
		year, _ := strconv.Atoi(m[1])
		month, _ := strconv.Atoi(m[2])
		number, _ := strconv.Atoi(m[3])
		return []int{1, year, month, number, channelRank(m[4])}
	}
	if m := datedPattern.FindStringSubmatch(tag); m != nil {
		date, _ := strconv.Atoi(m[1])
		number, _ := strconv.Atoi(m[2])
		return []int{0, date, number, 0, 0}
	}
	return nil
}

func tagNewer(a, b string) bool {
	ka, kb := tagKey(a), tagKey(b)
	if ka == nil || kb == nil {
		return ka != nil
	}
	for i := range ka {
		if ka[i] != kb[i] {
			return ka[i] > kb[i]
		}
	}
	return false
}

// rank is how stable a release is, as an index in channels. A dated release
// counts as Release unless GitHub marks it as a pre-release.
func (r release) rank() int {
	if m := namePattern.FindStringSubmatch(strings.ToLower(r.Tag)); m != nil {
		return channelRank(m[4])
	}
	if r.Prerelease {
		return 0
	}
	return channelRank("release")
}

// title is the release as a person reads it: "2611 3 Alpha".
func (r release) title() string {
	m := namePattern.FindStringSubmatch(strings.ToLower(r.Tag))
	if m == nil {
		return r.Tag
	}
	number, _ := strconv.Atoi(m[3])
	return fmt.Sprintf("%s%s %d %s", m[1], m[2], number, channelNames[m[4]])
}

// usbAsset is the package of a release to put on a USB drive for this model:
// always the standard one. The -compressed packages can only be installed by
// a printer that already runs Boomslang, never by the stock USB updater.
func (r release) usbAsset(model string) *asset {
	for _, group := range modelGroups[strings.ToUpper(model)] {
		name := "update-" + group + ".swu"
		for i := range r.Assets {
			if r.Assets[i].Name == name {
				return &r.Assets[i]
			}
		}
	}
	return nil
}

// pickRelease returns the newest release for the model that is at least as
// stable as minChannel, or the release with exactly this tag when one is given.
func pickRelease(releases []release, model, minChannel, tag string) *release {
	var best *release
	for i := range releases {
		r := &releases[i]
		if r.Draft || r.usbAsset(model) == nil {
			continue
		}
		if tag != "" {
			if strings.EqualFold(r.Tag, tag) {
				return r
			}
			continue
		}
		if r.rank() < channelRank(minChannel) {
			continue
		}
		if best == nil || tagNewer(r.Tag, best.Tag) {
			best = r
		}
	}
	return best
}

func fetchReleases(url string) ([]release, error) {
	client := &http.Client{Timeout: 20 * time.Second}
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "boomslang-usb")
	req.Header.Set("Accept", "application/vnd.github+json")
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("could not reach GitHub: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 300))
		return nil, fmt.Errorf("GitHub answered %s: %s", resp.Status, strings.TrimSpace(string(body)))
	}
	var releases []release
	if err := json.NewDecoder(resp.Body).Decode(&releases); err != nil {
		return nil, fmt.Errorf("unexpected answer from GitHub: %w", err)
	}
	return releases, nil
}

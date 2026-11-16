package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
)

// Switching to the original Rinkhals (rinkhals-community/Rinkhals), the
// project Boomslang is a fork of. The touch screen has the same option
// (Settings > Switch to Rinkhals).
//
// GET /api/firmware/upstream answers with the latest stable Rinkhals release
// for this printer and whether its notes list the printer's firmware. The
// install itself goes through the normal preflight + commit with source
// "upstream", which additionally needs the word RINKHALS typed by the user
// (checked here, not only in the page).

const (
	upstreamReleasesAPI    = "https://api.github.com/repos/rinkhals-community/Rinkhals/releases?per_page=10"
	upstreamDownloadPrefix = "/rinkhals-community/Rinkhals/releases/download/"
	upstreamConfirmWord    = "RINKHALS"
)

type UpstreamRelease struct {
	Tag            string   `json:"tag"`
	Name           string   `json:"name"`
	URL            string   `json:"url"`
	PublishedAt    string   `json:"published_at"`
	AssetURL       string   `json:"asset_url"`
	AssetSize      int64    `json:"asset_size"`
	Firmware       string   `json:"firmware"`
	FirmwareListed bool     `json:"firmware_listed"`
	Warnings       []string `json:"warnings"`
	ConfirmWord    string   `json:"confirm_word"`
}

func isVersionChar(c byte) bool {
	return (c >= '0' && c <= '9') || c == '.'
}

// firmwareListed reports whether release notes name this firmware version.
// Rinkhals notes carry a "Supported printers" table with the tested
// firmwares. 2.7.3 must not match inside 2.7.3.7 or 12.7.3 (the same rule as
// release_assets.firmware_listed in the touch UI).
func firmwareListed(notes, firmware string) bool {
	if notes == "" || firmware == "" {
		return false
	}
	for from := 0; ; {
		i := strings.Index(notes[from:], firmware)
		if i < 0 {
			return false
		}
		start := from + i
		end := start + len(firmware)
		before := start > 0 && isVersionChar(notes[start-1])
		after := false
		for j := end; j < len(notes) && isVersionChar(notes[j]); j++ {
			if notes[j] != '.' {
				after = true // more digits follow: a longer version number
				break
			}
		}
		if !before && !after {
			return true
		}
		from = start + 1
	}
}

func upstreamWarnings(tag, firmware string, listed bool) []string {
	warnings := []string{
		"This removes Boomslang and installs the original Rinkhals. The Boomslang home screen, browser, automatic updates, app store and this portal's Boomslang features stop working.",
		"There is no button to come back. To return, install a Boomslang update package from a USB drive.",
		"Never do this during a print.",
	}
	if listed {
		warnings = append(warnings, fmt.Sprintf("Rinkhals %s lists firmware %s as supported.", tag, firmware))
	} else {
		warnings = append([]string{fmt.Sprintf(
			"Firmware %s is NOT listed as supported by Rinkhals %s. Rinkhals will probably not start and the printer will run the stock Anycubic software only.",
			firmware, tag)}, warnings...)
	}
	return warnings
}

// pickUpstreamRelease is the newest published, stable Rinkhals release with a
// standard update package for this printer.
func pickUpstreamRelease(raw []ghReleaseEntry, model, firmware string) *UpstreamRelease {
	group, _ := modelToAssetGroup(model)
	if group == "" {
		return nil
	}
	for _, r := range raw {
		if r.Draft || r.Prerelease {
			continue
		}
		asset := pickUpdateAsset(r.Assets, model, group)
		if asset == nil {
			continue
		}
		listed := firmwareListed(r.Body, firmware)
		return &UpstreamRelease{
			Tag:            r.TagName,
			Name:           r.Name,
			URL:            r.HTMLURL,
			PublishedAt:    r.PublishedAt,
			AssetURL:       asset.BrowserDownloadURL,
			AssetSize:      asset.Size,
			Firmware:       firmware,
			FirmwareListed: listed,
			Warnings:       upstreamWarnings(r.TagName, firmware, listed),
			ConfirmWord:    upstreamConfirmWord,
		}
	}
	return nil
}

var fetchUpstreamReleases = func() ([]ghReleaseEntry, error) {
	var raw []ghReleaseEntry
	err := httpGetJSON(upstreamReleasesAPI, &raw)
	return raw, err
}

func handleFirmwareUpstream(w http.ResponseWriter, r *http.Request) {
	if corsPreflight(w, r, "GET, OPTIONS") {
		return
	}
	writeJSONHeaders(w)
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	raw, err := fetchUpstreamReleases()
	if err != nil {
		http.Error(w, "Could not reach the Rinkhals releases: "+err.Error(), http.StatusBadGateway)
		return
	}
	release := pickUpstreamRelease(raw, currentModelCode(), currentKobraVersion())
	if release == nil {
		http.Error(w, "No Rinkhals release with a package for this printer was found", http.StatusNotFound)
		return
	}
	json.NewEncoder(w).Encode(release)
}

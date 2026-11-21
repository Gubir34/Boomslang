package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// Automatic Boomslang updates.
//
// The web portal runs all the time, so it is the one that watches GitHub: a
// few minutes after start and then every few hours it reads the Boomslang
// releases and, when there is a newer one for this printer, installs it with
// the same download / extract / update.sh / reboot flow as the Install button
// in the portal (runInstall).
//
// The "auto_update" property of this app chooses what is installed (set it
// in Boomslang > Apps > Boomslang Web, or in the portal's Apps page):
//
//	auto             the channel of the installed version (the default): on an
//	                 Alpha every release, on a Beta Beta and more stable, on a
//	                 Release only Releases
//	off              never update automatically
//	release          Release only
//	release-preview  Release Preview and Release
//	beta             Beta and everything more stable
//	alpha            every release (every push to master makes an Alpha)
//
// The older values "stable" and "test" still work and mean release and alpha.
//
// The "auto_update_hours" property limits when it installs, as hours of the
// printer's clock: "any" (the default) or a window such as "02-06", so the
// printer doesn't reboot while someone is about to start a print. Windows
// may cross midnight ("22-06").
//
// After an automatic update the touch screen says so once: the versions are
// left in autoUpdateNoticePath for the touch UI (rinkhals-ui.py).
//
// It never interrupts a print:
//   - the printer must be idle through Moonraker, twice, a couple of minutes
//     apart: standby, no heater with a target or still hot, no file being read
//     (autoupdate_idle.go). No answer from Moonraker counts as busy here, unlike
//     the manual install, where the user is looking at the printer
//   - it checks again after the download, right before update.sh runs
//
// Each release is tried once. Its tag is written to autoUpdateTriedPath just
// before update.sh runs, and a tried tag is never installed automatically
// again. A release that fails to install, or installs and then boots back into
// the old version, can't put the printer into an update-reboot loop. Manual
// installs from the portal or the touch screen are not affected.

const (
	autoUpdateAppID       = "65-rinkhals-web"
	autoUpdateProperty    = "auto_update"
	autoUpdateFirstCheck  = 10 * time.Minute
	autoUpdateInterval    = 6 * time.Hour
	autoUpdateIdleRecheck = 2 * time.Minute
)

// Replaced in tests.
var (
	autoUpdateTriedPath    = "/useremain/rinkhals/.auto-update-tried"
	autoUpdateNoticePath   = "/useremain/rinkhals/.auto-update-notice"
	autoUpdateNow          = time.Now
	autoUpdateHours        = func() string { return webAppSetting("auto_update_hours") }
	autoUpdateSleep        = time.Sleep
	autoUpdatePrinterIdle  = printerIdleForAutoUpdate
	autoUpdateFetchCatalog = func() (*RinkhalsCatalog, error) { return getRinkhalsCatalog(true) }
	autoUpdateRunInstall   = runInstall
	autoUpdateCurrent      = currentRinkhalsVersion
)

func startAutoUpdater() {
	// How the install before the last restart ended (autoupdate_report.go)
	settleAutoUpdate("")
	go func() {
		autoUpdateSleep(autoUpdateFirstCheck)
		for {
			delay := autoUpdateInterval
			err := autoUpdateOnce()
			writeAutoUpdateStatus(describeAutoUpdateCheck(autoUpdateMode(), err))
			if err != nil {
				log.Printf("Auto update: %v", err)
				// Waiting for the update hours: come back when they start
				var wait *autoUpdateWait
				if errors.As(err, &wait) && wait.until < delay {
					delay = wait.until
				}
			}
			autoUpdateSleep(delay)
		}
	}()
}

// webAppSetting reads a property of this app the same way tools.sh
// get_app_property does: the user's override, else the default in app.json.
func webAppSetting(key string) string {
	if v, ok := readUserConfig(autoUpdateAppID)[key]; ok {
		return v
	}
	if root, _ := resolveAppRoot(autoUpdateAppID); root != "" {
		if manifest, err := readManifest(root); err == nil && manifest != nil {
			if p, ok := manifest.Properties[key]; ok {
				if d, ok := p["default"]; ok && d != nil {
					return fmt.Sprint(d)
				}
			}
		}
	}
	return ""
}

func autoUpdateMode() string {
	return normalizeAutoUpdateMode(webAppSetting(autoUpdateProperty), autoUpdateCurrent())
}

// autoUpdateWait is returned while a release is waiting for the update hours.
type autoUpdateWait struct {
	tag   string
	hours string
	until time.Duration
}

// autoUpdateFailed is an install that started and ended without the reboot.
type autoUpdateFailed struct {
	tag, state, message string
}

func (f *autoUpdateFailed) Error() string {
	if f.message == "" {
		return fmt.Sprintf("Installing %s stopped (%s)", f.tag, f.state)
	}
	return fmt.Sprintf("Installing %s stopped (%s): %s", f.tag, f.state, f.message)
}

func (w *autoUpdateWait) Error() string {
	return fmt.Sprintf("%s is available, waiting for the update hours (%s, in %s)", w.tag, w.hours, w.until.Round(time.Minute))
}

var updateWindowPattern = regexp.MustCompile(`^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$`)

// parseUpdateWindow reads "02-06" as start and end hours. ok is false for
// "any", an empty value or anything unreadable, which all mean "any time":
// a typo must not stop updates for good.
func parseUpdateWindow(spec string) (start, end int, ok bool) {
	m := updateWindowPattern.FindStringSubmatch(spec)
	if m == nil {
		return 0, 0, false
	}
	start, _ = strconv.Atoi(m[1])
	end, _ = strconv.Atoi(m[2])
	if start > 23 || end > 24 || start == end%24 {
		return 0, 0, false
	}
	return start, end % 24, true
}

func inUpdateWindow(spec string, now time.Time) bool {
	start, end, ok := parseUpdateWindow(spec)
	if !ok {
		return true
	}
	hour := now.Hour()
	if start < end {
		return hour >= start && hour < end
	}
	return hour >= start || hour < end // crosses midnight
}

// untilUpdateWindow is how long until the window next opens (0 inside it).
func untilUpdateWindow(spec string, now time.Time) time.Duration {
	if inUpdateWindow(spec, now) {
		return 0
	}
	start, _, _ := parseUpdateWindow(spec)
	next := time.Date(now.Year(), now.Month(), now.Day(), start, 0, 0, 0, now.Location())
	if !next.After(now) {
		next = next.Add(24 * time.Hour)
	}
	return next.Sub(now)
}

// writeUpdateNotice leaves a note for the touch UI, which tells the user once
// that the printer updated itself (or that the update did not take).
func writeUpdateNotice(from, to string) error {
	data, _ := json.Marshal(map[string]string{
		"from": from,
		"to":   to,
		"time": autoUpdateNow().Format(time.RFC3339),
	})
	return os.WriteFile(autoUpdateNoticePath, data, 0644)
}

// normalizeAutoUpdateMode turns the setting into "off" or a channel name.
// "auto" (the default) follows the channel of the version that is installed:
// a printer on an Alpha gets every release, one on a Beta gets Beta and
// anything more stable, one on a Release only Releases. Whoever installed a
// test version asked for test versions; nobody on a Release is moved to one.
// A version that is not a named release (a dated tag, a dev build) counts as
// Release.
func normalizeAutoUpdateMode(mode, current string) string {
	mode = strings.ToLower(strings.TrimSpace(mode))
	switch mode {
	case "", "auto":
		if channel := releaseTagChannel(current); channel != "" {
			return channel
		}
		return "release"
	case "stable": // before the channel names
		return "release"
	case "test":
		return "alpha"
	case "off":
		return mode
	}
	if channelRank(mode) >= 0 {
		return mode
	}
	return "off" // an unknown value is not a reason to flash the printer
}

// releaseRank is how stable a release is, as an index in releaseChannels.
// Dated tags from before the channel names count as Release unless GitHub
// marks them as pre-releases.
func releaseRank(r *RinkhalsRelease) int {
	if channel := releaseTagChannel(r.Tag); channel != "" {
		return channelRank(channel)
	}
	if r.IsPrerelease {
		return channelRank("alpha")
	}
	return channelRank("release")
}

func readTriedTag() string {
	data, err := os.ReadFile(autoUpdateTriedPath)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(data))
}

func writeTriedTag(tag string) error {
	if err := os.MkdirAll(filepath.Dir(autoUpdateTriedPath), 0755); err != nil {
		return err
	}
	return os.WriteFile(autoUpdateTriedPath, []byte(tag+"\n"), 0644)
}

// pickAutoUpdate returns the newest release to install, or nil. Only release
// tags strictly newer than the running version count (a dev build never gets
// updated), only channels at least as stable as the mode, never the tag that
// was already tried, and only releases with a package for this printer.
func pickAutoUpdate(releases []RinkhalsRelease, current, mode, tried string) *RinkhalsRelease {
	mode = normalizeAutoUpdateMode(mode, current)
	if mode == "off" {
		return nil
	}
	minRank := channelRank(mode)
	var best *RinkhalsRelease
	for i := range releases {
		r := &releases[i]
		if r.AssetURL == "" || r.Tag == "" || r.Tag == tried {
			continue
		}
		if releaseRank(r) < minRank {
			continue
		}
		if !releaseTagNewer(r.Tag, current) {
			continue
		}
		if best == nil || releaseTagNewer(r.Tag, best.Tag) {
			best = r
		}
	}
	return best
}

// autoUpdateOnce checks for a newer release and installs it. It returns nil
// when there is nothing to do; when an install starts and succeeds the
// printer reboots and this never returns.
func autoUpdateOnce() error {
	mode := autoUpdateMode()
	if mode == "off" {
		return nil
	}

	current := autoUpdateCurrent()
	catalog, err := autoUpdateFetchCatalog()
	if err != nil {
		return fmt.Errorf("could not read the releases: %w", err)
	}
	release := pickAutoUpdate(catalog.Releases, current, mode, readTriedTag())
	if release == nil {
		return nil
	}
	if err := validateAssetURL("rinkhals", release.AssetURL); err != nil {
		return fmt.Errorf("release %s: %w", release.Tag, err)
	}

	if hours := autoUpdateHours(); !inUpdateWindow(hours, autoUpdateNow()) {
		return &autoUpdateWait{tag: release.Tag, hours: hours, until: untilUpdateWindow(hours, autoUpdateNow()) + time.Minute}
	}

	// Idle now and still idle a little later: don't start right as a print
	// is being sent
	waitIdle := &autoUpdateHeld{state: "waiting-idle", tag: release.Tag,
		message: fmt.Sprintf("%s is available, waiting for the printer to be idle", release.Tag)}
	if !autoUpdatePrinterIdle() {
		return waitIdle
	}
	autoUpdateSleep(autoUpdateIdleRecheck)
	if !autoUpdatePrinterIdle() {
		return waitIdle
	}

	tag := release.Tag
	token := &preflightToken{
		Source:   "rinkhals",
		Version:  tag,
		AssetURL: release.AssetURL,
		Compat:   &compatibilityReport{Compatible: true},
		BeforeApply: func() error {
			if !autoUpdatePrinterIdle() {
				return fmt.Errorf("the printer is busy, will try again later")
			}
			// From here on the install can change the printer: remember the
			// tag so it is never retried automatically
			if err := writeTriedTag(tag); err != nil {
				return fmt.Errorf("could not record the update attempt: %w", err)
			}
			if err := writeUpdateNotice(current, tag); err != nil {
				log.Printf("Auto update: could not leave the notice for the touch screen: %v", err)
			}
			if err := writeAutoUpdatePending(current, tag); err != nil {
				log.Printf("Auto update: could not record the install for its result: %v", err)
			}
			appendInstallLog(fmt.Sprintf("Automatic update from %s to %s", current, tag))
			autoUpdateNotify(fmt.Sprintf("Installing Boomslang %s", releaseDisplayName(tag)),
				fmt.Sprintf("Automatic update from %s. The printer restarts by itself; you will be told how it went.",
					releaseDisplayName(current)), "arrows_counterclockwise", false)
			return nil
		},
	}

	firmwareInstallMu.Lock()
	if installInProgressLocked() {
		firmwareInstallMu.Unlock()
		return &autoUpdateHeld{state: "waiting-install", tag: tag, message: fmt.Sprintf("%s is available, another install is running", tag)}
	}
	beginInstallLocked(token, "auto-"+randomToken(), false)
	firmwareInstallMu.Unlock()

	log.Printf("Auto update: installing %s (running %s, mode %s)", tag, current, mode)
	autoUpdateRunInstall(token, false)

	// runInstall only returns when the install did not reboot
	firmwareInstallMu.Lock()
	state, message := "", ""
	if installCurrent != nil {
		state, message = installCurrent.State, installCurrent.Error
	}
	firmwareInstallMu.Unlock()
	failed := &autoUpdateFailed{tag: tag, state: state, message: message}
	settleAutoUpdate(failed.Error()) // only if update.sh had started (BeforeApply left the pending file)
	return failed
}

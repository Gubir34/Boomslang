package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// Did it update itself? What the automatic updater did, for people who were not
// standing at the printer:
//
//   - every check leaves its outcome in autoUpdateStatusPath: up to date, a release
//     waiting for the update hours or for the printer to be idle, an error
//   - every automatic install is kept in autoUpdateHistoryPath (the last 20), with
//     whether the printer came back on the new version
//   - with phone notifications on (the ntfy_topic property, see notify.go) the phone
//     is told when an install starts and, after the restart, how it ended
//
// The touch screen (Updates) and the portal (/api/firmware/autoupdate) show both.
//
// How the outcome is known: right before update.sh runs, the versions are left in
// autoUpdatePendingPath. When this app starts again (after the reboot) it compares
// the running version with the one that was installed, records the result and
// removes the file. An install that fails without a reboot is settled at once.

const autoUpdateHistoryMax = 20

// Replaced in tests.
var (
	autoUpdateStatusPath  = "/useremain/rinkhals/.auto-update-status"
	autoUpdatePendingPath = "/useremain/rinkhals/.auto-update-pending"
	autoUpdateHistoryPath = "/useremain/rinkhals/.auto-update-history"
	autoUpdateNotify      = notifyAutoUpdate
)

// autoUpdateHeld is a release that is there but not installed yet, and why.
type autoUpdateHeld struct {
	state   string // waiting-idle, waiting-install
	tag     string
	message string
}

func (h *autoUpdateHeld) Error() string { return h.message }

type autoUpdateStatus struct {
	Checked   time.Time `json:"checked"`
	Mode      string    `json:"mode"`
	State     string    `json:"state"` // off, up-to-date, waiting-hours, waiting-idle, waiting-install, failed, error
	Available string    `json:"available,omitempty"`
	Message   string    `json:"message,omitempty"`
}

type autoUpdateEntry struct {
	Time    time.Time `json:"time"`
	From    string    `json:"from"`
	To      string    `json:"to"`
	Result  string    `json:"result"` // installed, failed
	Message string    `json:"message,omitempty"`
}

// describeAutoUpdateCheck turns what autoUpdateOnce returned into the status shown.
func describeAutoUpdateCheck(mode string, err error) autoUpdateStatus {
	status := autoUpdateStatus{Checked: autoUpdateNow(), Mode: mode}
	var wait *autoUpdateWait
	var held *autoUpdateHeld
	var failed *autoUpdateFailed
	switch {
	case mode == "off":
		status.State = "off"
	case err == nil:
		status.State = "up-to-date"
	case errors.As(err, &wait):
		status.State, status.Available = "waiting-hours", wait.tag
		status.Message = fmt.Sprintf("Waiting for the update hours (%s)", wait.hours)
	case errors.As(err, &held):
		status.State, status.Available, status.Message = held.state, held.tag, held.message
	case errors.As(err, &failed):
		status.State, status.Available, status.Message = "failed", failed.tag, failed.Error()
	default:
		status.State, status.Message = "error", err.Error()
	}
	return status
}

func writeAutoUpdateStatus(status autoUpdateStatus) {
	if err := writeJSONFile(autoUpdateStatusPath, status); err != nil {
		log.Printf("Auto update: could not write the status: %v", err)
	}
}

func readAutoUpdateStatus() *autoUpdateStatus {
	var status autoUpdateStatus
	if readJSONFile(autoUpdateStatusPath, &status) != nil {
		return nil
	}
	return &status
}

func readAutoUpdateHistory() []autoUpdateEntry {
	var history []autoUpdateEntry
	if readJSONFile(autoUpdateHistoryPath, &history) != nil {
		return []autoUpdateEntry{}
	}
	return history
}

func writeAutoUpdatePending(from, to string) error {
	return writeJSONFile(autoUpdatePendingPath, autoUpdateEntry{Time: autoUpdateNow(), From: from, To: to})
}

// settleAutoUpdate records how a started automatic install ended, once. message
// says why it failed when that is known (an install that did not reboot).
func settleAutoUpdate(message string) *autoUpdateEntry {
	var entry autoUpdateEntry
	if readJSONFile(autoUpdatePendingPath, &entry) != nil || entry.To == "" {
		return nil
	}
	if err := os.Remove(autoUpdatePendingPath); err != nil && !os.IsNotExist(err) {
		log.Printf("Auto update: could not remove %s: %v", autoUpdatePendingPath, err)
		return nil // settling again on every start would repeat the notification
	}
	running := autoUpdateCurrent()
	if running == entry.To {
		entry.Result = "installed"
	} else {
		entry.Result = "failed"
		if message == "" {
			message = "The printer started on " + releaseDisplayName(running) + " again"
		}
		entry.Message = message
	}

	history := append(readAutoUpdateHistory(), entry)
	if len(history) > autoUpdateHistoryMax {
		history = history[len(history)-autoUpdateHistoryMax:]
	}
	if err := writeJSONFile(autoUpdateHistoryPath, history); err != nil {
		log.Printf("Auto update: could not write the history: %v", err)
	}
	appendInstallLog(fmt.Sprintf("Automatic update to %s: %s", entry.To, entry.Result))

	if entry.Result == "installed" {
		autoUpdateNotify(fmt.Sprintf("Boomslang updated to %s", releaseDisplayName(entry.To)),
			fmt.Sprintf("Automatic update from %s.", releaseDisplayName(entry.From)), "white_check_mark", false)
	} else {
		autoUpdateNotify(fmt.Sprintf("Automatic update to %s did not complete", releaseDisplayName(entry.To)),
			fmt.Sprintf("%s. Still on %s; it will not be tried again automatically.", entry.Message, releaseDisplayName(running)),
			"warning", true)
	}
	return &entry
}

// notifyAutoUpdate sends to the phone when notifications are on. Right after a
// reboot the network may not be up yet, so it tries for a few minutes, in the
// background.
func notifyAutoUpdate(title, body, tags string, urgent bool) {
	go func() {
		for attempt := 0; attempt < 10; attempt++ {
			topic := strings.TrimSpace(webAppSetting("ntfy_topic"))
			if topic == "" {
				return
			}
			name := modelDisplayName(currentModelCode())
			err := sendNtfy(webAppSetting("ntfy_server"), topic, name+": "+title, body, tags, urgent)
			if err == nil {
				return
			}
			log.Printf("Auto update notification not sent (try %d): %v", attempt+1, err)
			time.Sleep(30 * time.Second)
		}
	}()
}

func writeJSONFile(path string, value interface{}) error {
	data, err := json.Marshal(value)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	temporary := path + ".tmp"
	if err := os.WriteFile(temporary, data, 0644); err != nil {
		return err
	}
	return os.Rename(temporary, path) // never a half written file after a power cut
}

func readJSONFile(path string, value interface{}) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, value)
}

// GET /api/firmware/autoupdate: the setting, the last check and the history.
func handleAutoUpdateReport(w http.ResponseWriter, r *http.Request) {
	if corsPreflight(w, r, "GET, OPTIONS") {
		return
	}
	writeJSONHeaders(w)
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	hours := strings.TrimSpace(autoUpdateHours())
	if hours == "" {
		hours = "any"
	}
	json.NewEncoder(w).Encode(map[string]interface{}{
		"mode":    autoUpdateMode(),
		"hours":   hours,
		"status":  readAutoUpdateStatus(),
		"history": readAutoUpdateHistory(),
	})
}

package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// Is the printer really idle? The automatic updater installs (and reboots) only
// on positive proof, because nobody is watching it:
//
//   - print_stats says standby, complete or cancelled. Not an empty or missing
//     state, and not a Kobra state Moonraker did not translate. GoKlipper can
//     report standby while a print is still running (its end-of-print routine,
//     #184), so the state alone is not enough:
//   - the nozzle and the bed have no target temperature and are cool. A print,
//     a preheat or a purge all heat; an update in the middle of one could leave
//     a heater on with nothing in charge of it.
//   - virtual_sdcard is not reading a file.
//
// Anything missing, unreadable or unexpected means "not idle": the update waits.

const (
	idleNozzleMaxC = 60.0
	idleBedMaxC    = 50.0
)

// Replaced in tests.
var autoUpdateQueryPrinter = func() ([]byte, error) {
	client := &http.Client{Timeout: 3 * time.Second}
	resp, err := client.Get("http://localhost:7125/printer/objects/query?print_stats&extruder&heater_bed&virtual_sdcard")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("moonraker answered %s", resp.Status)
	}
	return io.ReadAll(resp.Body)
}

type idleHeater struct {
	Temperature *float64 `json:"temperature"`
	Target      *float64 `json:"target"`
}

// printerIdleFromQuery judges a Moonraker objects query. It returns why the
// printer is not idle, or "" when it is.
func printerIdleFromQuery(body []byte) string {
	var parsed struct {
		Result struct {
			Status struct {
				PrintStats *struct {
					State *string `json:"state"`
				} `json:"print_stats"`
				Extruder      *idleHeater `json:"extruder"`
				HeaterBed     *idleHeater `json:"heater_bed"`
				VirtualSdcard *struct {
					IsActive *bool `json:"is_active"`
				} `json:"virtual_sdcard"`
			} `json:"status"`
		} `json:"result"`
	}
	if err := json.Unmarshal(body, &parsed); err != nil {
		return "the printer's state could not be read"
	}
	status := parsed.Result.Status
	if status.PrintStats == nil || status.PrintStats.State == nil {
		return "the printer did not report its state"
	}
	switch *status.PrintStats.State {
	case "standby", "complete", "cancelled":
	default:
		return fmt.Sprintf("the printer is %q", *status.PrintStats.State)
	}
	if reason := heaterBusy("nozzle", status.Extruder, idleNozzleMaxC); reason != "" {
		return reason
	}
	if reason := heaterBusy("bed", status.HeaterBed, idleBedMaxC); reason != "" {
		return reason
	}
	if sd := status.VirtualSdcard; sd != nil && sd.IsActive != nil && *sd.IsActive {
		return "a file is being printed"
	}
	return ""
}

func heaterBusy(name string, h *idleHeater, maxC float64) string {
	if h == nil || h.Temperature == nil || h.Target == nil {
		return "the " + name + " temperature is unknown"
	}
	if *h.Target > 0 {
		return fmt.Sprintf("the %s is heating (target %.0f °C)", name, *h.Target)
	}
	if *h.Temperature >= maxC {
		return fmt.Sprintf("the %s is still hot (%.0f °C)", name, *h.Temperature)
	}
	return ""
}

func printerIdleForAutoUpdate() bool {
	body, err := autoUpdateQueryPrinter()
	if err != nil {
		return false // no answer is "busy" here: nobody is watching
	}
	return printerIdleFromQuery(body) == ""
}

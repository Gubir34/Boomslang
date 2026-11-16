package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"
)

// Phone notifications through ntfy (https://ntfy.sh, or a server of your own).
//
// Off until a topic is set in this app's "ntfy_topic" property; the touch
// screen can make one and show it as a QR code (Settings > Phone
// notifications). Subscribe to the topic in the ntfy app and the printer
// tells you when a print finishes, fails, is cancelled or pauses (a pause
// is usually a filament change or a runout that needs you).
//
// What is sent: the printer model, the event and the file name, to the ntfy
// server, and only while a topic is set. Anyone who knows the topic can read
// the messages, which is why the touch screen generates a long random one.

const (
	notifyPollInterval = 15 * time.Second
	notifyDefaultURL   = "https://ntfy.sh"
)

var ntfyTopicPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{1,64}$`)

type printStatus struct {
	State    string
	Filename string
}

type moonrakerPrintDetailResponse struct {
	Result struct {
		Status struct {
			PrintStats struct {
				State    string `json:"state"`
				Filename string `json:"filename"`
			} `json:"print_stats"`
		} `json:"status"`
	} `json:"result"`
}

func fetchPrintStatus() (printStatus, bool) {
	client := &http.Client{Timeout: 3 * time.Second}
	resp, err := client.Get("http://localhost:7125/printer/objects/query?print_stats")
	if err != nil {
		return printStatus{}, false
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return printStatus{}, false
	}
	var parsed moonrakerPrintDetailResponse
	if json.NewDecoder(io.LimitReader(resp.Body, 64*1024)).Decode(&parsed) != nil {
		return printStatus{}, false
	}
	stats := parsed.Result.Status.PrintStats
	return printStatus{State: stats.State, Filename: stats.Filename}, stats.State != ""
}

// printEvent decides whether the change from prev to cur is worth a message.
func printEvent(prev, cur printStatus) (title, tags string, urgent, ok bool) {
	wasActive := prev.State == "printing" || prev.State == "paused"
	switch {
	case wasActive && cur.State == "complete":
		return "Print finished", "white_check_mark", false, true
	case wasActive && cur.State == "error":
		return "Print failed", "x", true, true
	case wasActive && cur.State == "cancelled":
		return "Print cancelled", "no_entry_sign", false, true
	case prev.State == "printing" && cur.State == "paused":
		return "Print paused", "pause_button", true, true
	}
	return "", "", false, false
}

func ntfyTarget(server, topic string) (string, error) {
	topic = strings.TrimSpace(topic)
	if !ntfyTopicPattern.MatchString(topic) {
		return "", fmt.Errorf("invalid ntfy topic")
	}
	server = strings.TrimRight(strings.TrimSpace(server), "/")
	if server == "" {
		server = notifyDefaultURL
	}
	u, err := url.Parse(server)
	if err != nil || (u.Scheme != "https" && u.Scheme != "http") || u.Host == "" {
		return "", fmt.Errorf("invalid ntfy server %q", server)
	}
	return server + "/" + topic, nil
}

func sendNtfy(server, topic, title, body, tags string, urgent bool) error {
	target, err := ntfyTarget(server, topic)
	if err != nil {
		return err
	}
	req, err := http.NewRequest("POST", target, strings.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Title", title)
	if tags != "" {
		req.Header.Set("Tags", tags)
	}
	if urgent {
		req.Header.Set("Priority", "high")
	}
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return fmt.Errorf("ntfy answered %s", resp.Status)
	}
	return nil
}

func startNotifier() {
	go func() {
		var prev printStatus
		for {
			time.Sleep(notifyPollInterval)
			topic := strings.TrimSpace(webAppSetting("ntfy_topic"))
			if topic == "" {
				prev = printStatus{} // off: forget, so turning it on mid-print sends nothing stale
				continue
			}
			cur, ok := fetchPrintStatus()
			if !ok {
				continue // Moonraker restarting is not an event
			}
			if title, tags, urgent, send := printEvent(prev, cur); send {
				file := cur.Filename
				if file == "" {
					file = prev.Filename
				}
				name := modelDisplayName(currentModelCode())
				if err := sendNtfy(webAppSetting("ntfy_server"), topic, name+": "+title, file, tags, urgent); err != nil {
					log.Printf("Notification not sent: %v", err)
				}
			}
			prev = cur
		}
	}()
}

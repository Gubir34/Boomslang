package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestPrintEvents(t *testing.T) {
	cases := []struct {
		prev, cur string
		title     string
		urgent    bool
	}{
		{"printing", "complete", "Print finished", false},
		{"paused", "complete", "Print finished", false},
		{"printing", "error", "Print failed", true},
		{"printing", "cancelled", "Print cancelled", false},
		{"printing", "paused", "Print paused", true},
		{"paused", "printing", "", false},   // resumed
		{"standby", "printing", "", false},  // started
		{"complete", "complete", "", false}, // nothing changed
		{"", "complete", "", false},         // portal started after the print ended
		{"standby", "error", "", false},     // an error outside a print
		{"paused", "paused", "", false},
	}
	for _, c := range cases {
		title, _, urgent, ok := printEvent(printStatus{State: c.prev}, printStatus{State: c.cur})
		if title != c.title || urgent != c.urgent || ok != (c.title != "") {
			t.Errorf("%s -> %s: got %q urgent=%v ok=%v", c.prev, c.cur, title, urgent, ok)
		}
	}
}

func TestSendNtfy(t *testing.T) {
	var path, title, priority, body string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		data, _ := io.ReadAll(r.Body)
		path, title, priority, body = r.URL.Path, r.Header.Get("Title"), r.Header.Get("Priority"), string(data)
	}))
	defer server.Close()

	if err := sendNtfy(server.URL+"/", "boomslang-abc_123", "Kobra S1: Print failed", "benchy.gcode", "x", true); err != nil {
		t.Fatal(err)
	}
	if path != "/boomslang-abc_123" || title != "Kobra S1: Print failed" || priority != "high" || body != "benchy.gcode" {
		t.Fatalf("unexpected request: %s %q %q %q", path, title, priority, body)
	}
}

func TestNtfyRejectsBadTopicsAndServers(t *testing.T) {
	for _, topic := range []string{"", "has space", "a/b", "../x", "ü"} {
		if _, err := ntfyTarget("https://ntfy.sh", topic); err == nil {
			t.Errorf("topic %q should be refused", topic)
		}
	}
	for _, server := range []string{"ftp://x", "not a url", "file:///etc"} {
		if _, err := ntfyTarget(server, "topic"); err == nil {
			t.Errorf("server %q should be refused", server)
		}
	}
	if got, _ := ntfyTarget("", "topic"); got != "https://ntfy.sh/topic" {
		t.Errorf("default server: got %q", got)
	}
}

func TestNtfyServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "nope", http.StatusForbidden)
	}))
	defer server.Close()
	if err := sendNtfy(server.URL, "topic", "t", "b", "", false); err == nil {
		t.Fatal("expected an error for a 403")
	}
}

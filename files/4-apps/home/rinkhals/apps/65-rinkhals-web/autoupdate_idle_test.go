package main

import (
	"errors"
	"strings"
	"testing"
)

func idleQuery(state, extruder, bed, sdcard string) []byte {
	parts := []string{}
	if state != "" {
		parts = append(parts, `"print_stats":`+state)
	}
	if extruder != "" {
		parts = append(parts, `"extruder":`+extruder)
	}
	if bed != "" {
		parts = append(parts, `"heater_bed":`+bed)
	}
	if sdcard != "" {
		parts = append(parts, `"virtual_sdcard":`+sdcard)
	}
	return []byte(`{"result":{"status":{` + strings.Join(parts, ",") + `}}}`)
}

const (
	coolNozzle = `{"temperature":28.5,"target":0}`
	coolBed    = `{"temperature":25,"target":0}`
	notReading = `{"is_active":false}`
)

func TestAnIdlePrinterIsIdle(t *testing.T) {
	for _, state := range []string{"standby", "complete", "cancelled"} {
		if reason := printerIdleFromQuery(idleQuery(`{"state":"`+state+`"}`, coolNozzle, coolBed, notReading)); reason != "" {
			t.Errorf("%s: %s", state, reason)
		}
	}
	// a printer whose virtual_sdcard says nothing about is_active
	if reason := printerIdleFromQuery(idleQuery(`{"state":"standby"}`, coolNozzle, coolBed, `{}`)); reason != "" {
		t.Error(reason)
	}
}

func TestStandbyWithAHeaterOnIsNotIdle(t *testing.T) {
	// GoKlipper can say standby mid-print: the heaters tell the truth
	cases := map[string][2]string{
		"nozzle heating":   {`{"temperature":219.8,"target":220}`, coolBed},
		"nozzle preheat":   {`{"temperature":40,"target":170}`, coolBed},
		"nozzle still hot": {`{"temperature":180,"target":0}`, coolBed},
		"bed heating":      {coolNozzle, `{"temperature":59,"target":60}`},
		"bed still hot":    {coolNozzle, `{"temperature":58,"target":0}`},
	}
	for name, heaters := range cases {
		if reason := printerIdleFromQuery(idleQuery(`{"state":"standby"}`, heaters[0], heaters[1], notReading)); reason == "" {
			t.Errorf("%s: judged idle", name)
		}
	}
}

func TestAnythingMissingOrUnexpectedIsNotIdle(t *testing.T) {
	cases := map[string][]byte{
		"printing":              idleQuery(`{"state":"printing"}`, coolNozzle, coolBed, notReading),
		"empty state":           idleQuery(`{"state":""}`, coolNozzle, coolBed, notReading),
		"no state":              idleQuery(`{}`, coolNozzle, coolBed, notReading),
		"no print_stats":        idleQuery("", coolNozzle, coolBed, notReading),
		"untranslated state":    idleQuery(`{"state":"busy"}`, coolNozzle, coolBed, notReading),
		"error":                 idleQuery(`{"state":"error"}`, coolNozzle, coolBed, notReading),
		"no extruder":           idleQuery(`{"state":"standby"}`, "", coolBed, notReading),
		"no bed":                idleQuery(`{"state":"standby"}`, coolNozzle, "", notReading),
		"no target":             idleQuery(`{"state":"standby"}`, `{"temperature":25}`, coolBed, notReading),
		"reading a file":        idleQuery(`{"state":"standby"}`, coolNozzle, coolBed, `{"is_active":true}`),
		"not json":              []byte("Unauthorized"),
		"moonraker error shape": []byte(`{"error":{"code":503,"message":"Klippy Host not connected"}}`),
	}
	for name, body := range cases {
		if reason := printerIdleFromQuery(body); reason == "" {
			t.Errorf("%s: judged idle", name)
		}
	}
}

func TestNoAnswerFromMoonrakerIsNotIdle(t *testing.T) {
	saved := autoUpdateQueryPrinter
	t.Cleanup(func() { autoUpdateQueryPrinter = saved })
	autoUpdateQueryPrinter = func() ([]byte, error) { return nil, errors.New("connection refused") }
	if printerIdleForAutoUpdate() {
		t.Fatal("no answer must mean busy")
	}
	autoUpdateQueryPrinter = func() ([]byte, error) {
		return idleQuery(`{"state":"standby"}`, `{"temperature":220,"target":220}`, coolBed, notReading), nil
	}
	if printerIdleForAutoUpdate() {
		t.Fatal("a hot nozzle must mean busy")
	}
}

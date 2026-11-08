package main

import "testing"

func TestReleaseTagNewer(t *testing.T) {
	cases := []struct {
		latest, current string
		want            bool
	}{
		{"20261109_01", "20261108_04_test", true},
		{"20261108_02", "20261108_01", true},
		{"20261108_10", "20261108_09", true},
		{"20261108_01", "20261108_01", false},
		{"20261101_01", "20261108_04_test", false},
		{"20261108_01", "20261108_01_test", false},
		{"20261108_01", "dev", false},
		{"20261108_01", "", false},
		{"", "20261108_01", false},
	}
	for _, c := range cases {
		if got := releaseTagNewer(c.latest, c.current); got != c.want {
			t.Errorf("releaseTagNewer(%q, %q) = %v, want %v", c.latest, c.current, got, c.want)
		}
	}
}

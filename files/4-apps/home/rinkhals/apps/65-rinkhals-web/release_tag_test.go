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

		// Named releases: {YY}{M}-{N}-{channel}
		{"2611-4-beta", "2611-3-alpha", true},
		{"2612-1-alpha", "2611-999-release", true},
		{"271-1-alpha", "2612-40-release", true},
		{"2610-1-alpha", "269-5-release", true},
		{"2611-3-release", "2611-3-alpha", true},
		{"2611-3-alpha", "2611-3-alpha", false},
		{"2611-2-release", "2611-3-alpha", false},
		{"2611-1000-alpha", "2611-3-alpha", false},
		{"2613-1-alpha", "2611-3-alpha", false},
		{"2611-1-alpha", "20261116_09_test", true},
		{"20991231_01", "2611-1-alpha", false},
	}
	for _, c := range cases {
		if got := releaseTagNewer(c.latest, c.current); got != c.want {
			t.Errorf("releaseTagNewer(%q, %q) = %v, want %v", c.latest, c.current, got, c.want)
		}
	}
}

func TestReleaseDisplayName(t *testing.T) {
	cases := map[string]string{
		"2611-3-alpha":           "2611 3 Alpha",
		"261-12-release-preview": "261 12 Release Preview",
		"2611-0-release":         "2611 0 Release",
		"20261108_04_test":       "20261108_04_test",
		"":                       "",
	}
	for tag, want := range cases {
		if got := releaseDisplayName(tag); got != want {
			t.Errorf("releaseDisplayName(%q) = %q, want %q", tag, got, want)
		}
	}
}

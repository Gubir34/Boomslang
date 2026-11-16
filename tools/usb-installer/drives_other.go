//go:build !linux && !windows

package main

import "fmt"

// Other systems (macOS, BSD): no drive detection; --target names the folder
// of the mounted USB drive.
func listDrives() ([]drive, error) {
	return nil, fmt.Errorf("USB drives are not detected on this system; use --target with the folder of the mounted drive")
}

func freeSpace(path string) int64 { return -1 }

func mountDrive(d drive) (string, error) {
	return "", fmt.Errorf("mount %s yourself and use --target", d.Device)
}

func flush(root string) {}

const ejectHint = "Eject the drive before pulling it out."

func namedDrive(name string) (drive, bool) {
	return drive{}, false
}

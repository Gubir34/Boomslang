//go:build linux

package main

import (
	"encoding/json"
	"fmt"
	"os/exec"
	"strconv"
	"strings"
	"syscall"
)

// lsblk prints booleans as true/false, "1"/"0" or 1/0 and sizes as numbers or
// strings, depending on its version: read them all the same way.
type loose string

func (l *loose) UnmarshalJSON(data []byte) error {
	*l = loose(strings.Trim(string(data), `"`))
	if *l == "null" {
		*l = ""
	}
	return nil
}

func (l loose) truthy() bool { return l == "true" || l == "1" }
func (l loose) number() int64 {
	n, err := strconv.ParseInt(string(l), 10, 64)
	if err != nil {
		return -1
	}
	return n
}

type blockDevice struct {
	Path        loose         `json:"path"`
	Type        loose         `json:"type"`
	Removable   loose         `json:"rm"`
	Hotplug     loose         `json:"hotplug"`
	Transport   loose         `json:"tran"`
	FS          loose         `json:"fstype"`
	Label       loose         `json:"label"`
	Size        loose         `json:"size"`
	Table       loose         `json:"pttype"`
	Model       loose         `json:"model"`
	Mountpoint  loose         `json:"mountpoint"`
	Mountpoints []loose       `json:"mountpoints"`
	Children    []blockDevice `json:"children"`
}

func (b blockDevice) mount() string {
	if b.Mountpoint != "" {
		return string(b.Mountpoint)
	}
	for _, m := range b.Mountpoints {
		if m != "" {
			return string(m)
		}
	}
	return ""
}

// parseLsblk turns `lsblk -J -b` output into the partitions of USB drives.
func parseLsblk(data []byte) ([]drive, error) {
	var parsed struct {
		Devices []blockDevice `json:"blockdevices"`
	}
	if err := json.Unmarshal(data, &parsed); err != nil {
		return nil, fmt.Errorf("could not read the list of drives: %w", err)
	}
	var drives []drive
	for _, disk := range parsed.Devices {
		if disk.Type != "disk" {
			continue
		}
		// USB sticks and card readers. Anything on another bus (SATA, NVMe)
		// is never offered, removable flag or not: writing to the wrong
		// disk is the one mistake this must not make.
		usb := disk.Transport == "usb" || (disk.Transport == "" && (disk.Removable.truthy() || disk.Hotplug.truthy()))
		if !usb {
			continue
		}
		parts := disk.Children
		if len(parts) == 0 && disk.FS != "" {
			parts = []blockDevice{disk} // formatted without a partition table
		}
		for _, part := range parts {
			if part.FS == "" || (part.Type != "part" && part.Type != "disk") {
				continue
			}
			d := drive{
				Root: part.mount(), Device: string(part.Path), Label: string(part.Label), FS: string(part.FS),
				Table: string(disk.Table), Model: strings.TrimSpace(string(disk.Model)), Size: part.Size.number(), Free: -1,
			}
			if d.Root != "" {
				d.Free = freeSpace(d.Root)
			}
			drives = append(drives, d)
		}
	}
	return drives, nil
}

func listDrives() ([]drive, error) {
	out, err := exec.Command("lsblk", "-J", "-b", "-o",
		"NAME,PATH,TYPE,RM,HOTPLUG,TRAN,FSTYPE,LABEL,SIZE,PTTYPE,MODEL,MOUNTPOINT").Output()
	if err != nil {
		return nil, fmt.Errorf("could not list drives with lsblk (%v); use --target to name the folder of the USB drive yourself", err)
	}
	return parseLsblk(out)
}

func freeSpace(path string) int64 {
	var stat syscall.Statfs_t
	if err := syscall.Statfs(path, &stat); err != nil {
		return -1
	}
	return int64(stat.Bavail) * int64(stat.Bsize)
}

// mountDrive mounts a partition for the current user through udisks, the way
// a file manager does, and returns where it was mounted.
func mountDrive(d drive) (string, error) {
	out, err := exec.Command("udisksctl", "mount", "-b", d.Device).CombinedOutput()
	text := strings.TrimSpace(string(out))
	if err != nil {
		return "", fmt.Errorf("could not mount %s (%s); open it in your file manager and run this again", d.Device, text)
	}
	if i := strings.LastIndex(text, " at "); i >= 0 {
		return strings.TrimRight(strings.TrimSpace(text[i+4:]), "."), nil
	}
	return "", fmt.Errorf("mounted %s but could not tell where: %s", d.Device, text)
}

// flush asks the system to write everything out, so the drive can be removed.
func flush(root string) {
	exec.Command("sync", "-f", root).Run()
}

const ejectHint = "Unmount (eject) the drive in your file manager before pulling it out."

// namedDrive handles a --drive that is not among the detected USB drives.
// On Linux there is nothing safe to guess: --target names a folder outright.
func namedDrive(name string) (drive, bool) {
	return drive{}, false
}

package main

import (
	"fmt"
	"strings"
)

// A place the update package can be written to: a partition of a USB drive.
type drive struct {
	Root   string // where files go: the mount point, or "E:\" on Windows; empty when not mounted
	Device string // /dev/sdb1, or "E:"
	Label  string
	FS     string // as the system names it: vfat, FAT32, exfat, ntfs...
	Table  string // partition table: dos / MBR, gpt / GPT, or empty when unknown
	Model  string
	Size   int64 // bytes, -1 when unknown
	Free   int64 // bytes, -1 when unknown
	Folder bool  // a folder named with --target, not a detected drive: nothing about it is checked
}

func (d drive) isFAT32() bool {
	switch strings.ToLower(d.FS) {
	case "vfat", "fat32", "fat", "msdos":
		return true
	}
	return false
}

// problems lists why the printer would not read this drive (blocking), and
// what could not be checked (warnings). The printer's updater only reads
// FAT32 on an MBR partition table.
func (d drive) problems(need int64) (blocking, warnings []string) {
	if d.Folder {
		warnings = append(warnings, "a folder was named, so the drive was not checked; the printer needs FAT32 on an MBR partition table")
		if d.Free >= 0 && need > 0 && d.Free < need+spaceMargin {
			blocking = append(blocking, fmt.Sprintf("it has %d MB free and the package needs %d MB", d.Free/1024/1024, (need+spaceMargin)/1024/1024))
		}
		return blocking, warnings
	}
	if d.FS == "" {
		warnings = append(warnings, "the file system could not be read; the printer needs FAT32")
	} else if !d.isFAT32() {
		blocking = append(blocking, fmt.Sprintf("it is formatted as %s; the printer only reads FAT32", strings.ToUpper(d.FS)))
	}
	switch strings.ToLower(d.Table) {
	case "dos", "mbr":
	case "gpt":
		blocking = append(blocking, "its partition table is GPT; the printer only reads MBR")
	default:
		warnings = append(warnings, "the partition table could not be checked; the printer needs MBR, not GPT")
	}
	if d.Free >= 0 && need > 0 && d.Free < need+spaceMargin {
		blocking = append(blocking, fmt.Sprintf("it has %d MB free and the package needs %d MB", d.Free/1024/1024, (need+spaceMargin)/1024/1024))
	}
	return blocking, warnings
}

func humanSize(bytes int64) string {
	if bytes < 0 {
		return "?"
	}
	if bytes >= 1<<30 {
		return fmt.Sprintf("%.1f GB", float64(bytes)/(1<<30))
	}
	return fmt.Sprintf("%d MB", bytes>>20)
}

func (d drive) describe() string {
	if d.Folder {
		return "the folder " + d.Root
	}
	name := d.Label
	if name == "" {
		name = d.Model
	}
	if name == "" {
		name = "USB drive"
	}
	where := d.Root
	if where == "" {
		where = "not mounted"
	}
	fs := d.FS
	if fs == "" {
		fs = "unknown"
	}
	return fmt.Sprintf("%s  %s  (%s, %s, %s)", d.Device, name, humanSize(d.Size), strings.ToUpper(fs), where)
}

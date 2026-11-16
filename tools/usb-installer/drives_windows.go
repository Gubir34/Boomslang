//go:build windows

package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

var (
	kernel32             = syscall.NewLazyDLL("kernel32.dll")
	procGetLogicalDrives = kernel32.NewProc("GetLogicalDrives")
	procGetDriveType     = kernel32.NewProc("GetDriveTypeW")
	procGetVolumeInfo    = kernel32.NewProc("GetVolumeInformationW")
	procGetDiskFreeSpace = kernel32.NewProc("GetDiskFreeSpaceExW")
	procFlushFileBuffers = kernel32.NewProc("FlushFileBuffers")
)

const driveRemovable = 2

// listDrives returns the removable drives that have a letter. Fixed disks
// are never offered, so the system drive can't be picked by mistake; a USB
// drive Windows reports as fixed can still be named with --drive.
func listDrives() ([]drive, error) {
	mask, _, _ := procGetLogicalDrives.Call()
	var drives []drive
	for i := 0; i < 26; i++ {
		if mask&(1<<uint(i)) == 0 {
			continue
		}
		letter := string(rune('A' + i))
		root := letter + `:\`
		rootPtr, _ := syscall.UTF16PtrFromString(root)
		kind, _, _ := procGetDriveType.Call(uintptr(unsafe.Pointer(rootPtr)))
		if kind != driveRemovable {
			continue
		}
		drives = append(drives, describeDrive(letter))
	}
	return drives, nil
}

// describeDrive reads what Windows knows about a drive letter.
func describeDrive(letter string) drive {
	root := letter + `:\`
	rootPtr, _ := syscall.UTF16PtrFromString(root)
	d := drive{Root: root, Device: letter + ":", Size: -1, Free: -1}

	label := make([]uint16, 261)
	fs := make([]uint16, 261)
	ok, _, _ := procGetVolumeInfo.Call(uintptr(unsafe.Pointer(rootPtr)),
		uintptr(unsafe.Pointer(&label[0])), uintptr(len(label)), 0, 0, 0,
		uintptr(unsafe.Pointer(&fs[0])), uintptr(len(fs)))
	if ok != 0 {
		d.Label = syscall.UTF16ToString(label)
		d.FS = syscall.UTF16ToString(fs)
	}

	var free, total, totalFree uint64
	ok, _, _ = procGetDiskFreeSpace.Call(uintptr(unsafe.Pointer(rootPtr)),
		uintptr(unsafe.Pointer(&free)), uintptr(unsafe.Pointer(&total)), uintptr(unsafe.Pointer(&totalFree)))
	if ok != 0 {
		d.Free, d.Size = int64(free), int64(total)
	}
	d.Table = partitionStyle(letter)
	return d
}

// partitionStyle asks PowerShell whether the disk behind a letter is MBR or
// GPT. Empty when it can't tell; the caller then only warns.
func partitionStyle(letter string) string {
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "powershell", "-NoProfile", "-NonInteractive", "-Command",
		fmt.Sprintf("(Get-Partition -DriveLetter %s | Get-Disk).PartitionStyle", letter))
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	out, err := cmd.Output()
	if err != nil {
		return ""
	}
	switch strings.ToUpper(strings.TrimSpace(string(out))) {
	case "MBR":
		return "mbr"
	case "GPT":
		return "gpt"
	}
	return ""
}

func freeSpace(path string) int64 {
	ptr, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return -1
	}
	var free, total, totalFree uint64
	ok, _, _ := procGetDiskFreeSpace.Call(uintptr(unsafe.Pointer(ptr)),
		uintptr(unsafe.Pointer(&free)), uintptr(unsafe.Pointer(&total)), uintptr(unsafe.Pointer(&totalFree)))
	if ok == 0 {
		return -1
	}
	return int64(free)
}

func mountDrive(d drive) (string, error) {
	return "", fmt.Errorf("%s has no drive letter; give it one in Disk Management and run this again", d.Device)
}

// flush writes out the volume's cache. Opening the volume needs
// administrator rights; without them the file's own flush has already run.
func flush(root string) {
	volume := `\\.\` + strings.TrimRight(root, `\`)
	ptr, err := syscall.UTF16PtrFromString(volume)
	if err != nil {
		return
	}
	handle, err := syscall.CreateFile(ptr, syscall.GENERIC_WRITE, syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE,
		nil, syscall.OPEN_EXISTING, 0, 0)
	if err != nil {
		return
	}
	defer syscall.CloseHandle(handle)
	procFlushFileBuffers.Call(uintptr(handle))
}

const ejectHint = `Use "Safely Remove Hardware" (the USB icon near the clock) before pulling the drive out.`

// namedDrive handles a --drive letter that is not in the removable list: some
// USB drives and card readers are reported as fixed disks. The Windows drive
// itself is never accepted.
func namedDrive(name string) (drive, bool) {
	letter := strings.ToUpper(strings.TrimRight(strings.TrimSpace(name), `:\/`))
	if len(letter) != 1 || letter[0] < 'A' || letter[0] > 'Z' {
		return drive{}, false
	}
	system := strings.ToUpper(strings.TrimRight(os.Getenv("SystemDrive"), `:\`))
	if system == "" {
		system = "C"
	}
	if letter == system {
		return drive{}, false
	}
	mask, _, _ := procGetLogicalDrives.Call()
	if mask&(1<<uint(letter[0]-'A')) == 0 {
		return drive{}, false
	}
	return describeDrive(letter), true
}

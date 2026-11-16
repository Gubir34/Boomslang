//go:build windows

package main

import (
	"os"
	"syscall"
	"unsafe"
)

// The Windows release is built as a window program (-H=windowsgui): double
// clicking it opens the page with no black console window behind it. A
// program like that has no console, so when it is started from a terminal
// with options (--cli, --list, --help ...) it attaches to that terminal, and
// the output and the questions work as before.

func init() {
	if len(os.Args) < 2 {
		return
	}
	attach := syscall.NewLazyDLL("kernel32.dll").NewProc("AttachConsole")
	const attachParentProcess = ^uintptr(0) // (DWORD)-1
	if ok, _, _ := attach.Call(attachParentProcess); ok == 0 {
		return // no terminal to attach to: it was not started from one
	}
	if out, err := os.OpenFile("CONOUT$", os.O_WRONLY, 0); err == nil {
		os.Stdout, os.Stderr = out, out
	}
	if in, err := os.OpenFile("CONIN$", os.O_RDONLY, 0); err == nil {
		os.Stdin = in
		stdin.Reset(in)
	}
}

// showError tells the user about a failure when there is no console to print
// it to: a dialog box.
func showError(message string) {
	user32 := syscall.NewLazyDLL("user32.dll").NewProc("MessageBoxW")
	text, _ := syscall.UTF16PtrFromString(message)
	title, _ := syscall.UTF16PtrFromString("Boomslang USB installer")
	const iconError = 0x10
	user32.Call(0, uintptr(unsafe.Pointer(text)), uintptr(unsafe.Pointer(title)), iconError)
}

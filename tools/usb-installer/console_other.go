//go:build !windows

package main

import (
	"fmt"
	"os"
)

// There is always a terminal here: errors are printed.
func showError(message string) { fmt.Fprintln(os.Stderr, "\nError:", message) }

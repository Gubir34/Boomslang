package main

import (
	"archive/zip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"hash"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// What the printer looks for on the USB drive: update.swu inside a folder
// with this name. A Kobra 2 Pro on some firmwares looks in "update" instead.
const (
	usbFolder    = "aGVscF9zb3Nf"
	usbFolderK2P = "update"
	usbFileName  = "update.swu"
	spaceMargin  = 8 * 1024 * 1024
)

const (
	downloadAttempts = 6
	stallTimeout     = 45 * time.Second
)

// Replaced in tests.
var retryPause = func(attempt int) { time.Sleep(time.Duration(attempt) * 2 * time.Second) }

// download fetches url into path, reporting progress, and returns the
// SHA-256 of what was written.
//
// A connection that drops or stalls (Wi-Fi, a phone hotspot) is picked up
// where it stopped, with a Range request, instead of starting 70 MB over. If
// the server does not honour the range the download starts again from zero,
// so the result is the same either way; the checksum is verified afterwards.
func download(url, path string, size int64, progress func(done, total int64)) (string, error) {
	file, err := os.Create(path)
	if err != nil {
		return "", err
	}
	defer file.Close()

	hash := sha256.New()
	var done int64
	var lastErr error
	// Give up after downloadAttempts tries in a row that brought nothing.
	// A connection that keeps dropping but moves forward each time (a weak
	// hotspot) gets there in the end.
	for failures := 0; failures < downloadAttempts; {
		if failures > 0 {
			retryPause(failures)
		}
		before := done
		_, total, err := downloadPart(url, file, hash, &done, size, progress)
		if total > 0 {
			size = total
		}
		if err == nil {
			if size > 0 && done != size {
				return "", fmt.Errorf("download incomplete: got %d of %d bytes", done, size)
			}
			if progress != nil {
				progress(done, size)
			}
			if err := file.Sync(); err != nil {
				return "", err
			}
			return hex.EncodeToString(hash.Sum(nil)), nil
		}
		var fatal *fatalError
		if errors.As(err, &fatal) {
			return "", fatal.err
		}
		lastErr = err
		if done > before {
			failures = 1 // it moved forward: keep going, after a short pause
		} else {
			failures++
		}
	}
	return "", fmt.Errorf("download failed: %d tries in a row brought nothing, stopped at %d MB: %w", downloadAttempts, done>>20, lastErr)
}

// fatalError is a failure that trying again will not fix (a 404, a full disk).
type fatalError struct{ err error }

func (f *fatalError) Error() string { return f.err.Error() }

// downloadPart makes one request, continuing from *done when it is not zero.
func downloadPart(url string, file *os.File, hash hash.Hash, done *int64, size int64, progress func(done, total int64)) (restarted bool, total int64, err error) {
	// No overall timeout (the file is large); a connection that sends
	// nothing for stallTimeout is cancelled below instead
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return false, 0, &fatalError{err}
	}
	req.Header.Set("User-Agent", "boomslang-usb")
	if *done > 0 {
		req.Header.Set("Range", fmt.Sprintf("bytes=%d-", *done))
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return false, 0, fmt.Errorf("could not connect: %w", err)
	}
	defer resp.Body.Close()

	switch {
	case resp.StatusCode == http.StatusPartialContent && *done > 0:
		total = size // continuing: the size is already known
	case resp.StatusCode == http.StatusOK:
		if *done > 0 {
			// The range was ignored: this is the whole file again
			if _, err := file.Seek(0, io.SeekStart); err != nil {
				return false, 0, &fatalError{err}
			}
			if err := file.Truncate(0); err != nil {
				return false, 0, &fatalError{err}
			}
			hash.Reset()
			*done = 0
			restarted = true
		}
		total = resp.ContentLength
	case resp.StatusCode >= 500 || resp.StatusCode == http.StatusTooManyRequests:
		return false, 0, fmt.Errorf("the server answered %s", resp.Status)
	default:
		return false, 0, &fatalError{fmt.Errorf("download failed: the server answered %s", resp.Status)}
	}

	stall := time.AfterFunc(stallTimeout, cancel)
	defer stall.Stop()
	buffer := make([]byte, 256*1024)
	last := time.Now()
	for {
		n, readErr := resp.Body.Read(buffer)
		if n > 0 {
			stall.Reset(stallTimeout)
			if _, err := file.Write(buffer[:n]); err != nil {
				return restarted, total, &fatalError{fmt.Errorf("could not write the download: %w", err)}
			}
			hash.Write(buffer[:n])
			*done += int64(n)
			if progress != nil && time.Since(last) > 200*time.Millisecond {
				progress(*done, total)
				last = time.Now()
			}
		}
		if readErr == io.EOF {
			if total > 0 && *done < total {
				return restarted, total, fmt.Errorf("the connection closed early")
			}
			return restarted, total, nil
		}
		if readErr != nil {
			return restarted, total, readErr
		}
	}
}

func sha256File(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()
	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return "", err
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}

// checkPackage makes sure a file is an update package the stock USB updater
// can install: a zip holding update_swu/setup.tar.gz. The contents are
// password protected, but the list of names is not, which is all that is
// read here. A -compressed package (setup.tar.xz) is refused: it would be
// ignored by the printer, or worse, leave the user wondering.
func checkPackage(path string) error {
	archive, err := zip.OpenReader(path)
	if err != nil {
		return fmt.Errorf("this is not an update package (%v)", err)
	}
	defer archive.Close()
	standard, compressed := false, false
	for _, f := range archive.File {
		switch f.Name {
		case "update_swu/setup.tar.gz":
			standard = true
		case "update_swu/setup.tar.xz":
			compressed = true
		}
	}
	switch {
	case standard:
		return nil
	case compressed:
		return fmt.Errorf("this is a compressed package for the printer's own updater; a USB install needs the one without -compressed in its name")
	default:
		return fmt.Errorf("this file has no update_swu/setup.tar.gz inside, it is not an update package")
	}
}

// digestMatches compares a SHA-256 with GitHub's "sha256:<hex>" digest.
// An empty digest (older releases have none) matches anything.
func digestMatches(digest, sum string) bool {
	if digest == "" {
		return true
	}
	return strings.EqualFold(strings.TrimPrefix(strings.ToLower(digest), "sha256:"), sum)
}

// placeOnDrive copies the package to <root>/<folder>/update.swu and reads it
// back to make sure what is on the drive is what was downloaded.
func placeOnDrive(source, root, folder, wantSum string) (string, error) {
	directory := filepath.Join(root, folder)
	if err := os.MkdirAll(directory, 0755); err != nil {
		return "", fmt.Errorf("could not create %s: %w", directory, err)
	}
	target := filepath.Join(directory, usbFileName)
	temporary := target + ".part"

	in, err := os.Open(source)
	if err != nil {
		return "", err
	}
	defer in.Close()
	out, err := os.Create(temporary)
	if err != nil {
		return "", fmt.Errorf("could not write to the drive: %w", err)
	}
	_, copyErr := io.Copy(out, in)
	syncErr := out.Sync() // push it out of the write cache, onto the stick
	closeErr := out.Close()
	for _, err := range []error{copyErr, syncErr, closeErr} {
		if err != nil {
			os.Remove(temporary)
			return "", fmt.Errorf("could not write to the drive: %w", err)
		}
	}

	sum, err := sha256File(temporary)
	if err != nil || sum != wantSum {
		os.Remove(temporary)
		if err == nil {
			err = fmt.Errorf("checksum differs")
		}
		return "", fmt.Errorf("the copy on the drive does not match the download (%v); the drive may be faulty", err)
	}
	os.Remove(target) // Windows will not rename over an existing file
	if err := os.Rename(temporary, target); err != nil {
		os.Remove(temporary)
		return "", fmt.Errorf("could not finish writing %s: %w", target, err)
	}
	return target, nil
}

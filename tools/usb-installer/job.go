package main

import (
	"fmt"
	"os"
	"path/filepath"
)

// reporter receives what happens while a package is written, so the console
// and the browser page can show the same job in their own way.
type reporter struct {
	logf     func(format string, args ...any)
	progress func(done, total int64)
}

func cliReporter() reporter {
	return reporter{
		logf: func(format string, args ...any) { fmt.Printf(format+"\n", args...) },
		progress: func(done, total int64) {
			if total > 0 {
				fmt.Printf("\rDownloading... %3d%%  (%d / %d MB)", done*100/total, done>>20, total>>20)
			} else {
				fmt.Printf("\rDownloading... %d MB", done>>20)
			}
			if total > 0 && done >= total {
				fmt.Println()
			}
		},
	}
}

// writePackage downloads pkg (or uses source, a file already on disk, whose
// SHA-256 is sum), checks it, and writes it to every folder on the drive.
//
// The download goes to the system's temporary files, not onto the stick: it
// is checked before a single byte reaches the drive.
func writePackage(pkg *asset, source, sum string, target drive, folders []string, r reporter) error {
	if pkg != nil {
		temporary, err := os.CreateTemp("", "boomslang-*.swu")
		if err != nil {
			return err
		}
		temporary.Close()
		defer os.Remove(temporary.Name())
		source = temporary.Name()

		sum, err = download(pkg.URL, source, pkg.Size, r.progress)
		if err != nil {
			return err
		}
		if !digestMatches(pkg.Digest, sum) {
			return fmt.Errorf("the download does not match the checksum GitHub published; nothing was written to the drive. Try again")
		}
		if err := checkPackage(source); err != nil {
			return fmt.Errorf("%s: %w", pkg.Name, err)
		}
		r.logf("Download checked.")
	} else if sum == "" {
		var err error
		if sum, err = sha256File(source); err != nil {
			return err
		}
	}

	for _, folder := range folders {
		r.logf("Writing %s...", filepath.Join(target.Root, folder, usbFileName))
		if _, err := placeOnDrive(source, target.Root, folder, sum); err != nil {
			return err
		}
	}
	flush(target.Root)
	return nil
}

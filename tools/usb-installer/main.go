// boomslang-usb prepares a USB drive that installs Boomslang on a printer.
//
// It does by itself what the README asks for by hand: download the update
// package of the printer model, check it, and put it on the drive as
// aGVscF9zb3Nf/update.swu. Run it without arguments and it asks what it
// needs; every answer can also be given as an option (see --help).
//
// It never formats or repartitions anything. A drive the printer could not
// read (not FAT32, or a GPT partition table) is refused with the reason,
// instead of being "fixed" by erasing it.
package main

import (
	"bufio"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

var version = "dev" // set at build time with -ldflags "-X main.version=..."

type options struct {
	model, channel, tag, drive, target, file, folder string
	force, yes, list, cli, gui                       bool
}

var stdin = bufio.NewReader(os.Stdin)

// errQuit is a clean exit the user chose.
var errQuit = errors.New("cancelled")

func main() {
	var o options
	flag.StringVar(&o.model, "model", "", "printer model: KS1, KS1M, K3, K3V2, K3M or K2P")
	flag.StringVar(&o.channel, "channel", "", "least stable channel to accept: release, release-preview, beta or alpha")
	flag.StringVar(&o.tag, "version", "", "install exactly this release, for example 2611-3-alpha")
	flag.StringVar(&o.drive, "drive", "", `USB drive to use: a letter on Windows ("E"), a device or mount point on Linux`)
	flag.StringVar(&o.target, "target", "", "write into this folder instead of a detected drive (the root of the USB drive)")
	flag.StringVar(&o.file, "file", "", "use this update-*.swu file instead of downloading one")
	flag.StringVar(&o.folder, "folder", "", "folder on the drive (default "+usbFolder+"; some Kobra 2 Pro firmwares need \"update\")")
	flag.BoolVar(&o.force, "force", false, "write even when the drive does not look readable by the printer")
	flag.BoolVar(&o.yes, "yes", false, "do not ask for confirmation")
	flag.BoolVar(&o.list, "list", false, "list the USB drives found and exit")
	flag.BoolVar(&o.cli, "cli", false, "ask in this window instead of opening the browser page")
	flag.BoolVar(&o.gui, "gui", false, "open the browser page (the default when started without options)")
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "boomslang-usb %s - put Boomslang on a USB drive for an Anycubic Kobra printer\n\n", version)
		fmt.Fprintf(os.Stderr, "Without options it opens a page in your browser. --cli asks here instead, or:\n\n")
		flag.PrintDefaults()
		fmt.Fprintf(os.Stderr, "\nExample: boomslang-usb --model KS1 --channel release --yes\n")
	}
	flag.Parse()
	if len(os.Args) == 1 || o.gui {
		fmt.Printf("Boomslang USB installer %s\n\n", version)
		if err := runGUI(); err != nil {
			fmt.Fprintf(os.Stderr, "\nError: %v\n", err)
			os.Exit(1)
		}
		return
	}
	wizard := o.cli && flag.NFlag() == 1 // asked for the console version and nothing else: wait before closing

	fmt.Printf("Boomslang USB installer %s\n\n", version)
	err := run(o)
	switch {
	case err == nil:
	case errors.Is(err, errQuit):
		fmt.Println("\nNothing was changed.")
	default:
		fmt.Fprintf(os.Stderr, "\nError: %v\n", err)
	}
	if wizard {
		fmt.Print("\nPress Enter to close.")
		stdin.ReadString('\n')
	}
	if err != nil && !errors.Is(err, errQuit) {
		os.Exit(1)
	}
}

// --- asking ------------------------------------------------------------------

func ask(question string) (string, error) {
	fmt.Print(question)
	line, err := stdin.ReadString('\n')
	if err != nil && line == "" {
		return "", fmt.Errorf("no answer could be read; give the options on the command line (see --help)")
	}
	return strings.TrimSpace(line), nil
}

// choose shows a numbered menu and returns the index picked. An empty answer
// picks the first entry; q cancels.
func choose(title string, entries []string) (int, error) {
	fmt.Println(title)
	for i, entry := range entries {
		fmt.Printf("  %d) %s\n", i+1, entry)
	}
	for {
		answer, err := ask(fmt.Sprintf("Choose 1-%d [1], or q to quit: ", len(entries)))
		if err != nil {
			return 0, err
		}
		if answer == "" {
			return 0, nil
		}
		if strings.EqualFold(answer, "q") {
			return 0, errQuit
		}
		if n, err := strconv.Atoi(answer); err == nil && n >= 1 && n <= len(entries) {
			return n - 1, nil
		}
	}
}

func confirm(question string) (bool, error) {
	answer, err := ask(question + " [y/N] ")
	if err != nil {
		return false, err
	}
	return strings.EqualFold(answer, "y") || strings.EqualFold(answer, "yes"), nil
}

// --- steps -------------------------------------------------------------------

func pickModel(o options) (string, error) {
	if o.model != "" {
		model := strings.ToUpper(strings.TrimSpace(o.model))
		if _, ok := modelGroups[model]; !ok {
			return "", fmt.Errorf("unknown model %q (use KS1, KS1M, K3, K3V2, K3M or K2P)", o.model)
		}
		return model, nil
	}
	entries := make([]string, len(modelNames))
	for i, m := range modelNames {
		entries[i] = fmt.Sprintf("%s (%s)", m.Name, m.Code)
	}
	i, err := choose("Which printer is it for?", entries)
	if err != nil {
		return "", err
	}
	fmt.Println()
	return modelNames[i].Code, nil
}

func describeRelease(r release) string {
	text := "Boomslang " + r.title()
	if r.rank() < channelRank("release") {
		text += "  (test version)"
	}
	if len(r.Published) >= 10 {
		text += "  " + r.Published[:10]
	}
	return text
}

// pickPackage decides which release to install and returns it with its package.
func pickPackage(o options, model string, releases []release) (*release, *asset, error) {
	if o.tag != "" {
		r := pickRelease(releases, model, "alpha", o.tag)
		if r == nil {
			return nil, nil, fmt.Errorf("there is no release %q with a package for the %s", o.tag, model)
		}
		return r, r.usbAsset(model), nil
	}
	if o.channel != "" {
		channel := strings.ToLower(o.channel)
		if channelRank(channel) < 0 {
			return nil, nil, fmt.Errorf("unknown channel %q (use release, release-preview, beta or alpha)", o.channel)
		}
		r := pickRelease(releases, model, channel, "")
		if r == nil {
			return nil, nil, fmt.Errorf("there is no %s (or more stable) release for the %s yet; try --channel alpha", channel, model)
		}
		return r, r.usbAsset(model), nil
	}

	// Asked: the newest stable release first, then newer test versions
	var offered []*release
	if stable := pickRelease(releases, model, "release", ""); stable != nil {
		offered = append(offered, stable)
	}
	for _, channel := range []string{"release-preview", "beta", "alpha"} {
		r := pickRelease(releases, model, channel, "")
		if r == nil {
			continue
		}
		known := false
		for _, have := range offered {
			known = known || have.Tag == r.Tag
		}
		if !known {
			offered = append(offered, r)
		}
	}
	if len(offered) == 0 {
		return nil, nil, fmt.Errorf("no release with a package for the %s was found", model)
	}
	if o.yes {
		// Unattended and no channel named: never pick a test version silently
		if offered[0].rank() < channelRank("release") {
			return nil, nil, fmt.Errorf("there is no stable release for the %s yet; name a test channel with --channel (newest: %s)", model, offered[0].Tag)
		}
		return offered[0], offered[0].usbAsset(model), nil
	}
	entries := make([]string, len(offered))
	for i, r := range offered {
		entries[i] = describeRelease(*r)
	}
	if offered[0].rank() < channelRank("release") {
		fmt.Println("There is no stable release yet. Test versions can have problems.")
	}
	i, err := choose("Which version?", entries)
	if err != nil {
		return nil, nil, err
	}
	fmt.Println()
	return offered[i], offered[i].usbAsset(model), nil
}

// matchDrive finds the drive the user named: a letter, a device or a mount point.
func matchDrive(drives []drive, name string) *drive {
	clean := strings.TrimRight(strings.TrimSpace(name), `\/:`)
	for i := range drives {
		d := &drives[i]
		for _, candidate := range []string{d.Device, d.Root} {
			if candidate != "" && strings.EqualFold(strings.TrimRight(candidate, `\/:`), clean) {
				return d
			}
		}
	}
	return nil
}

func pickDrive(o options, need int64) (drive, error) {
	if o.target != "" {
		info, err := os.Stat(o.target)
		if err != nil || !info.IsDir() {
			return drive{}, fmt.Errorf("%s is not a folder", o.target)
		}
		return drive{Root: o.target, Device: o.target, Folder: true, Size: -1, Free: freeSpace(o.target)}, nil
	}
	for {
		drives, err := listDrives()
		if err != nil {
			return drive{}, err
		}
		if o.drive != "" {
			if d := matchDrive(drives, o.drive); d != nil {
				return *d, nil
			}
			if d, ok := namedDrive(o.drive); ok {
				return d, nil
			}
			return drive{}, fmt.Errorf("no USB drive %q was found (see --list)", o.drive)
		}
		if len(drives) == 0 {
			if o.yes {
				return drive{}, fmt.Errorf("no USB drive was found")
			}
			answer, err := ask("No USB drive was found. Plug one in and press Enter, or q to quit: ")
			if err != nil {
				return drive{}, err
			}
			if strings.EqualFold(answer, "q") {
				return drive{}, errQuit
			}
			continue
		}
		if len(drives) == 1 && o.yes {
			return drives[0], nil
		}
		if o.yes {
			return drive{}, fmt.Errorf("more than one USB drive was found; name one with --drive (see --list)")
		}
		entries := make([]string, len(drives))
		for i, d := range drives {
			entries[i] = d.describe()
			if blocking, _ := d.problems(need); len(blocking) > 0 {
				entries[i] += "\n       cannot be used: " + strings.Join(blocking, "; ")
			}
		}
		i, err := choose("Which USB drive?", entries)
		if err != nil {
			return drive{}, err
		}
		fmt.Println()
		return drives[i], nil
	}
}

const formatHelp = `
The printer only reads USB drives formatted as FAT32 with an MBR partition
table. This tool does not format drives. Format it yourself (this erases it):
  Windows: right click the drive > Format > File system FAT32. Drives over
           32 GB, or with a GPT table, need Disk Management or "diskpart"
           (clean, convert mbr, create partition primary, format fs=fat32 quick).
  Linux:   GNOME Disks or GParted: new "msdos" partition table, one FAT32 partition.
Then run this again.`

func run(o options) error {
	if o.list {
		drives, err := listDrives()
		if err != nil {
			return err
		}
		if len(drives) == 0 {
			fmt.Println("No USB drive was found.")
		}
		for _, d := range drives {
			fmt.Println(d.describe())
			blocking, warnings := d.problems(0)
			for _, p := range blocking {
				fmt.Println("    cannot be used:", p)
			}
			for _, p := range warnings {
				fmt.Println("    note:", p)
			}
		}
		return nil
	}

	model, err := pickModel(o)
	if err != nil {
		return err
	}

	// What to install
	var source, title string
	var sum string
	var size int64
	var pkg *asset
	if o.file != "" {
		info, err := os.Stat(o.file)
		if err != nil {
			return fmt.Errorf("cannot read %s: %w", o.file, err)
		}
		if err := checkPackage(o.file); err != nil {
			return fmt.Errorf("%s: %w", o.file, err)
		}
		source, size, title = o.file, info.Size(), filepath.Base(o.file)
	} else {
		fmt.Println("Looking for releases...")
		releases, err := fetchReleases(releasesAPI)
		if err != nil {
			return err
		}
		var chosen *release
		chosen, pkg, err = pickPackage(o, model, releases)
		if err != nil {
			return err
		}
		size, title = pkg.Size, "Boomslang "+chosen.title()
		if chosen.rank() < channelRank("release") {
			title += " (test version)"
		}
	}

	// Where to put it
	target, err := pickDrive(o, size)
	if err != nil {
		return err
	}
	if target.Root == "" {
		fmt.Printf("%s is not mounted, mounting it...\n", target.Device)
		root, err := mountDrive(target)
		if err != nil {
			return err
		}
		target.Root, target.Free = root, freeSpace(root)
	}
	blocking, warnings := target.problems(size)
	for _, w := range warnings {
		fmt.Println("Note:", w)
	}
	if len(blocking) > 0 && !o.force {
		return fmt.Errorf("%s cannot be used: %s%s", target.Device, strings.Join(blocking, "; "), formatHelp)
	}

	folders := []string{usbFolder}
	switch {
	case o.folder != "":
		if strings.ContainsAny(o.folder, `/\:`) || o.folder == "." || o.folder == ".." {
			return fmt.Errorf("--folder is a single folder name, not a path")
		}
		folders = []string{o.folder}
	case model == "K2P" && !o.yes:
		i, err := choose("The Kobra 2 Pro looks in a different folder on some firmwares. Write to:",
			[]string{"both folders (works either way)", usbFolder + " only", usbFolderK2P + " only"})
		if err != nil {
			return err
		}
		fmt.Println()
		folders = [][]string{{usbFolder, usbFolderK2P}, {usbFolder}, {usbFolderK2P}}[i]
	}

	fmt.Printf("About to write:\n  %s for the %s (%s)\n  to %s", title, model, humanSize(size), target.describe())
	for _, folder := range folders {
		path := filepath.Join(target.Root, folder, usbFileName)
		note := ""
		if _, err := os.Stat(path); err == nil {
			note = "  (replaces the update.swu that is there)"
		}
		fmt.Printf("\n  as %s%s", path, note)
	}
	fmt.Println()
	if !o.yes {
		ok, err := confirm("Go ahead?")
		if err != nil {
			return err
		}
		if !ok {
			return errQuit
		}
	}

	err = writePackage(pkg, source, sum, target, folders, cliReporter())
	if err != nil {
		return err
	}

	fmt.Printf(`
Done. The drive is ready.

  1. %s
  2. Plug it into the printer while the printer is on and not printing.
  3. The printer installs it and restarts by itself. Leave it on until it
     is back; this takes a few minutes.
`, ejectHint)
	return nil
}

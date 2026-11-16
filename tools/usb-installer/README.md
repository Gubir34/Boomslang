# Boomslang USB installer

Puts Boomslang on a USB drive for an Anycubic Kobra printer: it downloads the
right update package for the printer model, checks it, and writes it to the
drive as `aGVscF9zb3Nf/update.swu`, which is what the printer looks for.

Download it from the [Releases](https://github.com/Gubir34/Boomslang/releases)
page:

- Windows: `boomslang-usb-windows-x64.exe`, double click it
- Linux: `boomslang-usb-linux-x64` (or `-arm64`), then
  `chmod +x boomslang-usb-linux-x64 && ./boomslang-usb-linux-x64`

Started without options it opens a window (Edge or Chrome as an app window
when one is installed, otherwise your default browser). **Kobra S1** and the
newest version are already selected: plug in the drive, pick it, and press
**Write to USB drive**. Closing the window quits the program. Nothing is sent
anywhere except to GitHub for the download. It needs no installation and no
extra libraries; the Windows file has the Boomslang icon and opens no console
window.

Prefer the console? `--cli` asks the same questions in the terminal. On
Windows, run the `.exe` from a terminal with an option (`--cli`, `--list`,
`--help`) and it prints there as usual.

## What it checks

- Only USB drives are offered (removable drives on Windows, drives on the USB
  bus on Linux), so an internal disk can't be picked by mistake.
- The printer only reads **FAT32** on an **MBR** partition table. Other
  drives are refused with the reason. The tool never formats anything;
  format the drive yourself first (this erases it).
- The download is resumed when the connection drops, compared with the
  checksum GitHub publishes, and opened to make sure it is a standard update
  package. The `-compressed` packages are refused: the stock USB updater
  can't read them.
- What is written to the drive is read back and compared before it gets the
  name `update.swu`.

## Options

```
boomslang-usb --model KS1 --channel release --yes     # newest stable release, no questions
boomslang-usb --model KS1M --version 2611-3-alpha     # one exact release
boomslang-usb --model K3 --file update-k2p-k3.swu     # a file you already downloaded
boomslang-usb --cli                                   # questions in the terminal, no browser
boomslang-usb --list                                  # the USB drives found
boomslang-usb --target /media/me/STICK ...            # write to a folder, skip drive detection
```

`--channel` takes `release`, `release-preview`, `beta` or `alpha` and picks
the newest release at least that stable. Without `--channel` and with `--yes`
only a stable release is ever chosen.

Models: `KS1` (Kobra S1), `KS1M` (S1 Max), `K3` (Kobra 3), `K3V2`, `K3M`
(Kobra 3 Max), `K2P` (Kobra 2 Pro; it asks which folder, as some of its
firmwares read `update` instead).

## Building

```
cd tools/usb-installer
go test ./...
CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -o boomslang-usb.exe .
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o boomslang-usb .
```

`rsrc_windows_amd64.syso` is the Windows icon; `python3 make-resource.py`
rebuilds it from `icon.png` (the Windows release is linked with
`-H=windowsgui`, see `.github/workflows/auto-release.yml`).

The window is a local web page (`index.html`, embedded in the program) served
on 127.0.0.1 with a random token, so no web page you have open elsewhere can
use it. No dependencies outside Go's standard library. On Linux it uses `lsblk` to
find drives and `udisksctl` to mount one that isn't mounted.

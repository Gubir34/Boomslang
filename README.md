[![Discord](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fdiscord.com%2Fapi%2Finvites%2FbQcrsteFGU%3Fwith_counts%3Dtrue&query=%24.approximate_member_count&logo=discord&logoColor=white&label=Discord&suffix=%20members&color=%235865F2)](https://discord.gg/bQcrsteFGU) [![Downloads](https://img.shields.io/github/downloads/Gubir34/Boomslang/total?label=Downloads&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0idXRmLTgiPz4KPCEtLSBMaWNlbnNlOiBQRC4gTWFkZSBieSBzdGVwaGVuaHV0Y2hpbmdzOiBodHRwczovL2dpdGh1Yi5jb20vc3RlcGhlbmh1dGNoaW5ncy9taWNyb25zIC0tPgo8c3ZnIGZpbGw9IiNmZmZmZmYiIHdpZHRoPSI4MDBweCIgaGVpZ2h0PSI4MDBweCIgdmlld0JveD0iMCAwIDUxMiA1MTIiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIgPjx0aXRsZT5kb3dubG9hZDwvdGl0bGU%2BPHBhdGggZD0iTTIzMiA2NEwyODAgNjQgMjgwIDIxNCAyNzcgMjcwIDMwMCAyNDIgMzU2IDE4OSAzODggMjIxIDI1NiAzNTMgMTI0IDIyMSAxNTYgMTg5IDIxMiAyNDIgMjM1IDI3MCAyMzIgMjE0IDIzMiA2NFpNNjQgNDAwTDQ0OCA0MDAgNDQ4IDQ0OCA2NCA0NDggNjQgNDAwWiIgLz48L3N2Zz4%3D)](https://github.com/Gubir34/Boomslang/releases) [![Firmwares](https://img.shields.io/badge/Stock%20firmwares-blue?logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0idXRmLTgiPz4KPCEtLSBMaWNlbnNlOiBQRC4gTWFkZSBieSBzdGVwaGVuaHV0Y2hpbmdzOiBodHRwczovL2dpdGh1Yi5jb20vc3RlcGhlbmh1dGNoaW5ncy9taWNyb25zIC0tPgo8c3ZnIGZpbGw9IiNmZmZmZmYiIHdpZHRoPSI4MDBweCIgaGVpZ2h0PSI4MDBweCIgdmlld0JveD0iMCAwIDUxMiA1MTIiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIgPjx0aXRsZT5kb3dubG9hZDwvdGl0bGU%2BPHBhdGggZD0iTTIzMiA2NEwyODAgNjQgMjgwIDIxNCAyNzcgMjcwIDMwMCAyNDIgMzU2IDE4OSAzODggMjIxIDI1NiAzNTMgMTI0IDIyMSAxNTYgMTg5IDIxMiAyNDIgMjM1IDI3MCAyMzIgMjE0IDIzMiA2NFpNNjQgNDAwTDQ0OCA0MDAgNDQ4IDQ0OCA2NCA0NDggNjQgNDAwWiIgLz48L3N2Zz4%3D)](https://rinkhals.firmwareforge.org) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/rinkhals-community/Rinkhals)


# Boomslang

Boomslang is a fork of [Rinkhals](https://github.com/rinkhals-community/Rinkhals) by Julien Batonnet and the Rinkhals Community. It keeps Rinkhals' on-printer layout (`/useremain/rinkhals`), so apps and tools made for Rinkhals keep working, and adds support for newer firmware such as Kobra S1 `2.7.3.7`.

Boomslang is a custom firmware for some Anycubic Kobra 3D printers (specifically the ones running Kobra OS, see below for the details).

The goal of this project is to expand existing Anycubic features with better compatibility, apps and more.
This project will likely not support every use case, such as running vanilla Klipper or a specific feature / plugin.

By using Boomslang, you will keep all stock Anycubic features (print screen, Anycubic tools, calibration, ...) and get even more, like:
- Mainsail, Fluidd (with Moonraker)
- USB camera support in Mainsail, Fluidd
- Prints from Orca will show the print screen
- SSH access for customization (user: **root**, password: **rockchip**)
- OTA Boomslang updates
- [Apps system](https://github.com/rinkhals-community/Rinkhals.Apps) (OctoEverywhere, Cloudflare, Tailscale, ...)

Latest version will likely support the two latest firmwares from Anycubic, unless specified. For older firmware please check older releases or our [firmware archive](https://rinkhals.firmwareforge.org).
Here are the supported GoKlipper / K3-family printers and firmwares with the latest Boomslang release:
| Model  | Tested firmwares | Notes |
| -- | -- | -- |
| Kobra 3 (+ combo) | `2.4.5` `2.4.6.7` |
| Kobra 2 Pro | `3.1.2.3` `3.1.4` | Only with mainboard [Trigorilla Spe **B** v1.0.x](https://1coderookie.github.io/Kobra2ProInsights/hardware/mainboard/#trigorilla_spe_b_v10x-stock-new-revision). `3.1.4` seems to be buggy for some people |
| Kobra S1 (+ combo) | `2.7.0.9` `2.7.2.7` | `2.7.3.7` is patched but not yet tested on a printer. Its update writes `2.7.3.5` as the firmware version, so both are accepted |
| Kobra 3 Max (+ combo) | `2.5.1.7` `2.5.2.8` |
| Kobra 3 V2 (+ combo) | `1.1.0.4` `1.1.2.8` |
| Kobra S1 Max (+ combo) | `2.6.9.6` `2.7.1.4` `2.7.2.1` |

The K4-family currently has a separate status:

| Model | Status | Notes |
| -- | -- | -- |
| Kobra X | Not supported | Uses the `KlipperC++` / K4 software base and is currently blocked by SWU RSA signature verification. See the [Kobra X documentation](https://rinkhals-community.github.io/Rinkhals/printers/kobra-x/) for details. |

## Kobra X status

Some Kobra X firmware packages are publicly available and the SWU password has also been recovered.

However, Anycubic moved from the K3 software base (GoKlipper) to a K4 software base using a C++ Klipper port. Because of this, Kobra X support is not expected to be a simple port of the current Boomslang stack.

In addition, the SWU update flow requires a trusted certificate for package acceptance. Until a reliable bypass is discovered, SWU-based firmware injection similar to Boomslang is not currently feasible on Kobra X.

## General Information

In case you're wondering: Rinkhals is named after the rinkhals, a sub-species of Cobras ... Kobra ... Rinkhals 👏 Boomslang keeps the snake theme with another South African snake, the boomslang.

You can join the Rinkhals community on Discord: https://discord.gg/bQcrsteFGU

Since people have been asking, donations are accepted, but please remember this project is built for fun and not for the money. Donations will not be accepted to work on specific bugs or features. The donation link is the Sponsor button at the top of the page.


<p align="center">
    <img width="48" src="https://github.com/rinkhals-community/Rinkhals/blob/master/icon.png?raw=true" />
</p>


## Boomslang installation

> [!WARNING]
> **Make sure you're confident tweaking your printer and you understand what you're doing. We're not responsible if you brick your printer (even if there's some [documentation](https://rinkhals-community.github.io/Rinkhals/printers/recover-boot-issues/)) about that)**

> [!CAUTION]
> Many users want to change their Klipper printer configuration (the printer.cfg file). We strongly advise against modifying the stock printer configuration. Boomslang offers additional protection you don't have while modifying directly your printer configuration. **We won't offer any support** and **your printer might not work properly or not boot anymore**. Check the documentation for more information: [Printer configuration](https://rinkhals-community.github.io/Rinkhals/about/printer-configuration/)

A [quick start guide](https://rinkhals-community.github.io/Rinkhals/guides/rinkhals-quick-start/) is available to get Boomslang up and running on your printer.

There are two options to install Boomslang:
1. Use the provided Boomslang installer (named **install-*.swu**)
2. Install the raw swu directly (named **update-*.swu**)

Either way, you'll need to:
- Download the release / file you want from the [Releases](https://github.com/Gubir34/Boomslang/releases) page
- Rename the downloaded SWU file as **update.swu**
- Copy it in a directory named **aGVscF9zb3Nf** (or **update** for the Kobra 2 Pro in certain conditions) on a FAT32 USB drive (MBR, GPT is not supported)
- Plug the USB drive in your printer

More detailed information about the Boomslang installer are available in the [documentation](https://rinkhals-community.github.io/Rinkhals/about/rinkhals-installer/)

For more information about installation, firmware updates and details about specific situations, go to https://rinkhals-community.github.io/Rinkhals/about/installation-and-firmware-updates/


<p align="center">
    <img width="48" src="https://github.com/rinkhals-community/Rinkhals/blob/master/icon.png?raw=true" />
</p>


## Touch UI

After installation, Boomslang provides a touch UI accessible from the printer screen when you tap the Settings icon, then tap Boomslang.

The main menu gives you quick access to four areas arranged in a 2×2 grid:
- **Manage apps** — enable, disable, start and stop individual apps
- **App Store** — browse and install community apps directly from the printer screen (see below)
- **Updates** — check for and apply OTA Boomslang updates
- **Settings** — advanced options, reboot controls and system information

<p align="center">
    <img width="192" src="./docs/docs/assets/rinkhals-ui/ui-main.png">
    <img width="192" src="./docs/docs/assets/rinkhals-ui/ui-apps.png">
    <img width="192" src="./docs/docs/assets/rinkhals-ui/ui-app-store.png">
    <img width="192" src="./docs/docs/assets/rinkhals-ui/ui-updates.png">
</p>

## Boomslang Installer

From the release pages, you'll find the installer-\*.swu files for your printer model. This is an interactive touch tool to install and update Boomslang and system firmware updates.

You can find more information in [the documentation](https://rinkhals-community.github.io/Rinkhals/about/rinkhals-installer/)

## Apps system

> [!WARNING]
> Those printers are quite weak in terms of CPU and Memory. Every additional app / feature and client you connect to the web interface will make the experience slower and might end up in crashes.<br />
> Having said that, running your printer with Moonraker, 1\~2 apps and 1\~2 connected clients should work fine.

An apps system is provided in Boomslang. It allows for the users to easily add some features to their printer. Some default ones ship with every release (Moonraker, Mainsail, Fluidd, mjpg-streamer, Remote display via VNC, Hostname/mDNS, the opt-in Firmware Collector, and the Boomslang monitor for MQTT) and additional community apps are available on separate repos like:
- https://github.com/rinkhals-community/Rinkhals.Apps (Tailscale, Cloudflare Tunnel, OctoApp, OctoEverywhere, NFS mount, stunnel, and more)
- https://github.com/basvd/Rinkhals.WebUI (a web interface for Boomslang)

The default apps are listed in detail under [Features and built-in apps](https://rinkhals-community.github.io/Rinkhals/about/#features-and-built-in-apps) in the documentation. Instructions on how to install or develop apps live in the Rinkhals.Apps repository.

### App Store

The Boomslang Touch UI includes a built-in **App Store** that lets you browse, install and remove community apps without leaving the printer screen. Apps are sourced directly from [rinkhals-community/Rinkhals.Apps](https://github.com/rinkhals-community/Rinkhals.Apps) on GitHub.

<p align="center">
    <img width="192" src="./docs/docs/assets/rinkhals-ui/ui-app-store.png">
    <img width="192" src="./docs/docs/assets/rinkhals-ui/ui-app-store-detail.png">
</p>

To use it, open the Boomslang Touch UI and tap **App Store**. The store will fetch the latest app list, show version info and flag already-installed apps. Tap any app to see its description, then tap **Install** or **Remove** as needed.


<p align="center">
    <img width="48" src="https://github.com/rinkhals-community/Rinkhals/blob/master/icon.png?raw=true" />
</p>


## Contributing

> [!NOTE]
> If you develop on Windows, don't forget to disable Git's autocrlf function, as this repo contains Linux scripts running on Linux machines.<br />
> Run `git config core.autocrlf false` **BEFORE** cloning the repo

More and more contributors help this project move faster. Thank you everyone!
If you want to help and contribute, whether it's code, documentation or sharing good ideas, the upstream Rinkhals community is on Discord!

<a href="https://github.com/rinkhals-community/Rinkhals/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=rinkhals-community/Rinkhals" />
</a>
<br /><br />

Current maintainers:
- **jbatonnet**
- **martinbogo**
- **antirad**
- **basvd**
  
Special thanks to those people for providing the base research and helping support for more printers:
- **utkabobr** (https://github.com/utkabobr/DuckPro-Kobra3)
- **systemik** (https://github.com/systemik/Kobra3-Firmware)
- **moosbewohner** for Kobra 2 Pro support. (https://github.com/moosbewohner/Rinkhals)
- **Kalenell** and **woswai1337** for Kobra S1 support.
- **evil_santa**, **CalmFrog**, **basvd**, **_René**, **RadioRadio** and more for Kobra 3 Max support.
- **AndrewS** for ethernet adapters USB testing and Kobra X firmware dump.
- **Ac_K** for passwords and technical discovery of Kobra X.
- **clutchthrower** for the built-in App Store in the Touch UI.
- Anycubic for the cool printer and the few OSS items. (https://github.com/ANYCUBIC-3D/Kobra)

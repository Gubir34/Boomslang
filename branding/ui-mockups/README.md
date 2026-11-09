# Boomslang UI mockups

Touch-screen mockups for the printer UI (800×480, landscape). These are the design reference for rebuilding the LVGL screens in `files/3-rinkhals/opt/rinkhals/ui/` (`rinkhals-ui.py`, `lvgl_rinkhals.py`).

- `png/` – one screenshot per screen at exactly 800×480, the real screen size. **This is the reference.**
- `html/` – the same screens as static HTML. Open them in a browser and click through. Not used at runtime.
- Live editable canvas: https://claude.ai/artifact/C9uKYi8ot26jiAuo1a5HPZ

Some text in the mockups is placeholder data. The real UI must fill it from the system: version strings, the IP address, the app list and status, the store catalogue, the changelog, firmware versions, the clock and the QR code.

## Two themes

The user picks a theme in Settings ("Switch to Aero UI" / "Switch to Classic UI"). Both themes have the same features, only the look changes. Persist the choice in a config file, the same way sounds are muted with `MUTE_SOUNDS_FILE`.

### Classic (flat)

| Screen | PNG | Notes |
|---|---|---|
| Home | `Main.png` | 3×2 tile grid (Apps, App Store, Updates, Web portal, Mainsail, Browser), plus a row with Restart / Reboot / Settings |
| Apps | `Apps.png` | Installed apps list: status pill, start/stop switch, chevron to app settings |
| App Store | `FlatStore.png` | Category chips, 2×2 app cards, Install / Installed |
| Updates | `FlatUpdates.png` | Boomslang card (changelog, progress bar, Update) and firmware card |
| Browser | `FlatBrowser.png` | URL bar, reader-mode article, bottom nav (back / forward / text size) |
| Settings | `FlatSettings.png` | Sounds, Switch to Aero UI, Info, Switch to stock, Uninstall Boomslang (red) |
| Web portal | `FlatPortal.png` | Big QR code, URL, Web portal / Mainsail / Fluidd selector |

The Home header shows the logo, "Boomslang", the printer model and IP, and a version pill. Every other screen has a 56 px header with a back arrow and a title. Restart and Reboot open a confirm dialog, as the code does today.

### Aero (glass, Windows 7–style)

Every Aero screen shares the same chrome:

- **Wallpaper:** a dark green radial gradient with flowing light curves. Ship it as one pre-rendered 800×480 image.
- **Top left:** a 60×60 glass back button (undo arrow) that returns to Aero Home.
- **Top centre:** a glass tab hanging from the top edge with the screen title. Aero Home shows logo, "Boomslang", the version and an Update pill instead.
- **Top right:** a glass tray with Wi-Fi, network activity, notifications (red count badge) and printer status.
- **Bottom:** an 84 px taskbar with six 60 px round light "orbs" and a clock/date box at the right. The orb of the current screen gets a 3 px accent ring and a glow.
- **Content area:** y = 82…382 (300 px tall), x = 14…786.

| Orb (left→right) | Screen | PNG |
|---|---|---|
| gear | Settings | `Settings.png` |
| shopping bag | App Store | `Store.png` |
| widgets | Apps | `AeroApps.png` |
| QR | Web portal | `Portal.png` |
| L + magnifier (custom LemSearch icon) | LemSearch | `LemSearch.png` |
| power | Power | `Power.png` (Restart Boomslang / Reboot printer / Switch to stock) |

Aero Home is `Aero.png`. Its Update pill opens `Updates.png`. LemSearch results open `Browser.png`.

The LemSearch icon is a custom glyph, not part of Material Icons: a thick "L" stroke with a small magnifier in its inner corner. It is drawn as SVG in `html/LemSearch.html` and `html/Aero.html`. Export it to a PNG or an LVGL image for the printer.

## Design tokens

| Token | Value |
|---|---|
| Accent (logo green) | `#4fb548` (already `COLOR_PRIMARY`) |
| Light accent (snake belly) | `#c9ea7f` |
| Danger | `#ff7a66` (Classic), `#ff8a78` (Aero), badge `#e0533f` |
| Classic background | `#0d120e` |
| Classic surface / border | `#161d17` / `#243026` |
| Classic icon tile | `#1f2a21` |
| Classic text / muted | `#eef3ec` / `#9aa79a` |
| Aero text / muted | `#f2f8ee` / `#b8cdb0` |
| Aero glass | vertical gradient white 20% → white 7% (48%) → black 18–30% (100%), 1 px white 28% border, 1 px white 35% top inner highlight |
| Aero window panel | black-green `rgba(6,18,8,0.62)`, 1 px white 22% border, radius 16 |
| Aero orb | radial `#ffffff` → `#eef7e8` → `#b7d6a3`, 1 px white 55% border, dark icon `#10210f` |
| Aero pill button | vertical `#e9f8c8` → `#c9ea7f` → accent, dark text `#0b1a0c` |
| Radius | cards 14–16, icon tiles 10–12, pills fully round |
| Font | Inter in the mockups (400/500/600/700). The printer currently has AlibabaSans; either ship Inter TTF or keep AlibabaSans |
| Icons | Material Symbols Rounded names (`settings`, `local_mall`, `widgets`, `qr_code_2`, `power_settings_new`, `wifi`, `swap_vert`, `notifications`, `system_update`, …). The printer has `MaterialIcons-Regular.ttf`: use the matching codepoints |
| Type sizes | titles 20, row titles 16–17, secondary 13, small badges 12 |
| Touch targets | ≥ 44 px everywhere |

## LVGL notes

- Fine in LVGL: flat colours, radius, borders, simple shadows, vertical `bg_grad`, opacity, images.
- **No backdrop blur in LVGL.** The glass look is gradient + opacity + highlight line only.
- Radial gradients (wallpaper, orbs) are not cheap in LVGL v9 on this hardware. Pre-render the wallpaper and the orb background as images, or approximate the orb with a vertical gradient.
- Keep the number of font sizes small. Each size is a separate font in memory.

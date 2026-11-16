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

### Where the code is today

- **Classic** is complete for the Home screen (`layout_classic_home` in `rinkhals-ui.py`).
- **Aero** is the default on 800×480 screens (Kobra S1 and S1 Max); every other screen keeps Classic, because the mockups exist for that size only. It covers the **Home screen**: wallpaper, back button, title tab with the Update pill, tray, taskbar with the six orbs and the clock (`layout_aero_home`). The orbs open the existing screens (Settings, App Store, Apps, Web portal QR, browser, Power), which still look Classic: re-skinning them, and showing the taskbar on every screen, is not done yet.
- Settings has **Look**: Classic, Aero or Liquid Plastic, kept in `/useremain/rinkhals/.ui-theme`. (The older `.classic-ui` flag still means Classic.) If building the Aero or Liquid home fails for any reason the UI falls back to Classic by itself, so the printer is never left without a menu.
- The wallpaper is `assets/aero-wallpaper.bin`, a raw RGB565 LVGL image made by `branding/make-aero-wallpaper.py` from `branding/aero-wallpaper.png`. It is not a PNG on purpose: a PNG is decoded again on every redraw when LVGL's image cache is off.
- Aero is drawn in real pixels (the mockups are 800×480), not in `lv.dpx()` units.

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

### Liquid Plastic (clear glass panes)

Our take on the "liquid glass" look: clear, curved panes that blur and tint what is behind them, lit from the top left, with a thin bright rim that fades around the edge. Capsules and circles, floating, no hard borders, white icons. Same layout as Aero; the look differs, and the tab opens a **quick settings** panel (`Liquid.png`, `LiquidPanel.png`, from `html/Liquid.html` and `html/LiquidPanel.html`).

Where the code is: **Home and the quick settings panel are done**; the other screens (Apps, Store, Settings, Browser) still look Classic when opened from it.

- **Quick settings** (tap the tab): a brightness **slider** (never below 15 %, so the screen can't be set to black), two **toggles** (Sounds, Auto update) and two **buttons** (Web portal, Settings). Tapping outside the panel or its handle closes it. The widgets are in `liquid_ui.py` (`Glass.touch`, `Glass.slider`, `Toggle`, `DropPanel`) and are meant to be reused for the other screens.
- **How it is drawn:** LVGL can't blur what is behind a widget and the printer's CPU could not do it every frame. The panes sit on a fixed wallpaper, so `branding/make-liquid.py` draws them into two pictures with a browser (`assets/liquid-home.bin`, and `liquid-panel.bin` with the panel open), in the same raw RGB565 format as the Aero wallpaper. The printer only shows the picture; the icons, text, clock, slider and a pressed pane's light are live, on top.
- **One set of numbers:** `liquid_layout.py` has every position. The picture generator and the live parts both read it. `tests/test_liquid.py` reads the pictures back and checks that the panes' edges are where the layout says, so a changed layout with old pictures fails the tests.
- The look is chosen in Settings > Look (Classic, Aero, Liquid Plastic; a file, `/useremain/rinkhals/.ui-theme`). Aero is still the default. A look that fails to build falls back to Classic.
- To change the look: edit `liquid_layout.py` or `make-liquid.py`, run `python3 branding/make-liquid.py` (needs Pillow and Firefox), commit the pictures it writes.

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

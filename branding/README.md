# Boomslang branding

`boomslang-logo.svg` is the source of every logo file. `make-installer-sprites.py`
draws the installer progress sprites and error image from the same mascot.

Regenerate everything from the repository root (needs `rsvg-convert` and ImageMagick 7):

```sh
L=branding/boomslang-logo.svg
rsvg-convert -w 512 -h 512 $L -o icon.png
cp icon.png docs/docs/assets/icon.png
cp icon.png web-portal/static/assets/logo.png
rsvg-convert -w 128 -h 128 $L -o web-portal/static/assets/icon.png
cp web-portal/static/assets/icon.png files/3-rinkhals/opt/rinkhals/ui/assets/icon.png
# Boot splash: 24-bit BMP on black, read by ffmpeg in start.sh and rinkhals-ui.sh
magick files/3-rinkhals/opt/rinkhals/ui/assets/icon.png -background black -alpha remove -alpha off \
    -type TrueColor BMP3:files/3-rinkhals/opt/rinkhals/ui/assets/icon.bmp
cp $L web-portal/static/favicon.svg
cp $L web-portal/src/lib/assets/favicon.svg

# Installer sprites: 10 rows of 1024x128 (one per 10% of progress), lossless WebP with alpha
python3 branding/make-installer-sprites.py grid > /tmp/grid.svg
python3 branding/make-installer-sprites.py error > /tmp/error.svg
rsvg-convert /tmp/grid.svg -o /tmp/grid.png
rsvg-convert /tmp/error.svg -o /tmp/error.png
magick /tmp/grid.png -strip -define webp:lossless=true files/3-rinkhals/opt/rinkhals/ui/assets/snake-grid.webp
magick /tmp/error.png -strip -define webp:lossless=true files/3-rinkhals/opt/rinkhals/ui/assets/snake-error.webp
```

Colours: body `#3f9a3c`, head `#4fb548`, belly `#c9ea7f`, eyes `#f6f2c8` / `#2b2f36`,
tongue `#e0533f`, branch `#7a4a24` / `#9c6436`.

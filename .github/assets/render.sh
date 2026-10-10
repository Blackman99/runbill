#!/usr/bin/env bash
# Re-render logo PNG, OG image and social previews. Run from the repo root.
set -euo pipefail
CHROME=${CHROME:-google-chrome}
node .github/assets/gen-logo.js >/dev/null
tmp=$(mktemp -d)
printf '<!doctype html><html><head><style>html,body{margin:0;background:transparent}img{display:block;width:512px;height:512px}</style></head><body><img src="file://%s/site/logo.svg"></body></html>' "$PWD" > "$tmp/logo.html"
shot() { "$CHROME" --headless=new --no-sandbox --disable-gpu --hide-scrollbars --virtual-time-budget=3000 "$@" 2>/dev/null; }
shot --default-background-color=00000000 --window-size=512,512 --screenshot=site/logo-512.png "file://$tmp/logo.html"
shot --window-size=1200,630 --screenshot=site/og-image.png "file://$PWD/.github/assets/og.html?w=1200&h=630"
shot --window-size=1280,640 --screenshot=site/social-preview.png "file://$PWD/.github/assets/og.html?w=1280&h=640"
cp site/social-preview.png og-social-preview.png
shot --window-size=1200,630 --screenshot=docs/assets/og-docs.png "file://$PWD/.github/assets/og.html?w=1200&h=630&docs=1"
rm -rf "$tmp"

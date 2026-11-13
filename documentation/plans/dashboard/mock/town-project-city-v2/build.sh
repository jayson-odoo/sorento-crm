#!/usr/bin/env bash
# Rebuilds the TOWN-PROJECT-CITY mock v2 from the LIVE Town engine:
#   1. townWorldMap.ts = sorento_crm_frontend/.../town/components/townWorld.ts + patches/patch*.py (in order)
#   2. bundles mock.html + mock-entry.ts with the frontend's vite and Tailwind
#   3. inlines the bundle into ../town-project-city-mock-v2.html (one self-contained file)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../../../.." && pwd)"
FE="$ROOT/sorento_crm_frontend"
cp "$FE/app/(protected)/town/components/townWorld.ts" "$HERE/townWorldMap.ts"
sed -i "s#from '\.\./lib/#from '@/app/(protected)/town/lib/#; s#from './TownLightbox'#from '@/app/(protected)/town/components/TownLightbox'#" "$HERE/townWorldMap.ts"
for p in "$HERE"/patches/patch[0-9].py; do python3 "$p" "$HERE/townWorldMap.ts"; done
OUT="$(mktemp -d)"
(cd "$FE" && MOCK_OUT="$OUT" node node_modules/vite/bin/vite.js build --config "$HERE/vite.config.mjs")
python3 - "$OUT" "$HERE/../town-project-city-mock-v2.html" <<'PY'
import pathlib, re, sys
out, dest = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
html = (out / 'mock.html').read_text()
def script(m):
    js = (out / m.group(1).lstrip('./')).read_text().replace('</script', '<\\/script')
    return '<script type="module">' + js + '</script>'
def style(m):
    return '<style>' + (out / m.group(1).lstrip('./')).read_text() + '</style>'
html = re.sub(r'<script type="module" crossorigin src="([^"]+)"></script>', script, html)
html = re.sub(r'<link rel="stylesheet" crossorigin href="([^"]+)">', style, html)
assert 'src="./assets' not in html and 'href="./assets' not in html, 'an asset was not inlined'
dest.write_text(html)
print(dest, len(html) // 1024, 'KB')
PY
rm -rf "$OUT"

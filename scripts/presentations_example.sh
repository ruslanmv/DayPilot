#!/usr/bin/env bash
# Rebuild docs/presentations/examples/superintelligence through the Presentations API, exactly as the
# app does: brand (SVG logo) -> timing plan for the talk -> build, render and check -> files.
#   scripts/presentations_example.sh [http://127.0.0.1:8890] [minutes]
# Needs a gateway with DAYPILOT_PRESENTATIONS=true and the render worker (LibreOffice + poppler).
set -euo pipefail
cd "$(dirname "$0")/.."
B="${1:-http://127.0.0.1:8890}/v1/presentations"
MIN="${2:-5}"
EX=docs/presentations/examples/superintelligence
H=(-H "X-Workspace-Id: ${WORKSPACE:-example}")
J=(-H "Content-Type: application/json")
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
py() { python3 -c "$1"; }

cid=$(curl -fsS "${H[@]}" "${J[@]}" -X POST "$B/companies" -d '{"name":"DayPilot"}' | py "import json,sys;print(json.load(sys.stdin)['id'])")
logo=$(curl -fsS "${H[@]}" -X POST "$B/companies/$cid/assets" -F "file=@$EX/logo.svg;type=image/svg+xml" | py "import json,sys;print(json.load(sys.stdin)['id'])")
curl -fsS "${H[@]}" "${J[@]}" -X POST "$B/companies/$cid/brand-kits" -d "{\"palette\":{\"primary\":\"#1B2A6B\",\"accent\":\"#0FA3B1\",\"foreground\":\"#16203A\"},\"headingFont\":\"Calibri\",\"bodyFont\":\"Calibri\",\"footerText\":\"DayPilot · Leadership briefing\",\"logoAssetId\":\"$logo\",\"activate\":true}" >/dev/null

# Re-time the talk; every slide already has its script, so the words are kept and only the time changes.
py "import json;json.dump({'storyline':json.load(open('$EX/storyline.json')),'minutes':$MIN,'pace':'natural','keepExisting':True},open('$tmp/req.json','w'))"
curl -fsS "${H[@]}" "${J[@]}" -X POST "$B/talk/script" -d @"$tmp/req.json" >"$tmp/timed.json"
py "import json;d=json.load(open('$tmp/timed.json'));[print(f\"{s['seconds']:>4}s  {s['scriptWords']:>3}/{s['words']:<3} words  {s['fit']:<7} {s['title']}\") for s in d['plan']['slides']];[print('advice:',a) for a in d['plan']['advice']];json.dump({'companyId':'$cid','storyline':d['storyline']},open('$tmp/deck.json','w'))"

did=$(curl -fsS "${H[@]}" "${J[@]}" -X POST "$B/decks" -d @"$tmp/deck.json" | py "import json,sys;print(json.load(sys.stdin)['id'])")
for _ in $(seq 1 180); do
  state=$(curl -fsS "${H[@]}" "$B/decks/$did" | py "import json,sys;print(json.load(sys.stdin)['head']['state'])")
  [ "$state" != queued ] && [ "$state" != composing ] && break
  sleep 1
done
curl -fsS "${H[@]}" "$B/decks/$did/revisions/1" | py "import json,sys;r=json.load(sys.stdin);print('state:',r['state'],'quality:',r['quality']);[print(' ',f['severity'],f['code'],f['slide'],f['message']) for f in r['findings']]"
curl -fsS "${H[@]}" "$B/decks/$did/revisions/1/files/pptx" -o "$EX/superintelligence-${MIN}min.pptx"
curl -fsS "${H[@]}" "$B/decks/$did/revisions/1/script" -o "$EX/script-${MIN}min.md"
echo "wrote $EX/superintelligence-${MIN}min.pptx and $EX/script-${MIN}min.md"

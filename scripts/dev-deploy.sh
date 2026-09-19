#!/usr/bin/env bash
# Build, assemble, copy to the handheld and restart Decky Loader.
# Usage: scripts/dev-deploy.sh deck@<host>   (key auth and passwordless sudo required)
set -euo pipefail
HOST="${1:?usage: dev-deploy.sh user@host}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
NAME="Ally DSP"
export PATH="/opt/homebrew/bin:$PATH"
pnpm build >/dev/null
[ -d bin/lv2/lsp-plugins.lv2 ] || scripts/fetch-lsp.sh
scripts/assemble-converter.sh >/dev/null
rm -rf out/deploy; mkdir -p "out/deploy/$NAME/dist" "out/deploy/$NAME/defaults" "out/deploy/$NAME/bin"
cp plugin.json package.json main.py decky.pyi LICENSE THIRD_PARTY_LICENSES.md README.md minisign.pub "out/deploy/$NAME/" 2>/dev/null || true
cp dist/index.js "out/deploy/$NAME/dist/"
cp -R py_modules "out/deploy/$NAME/py_modules"
cp defaults/ally-dsp.service.tmpl defaults/fallback-sources.json defaults/converter-requirements.txt "out/deploy/$NAME/defaults/"
cp -R defaults/converter "out/deploy/$NAME/defaults/converter"
cp -R bin/lv2 "out/deploy/$NAME/bin/lv2"
find "out/deploy/$NAME" -name "__pycache__" -type d -prune -exec rm -rf {} +
ssh "$HOST" 'rm -rf /tmp/ally-dsp-deploy && mkdir -p /tmp/ally-dsp-deploy'
COPYFILE_DISABLE=1 tar -C out/deploy --exclude "._*" --exclude ".DS_Store" -cf - "$NAME" | ssh "$HOST" 'tar -C /tmp/ally-dsp-deploy -xf -'
ssh "$HOST" 'set -e; sudo -n rm -rf "$HOME/homebrew/plugins/Ally DSP"; sudo -n mv "/tmp/ally-dsp-deploy/Ally DSP" "$HOME/homebrew/plugins/Ally DSP"; sudo -n chown -R deck:deck "$HOME/homebrew/plugins/Ally DSP"; sudo -n systemctl restart plugin_loader; echo "deployed, plugin_loader restarted"'

# Architecture

Ally DSP is a Decky Loader plugin with a Python backend (`py_modules/allydsp`),
a React frontend (`src/`) and one audio runtime process. It runs without root
and writes only below the user's home directory.

```
Decky Loader (root) ── plugin backend "Ally DSP" (runs as deck)
                         ├─ setup_flow    hardware check → ASUS package → DAX3 XML → venv → presets → activate
                         ├─ dsp_runtime   ~/.config/systemd/user/ally-dsp.service, active preset
                         ├─ settings      global / per-app preset, extras, update state
                         ├─ jackwatch     pause the chain while headphones are plugged in
                         ├─ updater       GitHub Releases, minisign verification
                         └─ diagnostics   text report
Frontend (QAM) ── get_state / set_* callables, events setup_progress, dsp_state, convert_progress, update_state
               ── SteamClient.GameSessions.RegisterForAppLifetimeNotifications → on_running_app_changed

ally-dsp.service: /usr/bin/pipewire -c ~/homebrew/data/Ally DSP/active/chain.conf
  LV2_PATH=~/homebrew/plugins/Ally DSP/bin/lv2:/usr/lib/lv2
  filter chain: convolver → LSP PEQ → LSP multiband compressor → [LSP autogain] → LSP limiter
  smart filter targeting alsa_output.pci-…analog-stereo
```

## Files on the device

| Path | Content |
|---|---|
| `~/homebrew/plugins/Ally DSP/` | plugin code, `bin/lv2/lsp-plugins.lv2`, `defaults/converter` |
| `~/homebrew/settings/Ally DSP/settings.json` | settings, see below |
| `~/homebrew/data/Ally DSP/dax3/` | tuning XML, INF, `provenance.json` |
| `~/homebrew/data/Ally DSP/venv/` | Python venv with numpy/scipy for the converter (`meta.json` records the Python version) |
| `~/homebrew/data/Ally DSP/presets/<profile>/<voicing>/` | `chain.conf`, `ir.irs`, `converter.conf`, `meta.json` |
| `~/homebrew/data/Ally DSP/active/` | copy of the active preset the unit reads |
| `~/.config/systemd/user/ally-dsp.service` | unit, rendered from `defaults/ally-dsp.service.tmpl` |
| `~/homebrew/logs/Ally DSP/` | backend log, `diagnostics.txt` |

## Setup

`setup_flow.run_setup` runs in a worker thread and reports progress events.

1. `hardware`: Realtek codec and subsystem id from `/proc/asound`, speaker sink
   from `pw-dump`, tools (`7z`, `curl`), bundled LV2 plugins via `lv2ls`.
2. `resolve`: ASUS support API (`GetPDDrivers`), newest "Dolby Atmos driver"
   entry with URL and SHA-256; fallback pinned in `defaults/fallback-sources.json`.
3. `download`: `curl` with resume, progress by file size, SHA-256 check.
4. `extract`: find the 7z signature in the installer, slice the payload, `7z l`
   then `7z e` for `DEV_<dev>_SUBSYS_<ssid>*.xml` and `dax3_ext_rtk.inf`,
   validate the XML (root, security key, profiles), write `provenance.json`.
5. `venv`: `/usr/bin/python3 -m venv`, `pip install -r converter-requirements.txt`
   (fallback unpinned), import check. Rebuilt when the system Python changes.
6. `convert`: for every profile × voicing run
   `dolby_to_pipewire.py <xml> --profile P --variant V --target-sink S --no-activate ...`
   with `LV2_PATH` set, then `confgen.finalize` rewrites the drop-in into a
   standalone config: base modules, fixed node names (`effect_input.ally_dsp`,
   `effect_output.ally_dsp`), smart-filter name and target, IR path.
7. `activate`: write the resolved preset to `active/` and install the unit;
   start it and verify the node in `pw-dump` only when the DSP is switched on
   and no headphones are in use. Autostart follows the DSP switch.

Steps 3–4 and 6 are skipped when provenance and preset metadata already match.
Setup converts and activates with the settings it read at its start; when it
finishes, the backend reconverts if the extras changed meanwhile, otherwise it
applies the resolved preset (per-game preset, pre-gain).

## Runtime

- Preset switch: copy `chain.conf` and `ir.irs` to `active/`, apply pre-gain to
  the limiter input gain, `systemctl --user restart ally-dsp.service`, verify.
- The unit has `ConditionPathExists` on the active config and the LV2 bundle,
  `BindsTo=pipewire.service` and `Restart=on-failure`.
- Per-game presets: the frontend reports the running app id; the backend
  resolves `perApp[appId]` or the global preset and restarts only on change.
- Headphones: `jackwatch` polls the active output route every 3 s and stops the
  unit while `analog-output-headphones` is active; nothing starts the chain
  meanwhile. When the headphones are unplugged it starts the unit if the DSP is
  switched on, also when it was switched on during headphone use.
- Extras: leveler, dialog and regulator switches trigger a reconversion of all
  presets; pre-gain only re-applies the active preset. Virtual bass is offered
  only when Calf LV2 is installed system-wide.

## Settings

```json
{
  "enabled": true,
  "global": {"profile": "game", "voicing": "balanced"},
  "perApp": {"1245620": {"profile": "movie", "voicing": "warm", "enabled": true, "name": "Elden Ring"}},
  "extras": {"autogain": true, "dialog": true, "regulator": true, "virtualBass": false, "preGainDb": 0.0},
  "update": {"channel": "stable", "lastCheck": 0, "lastAttempt": 0, "latest": null, "autoCheck": true},
  "setup": {"done": true, "xmlSha256": "…", "packageVersion": "V11.130.1340.46", "converterVersion": "bde5653",
            "completedAt": "…", "extrasSignature": "…", "targetSink": "alsa_output.pci-0000_64_00.6.analog-stereo"}
}
```

## Updates

1. `updater.check` reads `releases/latest` (cached for six hours). `get_state`
   only reads the cache; a due check runs in the background and reports
   through `update_state`, and a failed one is retried after 30 minutes.
2. `updater.verify_release` downloads `SHA256SUMS` and `SHA256SUMS.minisig`,
   verifies the signature with the pinned `minisign.pub` and returns the zip URL
   and its SHA-256.
3. The frontend calls Decky's `utilities/install_plugin` with that data; Decky
   confirms with the user, downloads, checks the hash, replaces the plugin and
   reloads it. `_startup` re-creates the unit and active preset, or re-runs
   setup when data is missing.
4. Decky imports the new frontend bundle right away, but its `DeckyState` keeps
   the old plugin object as the active one (`setPlugins` does not re-resolve
   it), so the open Quick Access panel still shows the old UI. That panel sees
   the version mismatch and selects the plugin again
   (`DeckyPluginLoader.deckyState.setActivePlugin`, a Decky internal); if that
   does not work, it asks the user to press B and reopen the plugin.

Uninstall: Decky calls `_uninstall` both for a real uninstall and while it
replaces the plugin during an update, and kills the backend 5 s after asking it
to stop. `_uninstall` therefore only starts a transient user unit
(`systemd-run --on-active=60`) that disables the unit and deletes it and the
runtime data if `plugin.json` is gone by then. A starting backend cancels
pending removals. The unit's `ConditionPathExists` on the LV2 bundle keeps it
from starting once the plugin directory is gone.

First install: `install.sh` (sudo) downloads the latest release, verifies
`SHA256SUMS` and the signature, installs into `~/homebrew/plugins/Ally DSP` and
restarts Decky.

## Release pipeline

`release.yml` runs on tags `v*`: build and typecheck the frontend, `pytest`,
assemble the converter from the submodule, fetch and trim the LSP LV2 bundle
(`scripts/fetch-lsp.sh`), package `ally-dsp-<version>.zip`, sign `SHA256SUMS`
with the `MINISIGN_SEED` secret (`python3 -m allydsp.minisign sign`), verify the
signature against the committed key and create the release. The tag must equal
the `package.json` version.

## Compatibility notes

- Decky runs plugin backends in its bundled Python 3.11 (PyInstaller). It lacks
  `xml.etree` and may lack other stdlib modules; the backend only uses `re`,
  `json`, `os`, `subprocess`, `shutil`, `hashlib`, `base64`, `time`, `asyncio`,
  `threading`.
- Settings: the backend saves everything except `setup`, which `setup_flow`
  writes from its worker thread; both go through `settings` under one lock.
- Backends do not inherit `XDG_RUNTIME_DIR` or the session bus address;
  `util.user_env` sets them from the uid.
- The CLI (`python3 -m allydsp.cli`) uses the system Python and the same paths.

## Open items

- Listening test and QAM handling by the maintainer; suspend/resume behaviour.
- End-to-end test of the in-app update with a second release.
- Optional pre-release channel via GitHub pre-releases.
- Upstream: a `hardware-profile` for the RC73XA in Bazzite or `steamdeck-dsp`.
- Upstream (Decky): `DeckyState.setPlugins` could re-resolve `_activePlugin` by
  name, so every plugin shows its new UI after an update.

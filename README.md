# Ally DSP

Decky Loader plugin that restores the **Dolby speaker tuning of the ROG Xbox Ally X**
on SteamOS. Under Windows the built-in speakers are shaped by Dolby Atmos; on
SteamOS they play untreated. Ally DSP downloads ASUS' public Dolby driver package
onto your device, extracts the tuning made for your exact codec, converts it with
[speaker-tuning-to-easyeffects](https://github.com/antoinecellerier/speaker-tuning-to-easyeffects)
into a PipeWire filter chain and runs that chain as a WirePlumber smart filter in
front of the speaker sink. Steam keeps seeing the real speakers, the volume keys
keep working, headphones pause the chain.

Deutsch: Das Plugin holt das ASUS-Dolby-Tuning für das Xbox Ally X auf das Gerät,
wandelt es in eine PipeWire-Filter-Chain um und bietet die Dolby-Profile (Game,
Movie, Music, Voice, Dynamic, Custom 1–3) mit den Voicings Balanced/Detailed/Warm
global oder pro Spiel an.

## Features

- Setup wizard: hardware check, ASUS package download with SHA-256 verification,
  extraction of `DEV_0294_SUBSYS_10431384_*.xml`, private Python venv for the
  converter, conversion of all profiles, activation.
- Presets: Game, Dynamic, Movie, Music, Voice, Custom 1–3 × Balanced/Detailed/Warm.
- Global preset or per-game preset (switches automatically with the running app).
- Extras: Dolby volume leveler (on by default), dialog enhancer, regulator,
  experimental virtual bass, pre-gain.
- Headphone detection on the shared 3.5 mm jack pauses the speaker chain.
- Diagnostics page and text report for bug reports.
- Self-update from GitHub Releases: signed `SHA256SUMS` (minisign format) verified
  against the pinned `minisign.pub`, installation delegated to Decky Loader.
- No root, nothing written outside your home directory.

## Supported hardware

| Device | Codec subsystem | Status |
|---|---|---|
| ROG Xbox Ally X (RC73XA) | 1043:1384 | developed and tested on SteamOS 3.8.16 |
| ROG Xbox Ally (RC73YA) | 1043:1394 | tuning is in the same ASUS package, untested |

Requirements: SteamOS 3.8 or newer (PipeWire ≥ 1.4 with LV2 support, WirePlumber
0.5), Decky Loader, internet access during setup (≈ 10 MB ASUS package plus
≈ 220 MB numpy/scipy for the converter).

## Install

Decky Loader must be installed. In Desktop Mode open Konsole and run:

```bash
curl -sL https://github.com/bassobr/decky-ally-dsp/raw/main/install.sh -o /tmp/ally-dsp-install.sh && sudo bash /tmp/ally-dsp-install.sh
```

Then open the Quick Access menu → Decky → Ally DSP → **Setup**. Updates are offered
inside the plugin; `install.sh` can always be re-run.

## How it works

```
game → PipeWire → [Ally DSP smart filter: convolver → LSP PEQ → LSP multiband compressor → LSP limiter] → speaker sink → ALC294 → 2× TAS2781 → speakers
```

- The chain runs in its own `pipewire -c` process (`~/.config/systemd/user/ally-dsp.service`),
  the same pattern Valve uses for the Steam Deck microphone filter.
- The three LSP LV2 plugins are bundled in `bin/lv2` (LGPL-3, see
  `THIRD_PARTY_LICENSES.md`); `LV2_PATH` points the process at them.
- Preset switch = restart of that process with another configuration (well under a second).
- Runtime data lives in `~/homebrew/data/Ally DSP` (tuning XML, venv, presets),
  settings in `~/homebrew/settings/Ally DSP/settings.json`.

## Command line

The backend doubles as a CLI for support cases (run as the `deck` user):

```bash
cd ~/homebrew/plugins/"Ally DSP" && PYTHONPATH=py_modules python3 -m allydsp.cli doctor
PYTHONPATH=py_modules python3 -m allydsp.cli setup          # full setup, prints progress
PYTHONPATH=py_modules python3 -m allydsp.cli apply movie warm --save
PYTHONPATH=py_modules python3 -m allydsp.cli status
```

## Development

```bash
pnpm install && pnpm build          # frontend
python3 -m pytest tests -q          # backend (3.9+)
scripts/assemble-converter.sh       # copy converter from the submodule
scripts/fetch-lsp.sh                # bundle the LV2 plugins
scripts/dev-deploy.sh deck@<ip>     # copy to the handheld and restart Decky
```

Releases: tag `vX.Y.Z` (matching `package.json`); GitHub Actions builds, tests,
packages `ally-dsp-X.Y.Z.zip`, signs `SHA256SUMS` with the `MINISIGN_SEED` secret
and publishes the release. See `docs/` for the research and the implementation plan.

## License

MIT for this project. Third-party components and the reason the Dolby tuning is
never redistributed are listed in `THIRD_PARTY_LICENSES.md`.

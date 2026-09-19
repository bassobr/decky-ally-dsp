# Changelog

## 0.1.1 (2026-09-19)

- Remove the Custom 1–3 presets (Dolby's neutral personalize profiles).
- English-only UI.
- Await background tasks on unload.

## 0.1.0 (2026-09-19)

First release.

- Setup wizard: hardware check, ASUS "Dolby Atmos driver" download with SHA-256
  verification, DAX3 tuning extraction, converter venv, conversion of all
  profiles, activation.
- PipeWire filter chain (convolver, LSP parametric EQ, multiband compressor,
  autogain, limiter) as WirePlumber smart filter in a systemd user unit.
- Presets Game/Dynamic/Movie/Music/Voice × Balanced/Detailed/Warm, global or
  per game; headphone pause; extras (leveler, dialog, regulator, pre-gain).
- Diagnostics page and text report.
- Signed self-update from GitHub Releases, installed via Decky Loader.

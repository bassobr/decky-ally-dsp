# Changelog

## 0.1.0 (2026-09-19)

First release.

- Setup wizard: hardware check, ASUS "Dolby Atmos driver" download with SHA-256
  verification, DAX3 tuning extraction for the device's codec, private converter
  venv, conversion of all Dolby profiles, activation.
- PipeWire filter chain (convolver, LSP parametric EQ, multiband compressor,
  autogain, limiter) as WirePlumber smart filter in its own systemd user unit.
- Presets Game/Dynamic/Movie/Music/Voice/Custom 1–3 × Balanced/Detailed/Warm,
  global or per game; headphone pause; extras (leveler, dialog, regulator, pre-gain).
- Diagnostics page and text report.
- Signed self-update from GitHub Releases, installation via Decky Loader.

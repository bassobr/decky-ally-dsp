# Security Policy

Ally DSP runs **without root** inside Decky Loader (`"flags": []`). It writes
only below the user's home directory (`~/homebrew/{settings,data}/Ally DSP`,
`~/.config/systemd/user/ally-dsp.service`) and starts one additional PipeWire
process in the user session. It never modifies the SteamOS root filesystem.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting:

https://github.com/bassobr/decky-ally-dsp/security/advisories/new

Do not open public issues for security problems. This is a solo-maintained
project; reports are handled on a best-effort basis.

## Supported versions

Only the latest release receives fixes. The in-app updater moves installations
forward; older versions can be reinstalled with `install.sh`.

## Release integrity

- Releases are built by GitHub Actions from a tag and ship `SHA256SUMS` plus a
  minisign-compatible signature `SHA256SUMS.minisig`.
- The updater verifies the signature against the public key pinned in the
  plugin (`minisign.pub`) before trusting any checksum, then hands the zip URL
  and its SHA-256 to Decky Loader, which downloads the zip and rejects it on a
  checksum mismatch. Unsigned releases are refused.
- Manual check: `minisign -Vm SHA256SUMS -p minisign.pub`.
- Limits: the signing seed lives in a GitHub Actions secret, so a full account
  takeover could still produce valid signatures. minisign has no revocation;
  a compromised key requires an out-of-band key rotation and a reinstall.

## Downloaded third-party content

Setup downloads ASUS' public "Dolby Atmos driver" package over HTTPS and checks
it against the SHA-256 published by the ASUS support API (or the pinned
fallback hash) before extracting anything.

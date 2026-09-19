# Research notes: speaker sound on the ROG Xbox Ally X under SteamOS

Findings from September 2026 that led to Ally DSP. Verified on a ROG Xbox Ally X
(RC73XA) running SteamOS 3.8.16 (build 20260716.1, kernel 6.16.12-valve24.5).

## Why Windows sounds better

Two layers shape the speaker output on Windows:

1. **Amplifier DSP.** Two TI TAS2781 smart amps run a firmware with the ASUS
   tuning and speaker protection (`TAS2XXX13840.bin`, configuration
   `RC73_Veco_ISLR100_Tuning Mode`). Linux loads the same firmware once the
   Realtek codec is bound to the amps; the file is byte-identical to the one in
   ASUS' Windows "TI Smart Amplifier Driver" package.
2. **Host DSP.** Dolby Atmos runs as an audio processing object with a
   per-device tuning: speaker correction FIR/PEQ, intelligent EQ voicings
   (Balanced/Detailed/Warm), multiband compressor, regulator, limiter, dialog
   enhancer, volume leveler, virtualizer.

SteamOS has layer 1 (with the kernel caveats below) and no layer 2 at all:
Valve's `steamdeck-dsp` ships PipeWire hardware profiles only for
`valve-jupiter`, `valve-galileo` and `valve-fremont`; every other device gets
the `default` profile with just the microphone noise-suppression chain.

## Device facts

| Item | Value |
|---|---|
| DMI | `ASUSTeK COMPUTER INC.` / `ROG Xbox Ally X RC73XA_RC73XA` |
| Codec | Realtek ALC294, vendor `0x10ec0294`, subsystem `0x10431384` (RC73YA: `0x10431394`) |
| Amps | 2× TAS2781 over I2C, ACPI `TXNW2781`; ALSA controls `Speaker Program/Config/Profile Id`, `Speaker Analog Gain`, `Speaker Force Firmware Load` |
| Sink | `alsa_output.pci-0000_64_00.6.analog-stereo`; speakers and the 3.5 mm jack are routes of the same sink |
| PipeWire | 1.6.4 (Valve build with lilv, libmysofa, libebur128), WirePlumber 0.5.14, 48 kHz, quantum 512 |
| Filters present | Valve's mic chain in a separate `filter-chain.service`; WirePlumber loopback smart filters (`node.create-loopback`) on sink and source |
| Tools on SteamOS | Python 3.13 with venv, git, zstd, 7z, curl, lv2ls/lv2info |

## Kernel timeline for the TAS2781 on the Xbox Ally

| Patch | Effect | Mainline / stable |
|---|---|---|
| `ALSA: hda/realtek: Add match for ASUS Xbox Ally projects` (Oct 2025) | Binds the codec to the amps; "increases the output volume significantly" | 6.18, 6.17.13 |
| `hda/tas2781: fix speaker id retrieval for multiple probes` | Second amp probes correctly | 6.18, 6.17.13 |
| `Skip UEFI calibration on ASUS ROG Xbox Ally X` (Jan 2026) | Fixes distortion and dropouts above ~70 % volume | 6.19, 6.18.7 |
| TI calibration pre-processing (Feb 2026) | Replaces the skip quirk | 7.0 |

Valve's 6.16 kernel in SteamOS 3.8.16 contains the codec binding (dmesg:
`ALC294: picked fixup for PCI SSID 1043:1384`, `bound i2c-TXNW2781:00`,
`Instantiated 2 I2C devices`). Whether the calibration fix is included is
unknown; test at high volume.

## Getting the Dolby tuning without Windows

The ASUS support API lists a "Dolby Atmos driver" package with a SHA-256:

```
https://www.asus.com/support/webapi/ProductV2/GetPDDrivers?website=us&model=rog+xbox+ally+x+%EF%BC%882025%EF%BC%89+rc73xa&pdhashedid=&osid=52
```

`DolbyAtmosdriverforConsumer_ASUS_Z_V11.130.1340.46_17507.exe` (10.3 MB) is an
Inno Setup installer with a 7z archive at offset 4285120. It contains
`dax3_ext_rtk.inf` and 49 tuning files, among them
`DEV_0294_SUBSYS_10431384_PCI_SUBSYS_13841043.xml` (Xbox Ally X) and the
RC73YA variant. 7z reads the `.exe` only as a PE file, so the archive has to be
sliced out at the signature offset first:

```bash
python3 -c "d=open('pkg.exe','rb').read(); o=d.find(b'7z\xbc\xaf\x27\x1c'); open('payload.7z','wb').write(d[o:])"
7z e -r -odax3 payload.7z DEV_0294_SUBSYS_10431384_PCI_SUBSYS_13841043.xml dax3_ext_rtk.inf
```

The Microsoft Update Catalog does not help: searching the hardware id returns
only the Realtek codec driver without DAX3 files. The Realtek package on the ASUS
site (`Audio_DriverOnly_Dolby_ROG_Realtek_*.exe`) contains wrapper INFs but no
tuning XML either.

The XML (DAX3 3.7.1, tuning version 11, 2025-02-06) has one `internal_speaker`
endpoint with the profiles dynamic, movie, music, game, voice,
voice_onlinecourse, personalize_user1–3 and off. Each profile carries a
`tuning-cp` block (IEQ, dialog enhancer, leveler, virtualizer, bass, regulator)
and a `tuning-vlldp` block (speaker PEQ, filter coefficients, multiband
compressor, regulator, sliding bass, noise gate). The volume leveler is off in
this tuning. The personalize profiles are Dolby's neutral base for user EQ and
are not offered by the plugin.

## Converter

[speaker-tuning-to-easyeffects](https://github.com/antoinecellerier/speaker-tuning-to-easyeffects)
(MIT) converts DAX3 XMLs into EasyEffects presets or a PipeWire filter chain.
For this device the chain is: convolver (minimum-phase FIR) → LSP parametric EQ
(dialog) → LSP multiband compressor (regulator) → LSP autogain (leveler, when
enabled) → LSP limiter. It needs Python 3.10+, numpy/scipy and the LSP LV2
plugins; SteamOS has neither, so Ally DSP runs it in a private venv and bundles
the LV2 plugins. Virtual bass would additionally need Calf and is not offered.

## Existing work considered

- **DeckSP / AudioForge**: JamesDSP as flatpak with a virtual sink; heavy, no
  Dolby tuning, no multiband compressor.
- **Decky Virtual Surround Sound**: filter chain loaded with `pw-cli` from a
  user systemd unit; the basis for our runtime approach.
- **Bazzite**: convolver hardware profile for the first ROG Ally (RC71L),
  nothing for the RC73XA.
- **Valve `steamdeck-dsp`**: Faust-built LV2 for the Deck speakers, smart
  filters for the mic; the pattern Ally DSP follows for its own PipeWire process.

## Smart filters

A filter chain with `filter.smart = true` and `filter.smart.target = { node.name = <sink> }`
is inserted by WirePlumber between clients and the sink. Steam keeps seeing the
real sink, volume keys work, and the chain is limited to the speaker sink. On the
Ally X the resulting graph is
`app → alsa_loopback_stream → effect_input.ally_dsp → effect_output.ally_dsp → alsa_output`.

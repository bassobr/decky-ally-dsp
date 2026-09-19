# Recherche & Ideensammlung: Besserer Lautsprecherklang auf dem ROG Xbox Ally X unter SteamOS 3.8.x

Stand: 19.09.2026. Ausgangsfrage: Der Sound der eingebauten Lautsprecher ist unter SteamOS deutlich schlechter als unter Windows mit Dolby Atmos. Lässt sich das mit einem Decky-Plugin lösen?

---

## 0. Kurzfazit

**Ja, zu einem großen Teil.** Der Klangunterschied entsteht auf zwei Ebenen, und ein Decky-Plugin kann nur eine davon adressieren:

| Ebene | Was Windows macht | Was SteamOS 3.8 macht | Per Decky-Plugin lösbar? |
|---|---|---|---|
| **A. Verstärker-DSP** (2× TI TAS2781 Smart Amp, Firmware mit ASUS-Tuning + Lautsprecherschutz) | Treiber lädt Firmware, Kalibrierung, volle Lautstärke | Hängt vom Kernel ab. Für das Xbox Ally X kamen die Fixes erst in Kernel 6.17.13 / 6.18 / 6.19 / 7.x | **Nein** (Kernel/Firmware). Plugin kann nur diagnostizieren und ggf. Amp-Profil per `amixer` umschalten |
| **B. Host-DSP** (Dolby Atmos APO: Lautsprecher-EQ, Multiband-Kompressor, Limiter, Virtualizer, Volume Leveler, Dialog-Enhancer) | Aktiv, ASUS-getunt | **Nicht vorhanden.** Valves DSP-Paket `steamdeck-dsp` 0.99 enthält nur Profile für Valve-Hardware (jupiter, galileo, fremont), das Ally läuft auf dem `default`-Profil ohne jede Klangbearbeitung | **Ja.** PipeWire 1.6.8 in SteamOS bringt alles mit: Filter-Chain mit param_eq, Convolver, LV2-Support (lilv), WirePlumber-Smart-Filter |

Der vielversprechendste Weg: Ein Decky-Plugin, das eine **PipeWire-Filter-Chain als WirePlumber-Smart-Filter** vor den Lautsprecher-Sink hängt (ohne Root, ohne Änderungen am Read-only-Rootfs, update-sicher in `~/.config` bzw. `~/homebrew`). Als Tuning-Quelle bietet sich das **Original-Dolby-Tuning aus dem Windows-Treiber (DAX3-XML)** an, für das bereits ein Konverter nach PipeWire-Filter-Chain existiert (`speaker-tuning-to-easyeffects`). Die XML ist ohne Windows aus dem ASUS-Download extrahierbar (Abschnitt 10).

Wichtigste Vorbedingung: **Erst Ebene A prüfen.** Wenn der TAS2781-Treiber auf dem konkreten SteamOS-Build den Codec nicht bindet oder die Kalibrierung fehlschlägt (leise, verzerrt ab ~70 %, rechter Kanal stumm), hilft kein Software-DSP. Diagnosebefehle in Abschnitt 8.

---

## 1. Problemanalyse: Warum klingt Windows besser?

### 1.1 Schichtenmodell der Audiokette

```
Spiel/Anwendung
   │
   ▼
Host-DSP  ── Windows: Dolby Atmos APO (Speaker-EQ, IEQ-Voicing, Multiband-Kompressor,
   │         Regulator/Limiter, Surround-Virtualizer, Volume Leveler, Dialogue Enhancer)
   │      ── SteamOS: nichts (default-Profil von steamdeck-dsp, roher ALSA-Ausgang)
   ▼
HDA-Codec Realtek ALC294 (per I2C an die Amps gekoppelt)
   │
   ▼
2× TI TAS2781 Smart Amp mit eigener DSP-Firmware
   │    (Tuning + Speaker Protection; Firmware TAS2XXX13840.bin, Konfiguration
   │     "RC73_Veco_ISLR100_Tuning Mode", Kalibrierdaten aus UEFI-Variable CALI_DATA)
   ▼
2 Lautsprecher
```

### 1.2 Was Dolby Atmos für eingebaute Lautsprecher konkret tut

Laut Dolby-Dokumentation und der Analyse der DAX3-Tuning-Dateien (Konverter-Projekt, siehe 4.6) besteht ein OEM-Speaker-Tuning aus:

- **Lautsprecherkorrektur**: FIR/Convolver (Minimalphasen-Impulsantwort) und parametrischer EQ, kompensiert den Frequenzgang der kleinen Treiber
- **Intelligent Equalizer (IEQ)**: Voicing-Presets Balanced / Detailed / Warm
- **Multiband-Kompressor** (1–4 Bänder) und **Regulator** (Per-Band-Limiter, schützt vor Übersteuerung)
- **Brickwall-Limiter** am Ende
- **Bass Enhancement** (psychoakustisch, Harmonische)
- **Dialogue Enhancer** (Sprachband um 2,5 kHz)
- **Volume Leveler** (inhaltsabhängige Lautheitsregelung, proprietär)
- **Surround Virtualizer** (Crosstalk-basierte Verbreiterung für Stereolautsprecher)

Der Windows-Treiber wählt ein Preset (Dynamic/Game/Movie/Music/Voice). Auf dem ROG Ally X empfehlen Nutzer sogar, das ASUS-Default-Preset auf "Custom 1" zu ändern, weil das Default "muted and tinny" klingt. Das zeigt: Ein Großteil der "Klangqualität" ist reines Tuning, kein Hardware-Vorteil.

### 1.3 Wo SteamOS heute steht

- **Kein Host-DSP** für Fremdgeräte. Verifiziert im entpackten Paket `steamdeck-dsp-0.99` aus dem SteamOS-3.8-Repo: Hardware-Profile existieren nur für `valve-jupiter`, `valve-galileo`, `valve-fremont` und `default`. Das Skript `pipewire-hwconfig` liest den DMI-Namen (`sys_vendor` + `product_name`, kleingeschrieben) und kopiert das passende Profil beim Boot nach `/run/pipewire`. Für "asustek computer inc.-rog xbox ally x rc73xa…" gibt es keins.
- **Kernel-Stand ist der kritische Punkt**, siehe Abschnitt 2.2.

---

## 2. Hardware- und Kernel-Fakten zum ROG Xbox Ally X (RC73XA)

### 2.1 Hardware

| Komponente | Wert | Quelle |
|---|---|---|
| Modell | RC73XA (Xbox Ally X), RC73YA (Xbox Ally) | ASUS Spec, Kernel-Quirk |
| APU | AMD Ryzen AI Z2 Extreme, 24 GB LPDDR5X | ASUS Spec |
| Audio laut ASUS | "2-speaker system with Smart Amplifier Technology", Dolby Atmos, Hi-Res (Kopfhörer), Array-Mikro, AI Noise Cancelling | ASUS Spec |
| HDA-Codec | Realtek **ALC294**, Vendor-ID 0x10ec0294. Der zugehörige Kernel-Quirk heißt `ALC287_FIXUP_TXNW2781_I2C`, greift laut dmesg aber für den ALC294 des RC73XA | Gerätediagnose 19.09.2026, Kernel-Commit 18a4895 |
| PCI-Subsystem-ID | `0x1043:0x1384` (RC73XA), `0x1043:0x1394` (RC73YA) | Kernel-Commit 18a4895 |
| Verstärker | 2× Texas Instruments **TAS2781** (I2C, HDA-Side-Codec `snd_hda_scodec_tas2781_i2c`) | LKML-Bugthread Dez 2025 |
| Amp-Firmware | `TAS2XXX13840.bin` (Default, entspricht Windows), Alternative `TAS2XXX13841.bin` | LKML-Bugthread |
| Firmware-Inhalt | Konfiguration 0 "configuration_RC73_Veco_ISLR100_Tuning Mode_48 KHz" (Tuning + Schutz), Konfiguration 1 "calibration_Tuning Mode" (nur für Kalibrierung gedacht) | LKML-Bugthread |
| ALSA-Mixer-Controls des TAS2781-Treibers | `Speaker Analog Volume`, `Speaker Program Id`, `Speaker Config Id`, `Speaker Profile Id`, `Speaker Force Firmware Load` | Kernel-Doku/Threads |

### 2.2 Zeitleiste der Kernel-Fixes (alle nach dem Mainline-Stand von Kernel 6.16!)

| Datum | Patch | Wirkung | Landete in |
|---|---|---|---|
| Okt 2025 (A. Kapenekakis / Bazzite) | "ALSA: hda/realtek: Add match for ASUS Xbox Ally projects" | Codec wird an TAS2781-Amps gebunden, DSP-Firmware wird geladen. Zitat: "While these projects work without a quirk, adding it **increases the output volume significantly**" | 6.18, Backport 6.17.13 |
| Okt 2025 | "hda/tas2781: fix speaker id retrieval for multiple probes" | Ohne Fix scheitert der zweite Amp beim Probe (Xbox Ally X hat zwei) → ein Kanal stumm | 6.18, Backport 6.17.13 |
| 08.01.2026 (M. Schwartz) | "Skip UEFI calibration on ASUS ROG Xbox Ally X" | Beseitigt Verzerrung/Aussetzer ab ~70 % Lautstärke (UEFI-Kalibrierdaten überschrieben Firmware-Kalibrierung) | 6.19, Backport 6.18.7 |
| 28.02.2026 (TI, Baojun Xu) | "A workaround solution to lower-vol issue among lower calibrated-impedance micro-speaker on TAS2781" | Revertiert den Skip-Quirk, korrekte Kalibrier-Vorverarbeitung (`tas2781_cali_preproc`, SineGainI-Neuberechnung) für 0x10431384 | ~7.0/7.1 |
| 2026 | `ALC287_FIXUP_TXNW2781_I2C_ASUS` | Kopfhörerbuchse RC73XA/RC73YA | 6.18.x Stable |

### 2.3 Was das für SteamOS 3.8.x bedeutet

| SteamOS | Kernel (aus Valve-Repo `jupiter-3.8`) | Erwarteter Amp-Status |
|---|---|---|
| 3.8.10–3.8.16 **Stable** | linux-neptune-616 (am Gerät: 6.16.12-valve24.5) | **Am Gerät verifiziert:** Der Codec-Binding-Quirk ist enthalten (dmesg: „ALC294: picked fixup for PCI SSID 1043:1384“, „bound i2c-TXNW2781:00-tas2781-hda.0“, „Instantiated 2 I2C devices“). Ob der Fix für die UEFI-Kalibrierdaten enthalten ist, bleibt offen (Hörtest: Verzerrung/Aussetzer oberhalb ~70 % Lautstärke). SteamOS-Issues #2248/#2289 zeigen, dass ältere Builds unvollständig waren |
| 3.8.2x **Beta** | linux-neptune-618 (6.18.42–6.18.50) | Enthält Codec-Binding, Speaker-ID-Fix und Skip-UEFI-Quirk (ab 6.18.7) |
| 3.9 **Preview** | linux-neptune-72 (7.2) | Enthält alles inkl. TI-Endfix |

Bekannte Symptome aus Bazzite/SteamOS-Issues: Lautstärke deutlich niedriger als Windows, Verzerrung ab 70 %, rechter Kanal stumm, L/R-"Echo"/Glitching nach Firmware-Updates (Bazzite #3372, #4366, #1481, SteamOS #2248, #2289).

**Konsequenz:** Bevor ein Host-DSP Sinn macht, muss auf dem Gerät geprüft werden, ob der TAS2781-Treiber gebunden ist und die Firmware sauber lädt (Abschnitt 8). Ein Decky-Plugin kann das als "Gesundheitscheck" anzeigen, aber nicht reparieren.

---

## 3. Audio-Stack von SteamOS 3.8.x (verifiziert aus dem Paket-Repo)

| Paket | Version | Relevanz |
|---|---|---|
| `pipewire` (Valve-Build) | **1:1.6.8-1.101** im Repo, am Gerät mit 3.8.16 läuft 1:1.6.4-1.6 | Filter-Graph mit allen Builtins bis 1.6; Valve-Build hängt von `lilv` (LV2), `libmysofa` (SOFA), `libebur128`, `fftw`, `libsndfile` ab → **LV2-, SOFA- und EBUR128-Plugins sind kompiliert** |
| `wireplumber` | **0.5.14** | Smart-Filter-Policy verfügbar (`filter.smart`) |
| `steamdeck-dsp` | 0.99 im Repo, 0.96 am Gerät | Nur Valve-Profile; liefert aber `valve_deck_speakers.lv2` (Faust-generiert, GPL-3.0) als Architekturvorbild und zeigt Valves Smart-Filter-Verwendung |
| PipeWire-Default-Profil | 48 kHz, quantum 512 (min 256, max 8192) | Latenzbudget: 10,7 ms pro Puffer |
| Kernel | 6.16 (stable) / 6.18 (beta) / 7.2 (3.9 preview) | siehe 2.3 |
| Im Arch-Spiegel `extra-3.8` vorhanden, aber **nicht** installiert | `lsp-plugins-lv2` 1.2.22, `calf` 0.90.8, `zam-plugins`, `x42-plugins`, `easyeffects` 7.2.5, `ladspa`, `rnnoise` | Read-only-Rootfs: nicht per pacman nutzbar, aber als LV2-Bundle im Plugin bündelbar (LSP: LGPL-3) |

### 3.1 Builtin-Filter der Filter-Chain in PipeWire 1.6.8 (aus dem Quellcode)

`mixer copy bq_lowpass bq_highpass bq_bandpass bq_lowshelf bq_highshelf bq_peaking bq_notch bq_allpass bq_raw param_eq convolver delay invert clamp linear recip abs sqrt exp log mult sine max dcblock ramp debug zeroramp noisegate busy null` plus separate Plugins `ladspa`, `lv2`, `sofa`, `ebur128`, `ffmpeg`.

- **param_eq**: liest EqualizerAPO/AutoEq-Textdateien (`Preamp: -6.8 dB`, `Filter 1: ON PK Fc 1000 Hz Gain 3.5 dB Q 0.7`; Typen PK, LSC, HSC), bis zu 8 Kanäle (Ports `In 1..8`, `Out 1..8`), pro Kanal eigene Datei möglich (`filename1..8`). Praktisch latenzfrei.
- **convolver**: Impulsantworten aus WAV (mehrere Samplerates wählbar), FFT-partitioniert, blocksize 64–256, Latenz einstellbar. Genau das nutzt Bazzite für das erste ROG Ally (RC71L).
- **ladspa**: Absoluter Pfad zur `.so` erlaubt (Quellcode: `path[0] == '/'`), also aus dem Plugin-Verzeichnis ladbar.
- **lv2**: Wird über `lilv_world_load_all()` gefunden → `LV2_PATH` bzw. Standardpfade inkl. `~/.lv2`. Ein Decky-Plugin kann LV2-Bundles nach `~/.lv2/` legen (kein Root).
- **ebur128**: Lautheitsmessung mit Control-Ausgängen (Momentary/Shortterm/Global LUFS, True Peak) → Basis für einen simplen Volume Leveler. `lufs2gain` ist in 1.6.8 noch **nicht** enthalten (erst in neuerer Doku), Gain-Mapping müsste über `log`/`linear`/`clamp`-Bausteine oder ein LV2-Plugin erfolgen.
- **sofa**: HRTF-Spatializer (für Kopfhörer-Virtualisierung, nicht für Lautsprecher).

### 3.2 WirePlumber Smart Filter (der entscheidende Mechanismus)

Ein Filter-Chain-Knoten mit `filter.smart = true` wird von WirePlumber **automatisch und transparent** zwischen alle Streams und den Ziel-Sink gehängt. Vorteile gegenüber einem klassischen virtuellen Sink:

- Steam sieht weiterhin den echten Lautsprecher als Standardgerät → Lautstärketasten, Mute und Geräteauswahl im Gaming-Modus funktionieren unverändert.
- Umgeht das bekannte Problem, dass Steam im Gaming-Modus virtuelle Sinks nicht zuverlässig als Ausgabegerät anbietet/speichert (Steam-Forum zum Deck OLED; Valve hat den "Virtual Sink" in 3.7 sogar aus dem Desktop-Modus entfernt).
- `filter.smart.target = { … }` begrenzt den Filter auf den Lautsprecher-Sink; Bluetooth/USB/HDMI bleiben unbearbeitet.
- Valve selbst nutzt genau das für die Deck-Mikrofonkette (`filter.smart.target = { media.class = Audio/Source, alsa.card_name = acp5x }`) und blendet interne Knoten über `stream.rules` aus.

---

## 4. Was existiert bereits?

| Projekt | Ansatz | Für uns relevant |
|---|---|---|
| **DeckSP** (jessebofill, im Decky-Store) / **AudioForge** (neoseek, Fork) | Installiert JamesDSP als Flatpak (AudioForge: gepatchtes Flatpak gegen Loopback-Feedback), virtueller Sink, QAM-UI mit 15-Band-EQ, Compander, Convolver, Dynamic Bass, Stereo/Crossfeed, Tube, Reverb, Limiter, **Profile pro Spiel**. GPL-3 | Schnellster Weg zu "irgendeinem" DSP. Aber: schwergewichtig (Flatpak-Runtime), virtueller Sink statt Smart Filter, kein Ally-X-Tuning enthalten, JamesDSP-eigene Effektpalette ohne Multiband-Kompressor |
| **Decky Virtual Surround Sound** (DeckSettings/Josh.5, im Store) | Reine PipeWire-Filter-Chain (Convolver mit HRIR), geladen über `pw-cli -m load-module` aus einem **systemd-User-Service**, kein Root, kein Neustart von PipeWire, Presets als WAV in `~/.config/pipewire` | **Beste Architektur-Vorlage** für Laden/Entladen/Autostart einer Filter-Chain aus einem Decky-Plugin heraus (`defaults/service.sh`, ~940 Zeilen Bash) |
| **Volume Boost** (Store) | Sink-Lautstärke bis 150 % | Zeigt Bedarf nach mehr Pegel; ohne Limiter riskant |
| **Bazzite Hardware-Profil für ROG Ally RC71L** | `hardware-profiles/asustek computer inc.-rog ally rc71l_rc71l/pipewire.conf.d/filter-chain.conf`: zwei Builtin-Convolver (L/R) mit `game.wav`, `Audio/Sink` mit `node.target` auf den ALSA-Sink | Beweist, dass Valves hwconfig-Mechanik für Fremdgeräte funktioniert. Bazzite hat Profile für RC71L, GPD (G1617/G1618) und Lenovo 83E1 (Legion Go S), **keins für RC73XA** → Lücke, die unser Tuning später upstream füllen könnte |
| **speaker-tuning-to-easyeffects** (antoinecellerier, MIT) | Konvertiert **Dolby-DAX3-Tuning-XML aus dem Windows-Treiber** (`C:\Windows\System32\DriverStore\FileRepository\dax3_ext_*.inf_*\DEV_*_SUBSYS_*.xml`) in EasyEffects-Presets **oder direkt in eine PipeWire-Filter-Chain** (`dolby_to_pipewire.py`, nutzt Smart-Filter-Routing). Übernimmt Convolver (Minimalphasen-FIR), PEQ, Multiband-Kompressor, Regulator, Limiter, Dialog-EQ, Bass Enhancer, Autogain; benötigt LSP- und Calf-LV2-Plugins. Nicht abbildbar: inhaltsabhängiger Volume Leveler, 4-Kanal-Upmix. Getestet auf ~40 Geräten (ASUS TUF/Zenbook, Lenovo, Framework), Realtek ALC287 explizit unterstützt | **Größter Hebel für Authentizität**: das echte ASUS/Dolby-Tuning des Xbox Ally X statt Gehör-EQ. Die passende XML heißt `DEV_0294_SUBSYS_10431384_PCI_SUBSYS_13841043.xml` und steckt im öffentlichen ASUS-Download „Dolby Atmos driver“; ohne Windows extrahierbar (verifiziert, Abschnitt 10) |
| **EasyEffects** (Flatpak) | Vollwertiger GUI-DSP, Presets JSON | Im Gaming-Modus ohne GUI nutzbar (`--load-preset`), aber schwergewichtig; auf dem Deck Berichte über Knacken/Popping |
| **Valve `valve_deck_speakers.lv2`** | Faust-DSP → LV2 (nur 2 Audio-Ein/Ausgänge, keine Control-Ports, Steam-Deck-spezifisch, GPL-3) | Vorbild: eigenes Ally-X-Tuning in **Faust** schreiben und mit `faust2lv2` bauen → ein einziges, schlankes, latenzarmes LV2-Bundle ohne LSP/Calf-Abhängigkeiten |
| **Decky-Plugin-Rahmen** | Python-Backend (`main.py`, `decky`-Modul), Frontend React/TS im QAM, `bin/` für Binaries (CI-Build via Docker), Umgebungsvariablen `DECKY_PLUGIN_DIR`, `DECKY_PLUGIN_SETTINGS_DIR`, `DECKY_PLUGIN_RUNTIME_DIR`, `DECKY_USER_HOME`. Backend läuft als Deck-User; Root nur mit `"flags": ["root"]` in `plugin.json` | Alles Nötige (systemd --user, pw-cli, wpctl, amixer) geht **ohne Root** |

---

## 5. Antwort auf die Kernfrage

**Ein Decky-Plugin kann:**

1. Eine Lautsprecher-DSP-Kette (EQ, Convolver, Multiband-Kompressor, Limiter, Bass-Enhancement, Dialog-EQ, einfache Lautheitsregelung, milde Stereoverbreiterung) als Smart Filter vor den Lautsprecher-Sink hängen, im QAM ein-/ausschalten, Presets wechseln, Parameter live ändern.
2. Das Original-Dolby-Tuning aus Windows importieren (DAX3-XML) und in diese Kette übersetzen.
3. Presets pro Spiel anwenden, Kopfhörer erkennen und den Filter dann deaktivieren.
4. Den Zustand von Ebene A anzeigen (Kernel, TAS2781 gebunden, Firmware, aktives Amp-Profil) und ggf. per `amixer` das Amp-Profil/Programm umschalten.

**Ein Decky-Plugin kann nicht:**

1. Fehlende Kernel-Patches ersetzen (leise Ausgabe ohne Codec-Binding, stummer Kanal, Verzerrung ab 70 %).
2. Dolbys proprietäre, inhaltsabhängige Algorithmen (Volume Leveler mit Inhaltsanalyse, Virtualizer-Details) exakt nachbilden. Ein LUFS-basierter Leveler und eine M/S-Verbreiterung sind Näherungen.
3. Den Steam-Client ändern (z. B. eigene Einträge in den Steam-Audioeinstellungen).

---

## 6. Lösungsoptionen im Vergleich

| Option | Beschreibung | Aufwand | Klangpotenzial | Risiken |
|---|---|---|---|---|
| **A. Eigene Filter-Chain als Smart Filter** (empfohlen) | Decky-Plugin lädt `libpipewire-module-filter-chain` (Builtins + gebündelte LV2) via systemd-User-Unit; UI im QAM | mittel | hoch (mit gutem Tuning) | LV2-Ladepfad im PipeWire-Prozess, Kopfhörer-Erkennung, Preset-Qualität |
| **B. DAX3-Import** (Ergänzung zu A) | `speaker-tuning-to-easyeffects` als Python-Modul im Backend; Nutzer liefert XML (Windows-Partition mounten oder Datei kopieren) oder Plugin liefert vorkonvertierte Presets mit | mittel | sehr hoch (ASUS-Originaltuning) | Rechtliches: XML nicht mitliefern, nur Konverter + eigene Messpresets; LSP/Calf-Bundles nötig |
| **C. DeckSP/AudioForge-Fork mit Ally-X-Preset** | Bestehendes JamesDSP-Plugin, nur Preset + Gerätelogik ergänzen | gering | mittel | Flatpak-Abhängigkeit, kein Multiband, virtueller Sink statt Smart Filter, Wartung fremder Codebasis |
| **D. EasyEffects-Frontend** | Plugin steuert EasyEffects-Flatpak (Preset laden, Autostart) | gering–mittel | hoch | Schwergewichtig, Stabilitätsberichte, kein echtes Gaming-Modus-UI |
| **E. Nur Amp-Ebene** | Diagnose + `amixer`-Umschaltung von Program/Config/Profile, Firmware-Hinweise | gering | begrenzt | Kann Kernel-Bugs nicht lösen; Fehlkonfiguration kann Lautsprecher-Schutz umgehen |
| **F. Upstream-Beitrag** | Fertiges Tuning als `hardware-profile` an Bazzite und Valve (`steamdeck-dsp`) einreichen | gering (nach A/B) | hoch für alle Nutzer | Abhängig von Maintainer-Akzeptanz |

Empfehlung: **A als Basis, B als Tuning-Quelle, E als Diagnose-Tab, F als Langfristziel.**

---

## 7. Empfohlene Architektur (Option A + B) im Detail

### 7.1 Komponenten

```
decky-ally-dsp/
├── plugin.json            # flags: [] (kein Root nötig)
├── main.py                # Backend: Systemd-Unit verwalten, Presets schreiben, Diagnose, pw-cli/wpctl/amixer
├── src/                   # Frontend (QAM): Ein/Aus, Preset, Bänder, Diagnose-Tab
├── defaults/
│   ├── service.sh         # lädt/entlädt Filter-Chain via pw-cli (Vorbild: decky-virtual-surround-sound)
│   ├── presets/           # AutoEq-Textdateien (param_eq) + IR-WAVs + LV2-Control-Werte, z. B. game/movie/music/voice
│   └── lv2/               # gebündelte LV2-Bundles (LSP mb_compressor, limiter; optional eigenes Faust-Plugin)
└── bin/                   # optional: dolby_to_pipewire-Konverter, faust-generiertes LV2
```

- **Laufzeit:** `~/.config/systemd/user/ally-dsp.service` → `service.sh` → `pw-cli -m load-module libpipewire-module-filter-chain '{…}'` (Modul lebt so lange wie der pw-cli-Prozess; Entladen = Prozess beenden). Kein PipeWire-Neustart, keine Steam-Unterbrechung.
- **Persistenz:** Presets und generierte Konfiguration unter `DECKY_PLUGIN_SETTINGS_DIR`; LV2-Bundles per Symlink nach `~/.lv2/` (PipeWire findet sie über lilv-Standardpfade). Alles in `/home`, überlebt SteamOS-Updates.
- **Live-Parameter:** Control-Ports der Filter-Chain sind per `pw-cli set-param <node> Props '{ params = [ "lim:th" -3.0 ] }'` zur Laufzeit änderbar. `param_eq` liest seine Datei nur beim Laden → bei EQ-Änderungen Modul neu laden (kurze Lücke) oder für Live-Slider `bq_peaking`-Knoten mit Control-Ports nutzen.

### 7.2 Filter-Graph (Entwurf, ungetestet)

```
Eingang L/R
  → convolver (Minimalphasen-IR pro Kanal; Lautsprecherkorrektur aus DAX3 oder Messung)
  → param_eq (Voicing/IEQ-Preset, AutoEq-Format, beide Kanäle)
  → [optional] Dialog-EQ (bq_peaking ~2,5 kHz, live schaltbar)
  → LV2 LSP Multiband-Kompressor stereo (3–4 Bänder, entspricht Dolby MBC + Regulator)
  → [optional] Bass Enhancement (Calf Bass Enhancer LV2) oder Lowshelf + Kompressor-Band
  → LV2 LSP Limiter stereo (Brickwall, Lookahead ~5 ms)
  → Ausgang L/R  → Smart-Filter-Ziel: ALSA-Lautsprecher-Sink
```

Skizze der Modulkonfiguration (Port-Namen der LV2-Plugins mit `lv2info` verifizieren):

```
{ name = libpipewire-module-filter-chain
  args = {
    node.description = "Ally X Speaker DSP"
    media.name       = "Ally X Speaker DSP"
    filter.graph = {
      nodes = [
        { type = builtin label = convolver name = convL
          config = { filename = "<settings>/ir.wav" channel = 0 blocksize = 256 tailsize = 2048 } }
        { type = builtin label = convolver name = convR
          config = { filename = "<settings>/ir.wav" channel = 1 blocksize = 256 tailsize = 2048 } }
        { type = builtin label = param_eq  name = eq
          config = { filename = "<settings>/voicing-game.txt" } }
        { type = lv2 name = mbc plugin = "http://lsp-plug.in/plugins/lv2/mb_compressor_stereo" control = { … } }
        { type = lv2 name = lim plugin = "http://lsp-plug.in/plugins/lv2/limiter_stereo"       control = { … } }
      ]
      links = [
        { output = "convL:Out" input = "eq:In 1" }  { output = "convR:Out" input = "eq:In 2" }
        { output = "eq:Out 1"  input = "mbc:in_l" } { output = "eq:Out 2"  input = "mbc:in_r" }
        { output = "mbc:out_l" input = "lim:in_l" } { output = "mbc:out_r" input = "lim:in_r" }
      ]
      inputs  = [ "convL:In" "convR:In" ]
      outputs = [ "lim:out_l" "lim:out_r" ]
    }
    capture.props = {
      node.name = "ally_dsp.sink"  media.class = Audio/Sink
      audio.channels = 2  audio.position = [ FL FR ]
      filter.smart = true
      filter.smart.name = ally-speaker-dsp
      filter.smart.target = { node.name = "~alsa_output.pci-.*analog-stereo" }   # per pw-dump ermitteln
    }
    playback.props = { node.name = "ally_dsp.playback"  node.passive = true
                       audio.channels = 2  audio.position = [ FL FR ] }
  }
}
```

**Fallback ohne LV2** (falls das Laden aus `~/.lv2` im PipeWire-Prozess scheitert): reine Builtin-Kette aus `convolver` + `param_eq` + `linear` (Pre-Gain) + `clamp` als Notbremse. Klanglich schwächer (kein Multiband, hartes Clipping statt Limiter), aber garantiert lauffähig.

### 7.3 Woher kommt das Tuning?

1. **DAX3-Import** (authentisch): ASUS-Download „Dolby Atmos driver“ (oder Windows-Partition) → `DEV_0294_SUBSYS_10431384_PCI_SUBSYS_13841043.xml` → `dolby_to_pipewire.py` → Presets Balanced/Detailed/Warm × Dynamic/Game/Movie/Music/Voice. Verifizierter Ablauf in Abschnitt 10.
2. **Messung** (objektiv): UMIK-1 oder kalibriertes Handy-Mikro + REW, Lautsprecher unter Linux und unter Windows (Dolby an) an identischer Position messen; Differenzkurve → param_eq-Datei oder Minimalphasen-IR. Ergänzend Abgleich mit dem TAS-Firmware-Verhalten (die Amp-DSP-Ebene muss dabei identisch sein).
3. **Gehör-Presets** (schnell): Harman-ähnliche Zielkurve für Kleinlautsprecher, Lowshelf-Anhebung 150–250 Hz begrenzt durch Multiband-Kompression, Präsenz 2–4 kHz, Höhen ab 8 kHz leicht angehoben.

### 7.4 Latenz und Last

- Quantum 512 @ 48 kHz = 10,7 ms Puffer (SteamOS-Default). param_eq ≈ 0 ms, Convolver mit 256er Head-Partition ≈ 0–5 ms, LSP-Limiter-Lookahead ≈ 5 ms. Gesamt unter 15 ms zusätzlich, für Spiele unkritisch. "Game"-Preset ohne Convolver für minimale Latenz vorsehen.
- CPU: wenige Prozent eines Kerns auf dem Z2 Extreme; Faust-/LSP-Plugins laufen im PipeWire-RT-Thread.

### 7.5 Sicherheit für die Lautsprecher

Der eigentliche Schutz (Thermik, Auslenkung) sitzt in der TAS2781-Firmware, sofern sie geladen ist. Trotzdem: Limiter immer als letztes Glied, Pre-Gain begrenzen, Bass-Anhebung nur mit Multiband-Kompression, keine `amixer`-Experimente mit Program/Config ohne klare Dokumentation.

### 7.6 UI-Ideen für das QAM

- Hauptschalter, Preset-Auswahl (Game / Film / Musik / Stimme / Dolby-Import / Custom), Bass/Höhen/Klarheit-Regler (mappen auf Lowshelf, Highshelf, 2,5-kHz-Band), Lautheit (Leveler an/aus), Stereo-Breite.
- Pro-Spiel-Profile analog zu DeckSP und den Steam-Performance-Profilen.
- Diagnose-Tab: Kernel, TAS2781 gebunden?, Firmware geladen?, aktives Program/Config, aktiver Ausgang (Speaker/Headphones), Filter aktiv?, Latenz.
- Toast bei Kopfhörer-Erkennung ("DSP pausiert").

---

## 8. Offene Punkte, Risiken, Verifikation auf dem Gerät

### 8.1 Zuerst auf dem Xbox Ally X prüfen (Desktop-Modus, Konsole)

```bash
uname -r                                                   # 6.16 = Stable, 6.18 = Beta, 7.2 = 3.9 Preview
cat /sys/devices/virtual/dmi/id/sys_vendor /sys/devices/virtual/dmi/id/product_name   # exakter DMI-Name für hwconfig
sudo dmesg | grep -iE "tas2781|tasdev|TAS2XXX|realtek|hda"   # Firmware geladen? Kalibrierung? Fehler?
grep -i "Subsystem Id" /proc/asound/card*/codec#*           # erwartet 0x10431384
amixer -c 0 controls | grep -i speaker                      # "Speaker Program Id" etc. = TAS-Treiber gebunden
amixer -c 0 cget name='Speaker Program Id'; amixer -c 0 cget name='Speaker Config Id'
pw-dump | jq -r '.[] | select(.info.props["media.class"]=="Audio/Sink") | .info.props["node.name"]'   # Sink-Name für filter.smart.target
pw-metadata -n settings 0 clock.force-quantum; pw-top       # Quantum/Latenz
ls /run/pipewire /run/wireplumber; cat /run/pipewire/README # welches hwconfig-Profil aktiv ist (erwartet: default)
lv2ls 2>/dev/null | head; ls /usr/lib/lv2                   # LV2-Infrastruktur, Valve-Plugins vorhanden?
```

Ist unter Stable der TAS-Treiber nicht gebunden (keine "Speaker …"-Controls, leise Ausgabe), sollte ein Vergleichstest mit dem SteamOS-Beta- oder Preview-Kanal erfolgen, bevor Zeit ins Host-DSP fließt.

### 8.2 Technische Risiken

- **LV2 aus `~/.lv2` im PipeWire-Dienst:** `lilv_world_load_all()` nutzt `LV2_PATH` bzw. Standardpfade des PipeWire-Prozesses (systemd --user). Falls `~/.lv2` nicht erfasst wird: `systemctl --user set-environment LV2_PATH=…` plus Neustart von PipeWire, oder Drop-in `~/.config/environment.d/`. Alternativ LADSPA-Builds mit absolutem Pfad (LSP gibt es auch als LADSPA, Funktionsumfang geringer).
- **Kopfhörer an der 3,5-mm-Buchse** hängen am selben ALSA-Sink (Port-Umschaltung Speaker/Headphones). Der Filter würde dann auch Kopfhörer bearbeiten → Plugin muss den aktiven Port beobachten (`pw-dump`/`pw-mon` auf `Route`) und den Filter entladen bzw. `filter.smart.disabled` setzen.
- **Steam-Lautstärke** greift am ALSA-Sink hinter dem Filter → Kompressor-/Limiter-Schwellen bleiben lautstärkeunabhängig (gut), aber sehr leise Wiedergabe wird nicht "aufgeholt"; dafür der Leveler.
- **Bluetooth/HDMI** dürfen nicht gefiltert werden → `filter.smart.target` strikt auf den PCI-Analog-Sink.
- **Firmware-/Kernel-Updates** ändern Pegel und Klang der Amp-Ebene (Bazzite #4366) → Presets ggf. je Kernelstand nachziehen; Diagnose-Tab zeigt Version.
- **Lizenz/Redistribution:** DAX3-XML und ASUS-Tuning nicht mitliefern; nur Konverter (MIT), LSP (LGPL-3), Calf (LGPL), eigene Mess-/Gehör-Presets.
- **Decky-Store-Richtlinien:** Binaries müssen in CI (Docker) reproduzierbar gebaut werden (`backend/`, `remote_binary_bundling`).

### 8.3 Nicht verifiziert

- ~~Ob Valves 6.16-Kernel Xbox-Ally-Audiopatches zurückportiert hat~~ Erledigt: Codec-Binding ist enthalten (Abschnitt 10). Offen bleibt nur der UEFI-Kalibrierungs-Fix.
- ~~Exakter DAX3-Dateiname und ob ASUS für RC73XA ein separates Dolby-Paket zum Download anbietet.~~ Erledigt (Abschnitt 10).
- Port-Symbole der LSP-Plugins und Verhalten von `filter.smart` mit Wildcard-Targets auf WirePlumber 0.5.14 (Doku beschreibt ein JSON-Match-Objekt).
- Wo Valve die Deck-Lautsprecherkette (`valve_deck_speakers`) tatsächlich einhängt (nicht in `steamdeck-dsp` 0.99; vermutlich `jupiter-hw-support`, 51 MB, nicht geprüft).

---

## 9. Roadmap-Vorschlag

| Phase | Inhalt | Ergebnis |
|---|---|---|
| **0 Diagnose** | ✅ erledigt am 19.09.2026 per SSH (Abschnitt 10). Offen: Hörtest oberhalb 70 % Lautstärke, Vergleich mit Beta-Kernel 6.18 | Go für Host-DSP: Amp gebunden, Firmware identisch mit Windows, kein Host-DSP aktiv |
| **1 Proof of Concept (2–3 Tage)** | Handgeschriebene `filter-chain`-Konfiguration mit param_eq + Convolver als Smart Filter per `pw-cli` laden; Gehör-Preset; Kopfhörer-Test | Belegt Machbarkeit und Klanggewinn ohne Plugin-Code |
| **2 MVP-Plugin (1–2 Wochen)** | Decky-Template, Backend mit systemd-Unit/service.sh (Vorlage Virtual Surround Sound), QAM: Ein/Aus + 3–4 Presets, Diagnose-Tab | Nutzbar im Gaming-Modus, update-sicher |
| **3 Klang (1–2 Wochen)** | LSP-LV2 bündeln (MBC + Limiter), DAX3-Import über `dolby_to_pipewire.py`, Messpreset mit REW, Kopfhörer-Erkennung, Pro-Spiel-Profile | Windows-nahes Klangbild |
| **4 Veredelung** | Eigenes Faust-LV2 (schlank, ein Bundle wie bei Valve), Leveler via ebur128, Stereo-Breite, Store-Einreichung | Wartbares Produkt |
| **5 Upstream** | Tuning als `hardware-profile` für `asustek computer inc.-rog xbox ally x rc73xa…` an Bazzite und Valve (`steamdeck-dsp`) einreichen | Nutzen für alle, Plugin bleibt als Komfort-UI |

---

## 10. Nachtrag 19.09.2026: Gerätediagnose per SSH und DAX3-Beschaffung ohne Windows

### 10.1 Diagnose am Gerät (SteamOS 3.8.16, Build 20260716.1, nur lesende Befehle)

| Punkt | Befund |
|---|---|
| Kernel | `6.16.12-valve24.5-1-neptune-616` |
| DMI | `ASUSTeK COMPUTER INC.` / `ROG Xbox Ally X RC73XA_RC73XA`, BIOS RC73XA.317 → hwconfig-Profilname `asustek computer inc.-rog xbox ally x rc73xa_rc73xa`, gefunden wurde nur `default` (Beleg: `/run/pipewire/README`) |
| Codec | Realtek **ALC294**, Vendor 0x10ec0294, Subsystem 0x10431384 (Karte 1 „Generic_1“); Karte 0 ist HDMI |
| Amp-Treiber | gebunden: „ALC294: picked fixup for PCI SSID 1043:1384“, „bound i2c-TXNW2781:00-tas2781-hda.0“, „Instantiated 2 I2C devices“ → beide TAS2781 aktiv |
| TAS-Controls (Karte 1) | Program Id 0 (max 0), Config Id 0 (max 1), Profile Id 0 (max 2), Analog Gain 20/20 (11 dB + 20×0,5 dB), Force Firmware Load off |
| Amp-Firmware | `TAS2XXX13840.bin` und `13841.bin` vorhanden; **SHA-256 identisch mit den Dateien aus ASUS' Windows-Paket „TI Smart Amplifier Driver V3.1.52.0“** (58cffa36… bzw. 0fda76e7…). Header-String: „RC73_Veco_ISLR100 / Tuning Mode“. Die Amp-Ebene ist also unter Linux und Windows dieselbe Firmware |
| PipeWire-Stack | pipewire 1:1.6.4-1.6, wireplumber 0.5.14-1.4, steamdeck-dsp 0.96-1, lilv 0.24.26, lv2 1.18.10; `lv2ls` findet Valves drei Faust-Plugins; LADSPA: `caps.so`, `rnnoise_ladspa.so` |
| Aktive Filter | Valves Mikrofon-Kette (rnnoise + `valve_deck_microphone`) läuft als **eigener PipeWire-Prozess** (`filter-chain.service`, `pipewire -c filter-chain.conf`, gehärtet mit `MemoryDenyWriteExecute`, `NoNewPrivileges`, Syscall-Filter). Zusätzlich hängt WirePlumber per `node.create-loopback` Loopback-Smart-Filter vor Sink und Source (`alsa_loopback_device.alsa_output.pci-0000_64_00.6.analog-stereo`) → unser Filter muss sich per `filter.smart.before/after` einordnen |
| Sink | `alsa_output.pci-0000_64_00.6.analog-stereo` („Ryzen HD Audio Controller Analog Stereo“, `alsa.card_name` = „HD-Audio Generic“, identisch mit der HDMI-Karte → Match über `node.name`/`device.name`); Routen: `analog-output-speaker` aktiv, `analog-output-headphones` available=no (Jack-Erkennung funktioniert, gleicher Sink) |
| Takt | 48 kHz, quantum 512 (min 256, max 8192), keine Overrides |
| Speicher | NVMe 1,8 TB nur mit SteamOS-Layout, **keine NTFS/Windows-Partition**; SD-Karte ext4 |
| Werkzeuge | Python 3.13.5 (ensurepip ok, kein pip/numpy systemweit), git, zstd, **7z**, flathub-Remote; Root-FS read-only (`steamos-readonly enabled`) |
| Decky | Loader aktiv, Plugins: Ally Fix, LSFG-VK, Framegen, HueSync, autoflatpaks, steamgriddb |

Bewertung: Ebene A (Amp) ist auf diesem Build grundsätzlich in Ordnung, die Firmware ist dieselbe wie unter Windows. Offen bleibt nur, ob der UEFI-Kalibrierungs-Fix im Valve-Kernel steckt (Hörtest oberhalb 70 % Lautstärke). Ebene B (Host-DSP) fehlt vollständig. Das bestätigt die Stoßrichtung des Plugins.

### 10.2 DAX3-Tuning ohne Windows: verifizierter Weg

**Antwort: Es braucht kein installiertes Windows.** Die Tuning-XML liegt im öffentlichen ASUS-Download „Dolby Atmos driver“ für das RC73XA. Verifiziert am 19.09.2026 lokal (macOS, py7zr) und auf dem Ally (SteamOS, 7z), beide Male SHA-256 `3b422b4c36ed73d7023072ccde9fc288b556d77013788bee30910f54de3bb7b6`.

Fundort über die ASUS-Support-API (JSON, liefert relative Pfade auf `https://dlcdnets.asus.com`):

```
https://www.asus.com/support/webapi/ProductV2/GetPDDrivers?website=us&model=rog+xbox+ally+x+%EF%BC%882025%EF%BC%89+rc73xa&pdhashedid=&osid=52
```

| Paket (RC73XA) | Datei | Inhalt |
|---|---|---|
| Dolby Atmos driver V11.130.1340.46 (25.02.2026, 10,3 MB) | `/pub/ASUS/IOTHMD/Image/Software/SoftwareandUtility/17507/DolbyAtmosdriverforConsumer_ASUS_Z_V11.130.1340.46_17507.exe` | Inno-Setup-Hülle mit eingebettetem 7z-Archiv (Offset 4285120). Darin `ext_realtek_asus_consumer/ext_asus_consumer_AIO_rtk_24h2_25h2 v11.130.1340.46/` mit `dax3_ext_rtk.inf` und 49 Tuning-XMLs für ASUS-Geräte, darunter **`DEV_0294_SUBSYS_10431384_PCI_SUBSYS_13841043.xml`** (Xbox Ally X) und `…10431394…` (Xbox Ally RC73YA); dazu `swc_factory/` (Dolby APO-Service 3.30902.922.0, HSA) |
| Realtek Audio Driver V6.0.9882.1 (234,8 MB) | `/pub/ASUS/IOTHMD/Image/Driver/Audio/45010/Audio_DriverOnly_Dolby_ROG_Realtek_Z_V6.0.9882.1_45010.exe` | Codec-INFs (`HDXACPASUS.inf` listet `DEV_0294&SUBSYS_1043…`) und Dolby-Wrapper-INFs, **keine** DAX3-XML |
| TI Smart Amplifier Driver V3.1.52.0 (4,2 MB) | `/pub/ASUS/IOTHMD/Image/Driver/Audio/43586/SmartAMP_TI_DCH_ROG_TexasInstruments_Z_V3.1.52.0_43586_1.exe` | `TAS2xxx.inf` (ACPI\VEN_TXNW&DEV_2781&SUBSYS_10431384) und `Firmwares/TAS2XXX*.bin`, identisch mit linux-firmware |

Die INF bestätigt die Zuordnung: `DeviceExtension_Install_DolbyAccessNoGaming, HDAUDIO\FUNC_01&VEN_10EC&DEV_0294&SUBSYS_10431384` → `DEV_0294_SUBSYS_10431384_PCI_SUBSYS_13841043.xml`.

Rezept (funktioniert so auf SteamOS, 7z ist vorinstalliert; auf macOS statt 7z `py7zr`):

```bash
curl -L -o DolbyAtmos_ASUS.exe "https://dlcdnets.asus.com/pub/ASUS/IOTHMD/Image/Software/SoftwareandUtility/17507/DolbyAtmosdriverforConsumer_ASUS_Z_V11.130.1340.46_17507.exe"
# 7z liest die EXE nur als PE-Datei, deshalb das 7z-Archiv am Signatur-Offset herausschneiden:
python3 - <<'PY'
d=open('DolbyAtmos_ASUS.exe','rb').read(); off=d.find(b'7z\xbc\xaf\x27\x1c'); open('payload.7z','wb').write(d[off:])
PY
7z e -r -odax3 payload.7z DEV_0294_SUBSYS_10431384_PCI_SUBSYS_13841043.xml dax3_ext_rtk.inf
```

Negativbefund Microsoft-Update-Katalog: Die Suche nach `HDAUDIO\FUNC_01&VEN_10EC&DEV_0294&SUBSYS_10431384` liefert nur „Realtek Semiconductor Corp. – MEDIA – 6.0.9882.1“ (CAB, 12,8 MB, nur Codec-INFs). Die Dolby-Extension-Pakete („Dolby Driver Update 3.309xx“) sind dort nicht über die Hardware-ID auffindbar. Der ASUS-Download ist damit der praktikable Weg.

Aufbau der XML (DAX3 3.7.1, Tuning-Version 11 vom 06.02.2025): ein Endpoint `internal_speaker` (2 Front-Lautsprecher, Modus `normal`), zehn Profile (`dynamic`, `movie`, `music`, `game`, `voice`, `voice_onlinecourse`, `personalize_user1–3`, `off`). Pro Profil zwei Blöcke: `tuning-cp` (IEQ mit den drei Voicings Balanced/Detailed/Warm, Dialog-Enhancer, Volume Leveler, Virtualizer, Bass Enhancer, Regulator, Virtual Bass) und `tuning-vlldp` (Speaker-PEQ, `filter_coefficients`, Multiband-Kompressor, Regulator, Sliding Bass, Noise Gate). Der Volume Leveler ist in diesem Tuning ab Werk aus. Kein Kopfhörer-Endpoint (dafür nutzt Dolby die generische `Headphone_Default_Generic_Default_Atmos3.10.xml`).

### 10.3 Konverter-Probelauf auf dem Ally (Arbeitsverzeichnis `~/ally-dsp-work`, nichts aktiviert)

- Umgebung: `python3 -m venv venv` + numpy 2.5.3 / scipy 1.18.1 (220 MB), Konverter-Commit bde5653 vom 14.09.2026. Auf dem Mac scheitert der Konverter mit Python 3.9 (benötigt 3.10+).
- `--list` erkennt Endpoint und alle zehn Profile; `--doctor` identifiziert das Gerät korrekt (Vendor, Produkt, ALC294/0x10431384, Sink, Takt).
- `--all-profiles --output-dir out_ee --irs-dir out_ee` erzeugt 30 EasyEffects-Presets (10 Profile × 3 Voicings), je 10–12 KB JSON plus 33 KB Impulsantwort (`.irs`). Kette im Game-Preset: `convolver` (Minimalphasen-FIR aus der Lautsprecherkorrektur) → `autogain` (bypass, weil Dolbys Leveler hier aus ist) → `multiband_compressor` (6 Bänder, Eingangsgain +4 dB) → `limiter` (Herm Thin, Lookahead 1 ms). Hinweis des Tools: ohne Leveler „likely quieter than on Windows“, optional `--enable autogain`.
- `dolby_to_pipewire.py --variant balanced --output-dir out_pw --no-activate` erkennt den Ziel-Sink automatisch, **bricht aber ab**: PipeWire kann drei LSP-LV2-Plugins nicht laden (`para_equalizer_x16_lr`, `mb_compressor_stereo`, `limiter_stereo`). Genau diese drei Bundles muss das Plugin mitbringen (z. B. nach `~/.lv2/`), dann läuft die Erzeugung der Filter-Chain durch.
- Nicht ausgeführt: Der Doctor empfiehlt, `Speaker Force Firmware Load` einzuschalten. Auf diesem Gerät ist der Treiber gebunden und die Firmware identisch mit Windows; der Schalter ist eine Debug-Funktion und sollte nur bewusst für einen A/B-Hörtest genutzt und danach zurückgesetzt werden.

Angelegt wurde auf dem Gerät nur `~/ally-dsp-work/` (Paket, `dax3/`, `st2ee/`, `venv/`, `out_ee/`); löschen mit `rm -rf ~/ally-dsp-work`. Im Projekt liegen XML, INF und die 30 Presets unter `local/` (git-ignoriert, nicht weitergeben).

### 10.4 Konsequenzen für das Plugin

1. **DAX3-Import zur Laufzeit statt Bündelung**: Das Plugin lädt das ASUS-Paket auf dem Gerät herunter (10 MB), schneidet das 7z-Archiv heraus, extrahiert die zur Codec-SSID passende XML (aus `/proc/asound` ermittelt) und konvertiert lokal. So bleibt das proprietäre Tuning beim Nutzer, analog zum Lenovo-Helfer des Konverters.
2. **LSP-LV2 bündeln**: `para_equalizer_x16_lr`, `mb_compressor_stereo`, `limiter_stereo` (Arch-Paket `lsp-plugins-lv2` 1.2.22 aus `extra-3.8` als Quelle, LGPL-3), Installation nach `~/.lv2/`, Prüfung mit `lv2ls`.
3. **Eigener PipeWire-Prozess nach Valve-Vorbild**: `systemd --user`-Unit mit `pipewire -c ally-dsp.conf` (wie `filter-chain.service`) statt `pw-cli load-module` im Haupt-Daemon; robust gegen Abstürze des DSP-Graphen.
4. **Smart-Filter-Reihenfolge** gegenüber Valves Loopback-Filter festlegen und **Kopfhörer-Route** (`analog-output-headphones`) überwachen, um die Lautsprecherkorrektur bei Kopfhörern abzuschalten.
5. **Numpy/Scipy nur zur Konvertierung**: entweder einmalig in einer venv unter `~/homebrew/data/<plugin>/` oder die Konvertierung in eine Vorab-Stufe verlagern und nur fertige `.conf` + `.irs` ausliefern (dann ohne DAX3-Import).

## 11. Quellen

Hardware, Kernel, Firmware
- Phoronix: Linux Working Around Audio Problems On The ASUS ROG Xbox Ally X — https://www.phoronix.com/news/ASUS-Xbox-Ally-X-Linux-Audio
- LKML-Bugthread "hda/tas2781: ASUS ROG Xbox Ally X audio issues with default firmware" (Dez 2025) — https://ratatoskr.run/linux-sound/2025/12/3322915/t und https://lkml.iu.edu/2512.3/04468.html
- Kernel 6.17.13 ChangeLog (Xbox-Ally-Commits von A. Kapenekakis) — https://cdn.kernel.org/pub/linux/kernel/v6.x/ChangeLog-6.17.13
- Upstream-Commit "Add match for ASUS Xbox Ally projects" (SSIDs 1043:1384/1394, ALC287) — https://github.com/torvalds/linux/commit/18a4895370a79a3efb4a53ccd1efffef6c5b634e
- Patch "Skip UEFI calibration on ASUS ROG Xbox Ally X" (Jan 2026) — https://patchew.org/linux/20260108093650.1142176-1-matthew.schwartz@linux.dev/
- TI-Patch "workaround solution to lower-vol issue … TAS2781" (Feb 2026, revertiert Skip-Quirk) — https://ratatoskr.run/lkml/2026/02/3431107/t
- ASUS Spezifikation RC73XA — https://rog.asus.com/gaming-handhelds/rog-ally/rog-xbox-ally-x-2025/spec/
- SteamOS-Issues: #2248 rechter Lautsprecher stumm — https://github.com/ValveSoftware/SteamOS/issues/2248 ; #2289 kein Ton nach Update — https://github.com/ValveSoftware/SteamOS/issues/2289
- Bazzite-Issues: #3372 — https://github.com/ublue-os/bazzite/issues/3372 ; #4366 — https://github.com/ublue-os/bazzite/issues/4366 ; #1481 (Ally X leiser als Windows) — https://github.com/ublue-os/bazzite/issues/1481
- ROG Flow Z13 Linux-Audio-Untersuchung (Amp-Gain vs. Software-EQ) — https://dev.to/ankk98/rog-flow-z13-2025-linux-audio-quality-investigation-3ggk

SteamOS-Stack
- SteamOS-Paketspiegel (jupiter-3.8: pipewire 1.6.8, wireplumber 0.5.14, steamdeck-dsp 0.99, linux-neptune-616/618/72) — https://steamdeck-packages.steamos.cloud/archlinux-mirror/jupiter-3.8/os/x86_64/
- Arch-Spiegel extra-3.8 (lsp-plugins, calf, easyeffects, lilv) — https://steamdeck-packages.steamos.cloud/archlinux-mirror/extra-3.8/os/x86_64/
- steamdeck-dsp Spec (OpenMandriva) — https://github.com/OpenMandrivaAssociation/steamdeck-dsp
- SteamOS 3.8 Release Notes — https://steamcommunity.com/games/1675200/announcements/detail/697641379212298073
- GamingOnLinux: SteamOS 3.8.27 Beta / 3.9.1 Preview (Kernel 7.2) — https://www.gamingonlinux.com/2026/09/steamos-3-8-27-beta-and-steamos-3-9-1-preview-released-valve-continue-working-on-nvidia-support/
- Steam-Forum: virtuelle Sinks im Gaming-Modus (Deck OLED) — https://steamcommunity.com/app/1675200/discussions/2/598526768326935581/
- SteamOS-Issue #1329 Filter Chain Sink Deck OLED — https://github.com/ValveSoftware/SteamOS/issues/1329

PipeWire / WirePlumber
- Filter-Chain-Dokumentation — https://docs.pipewire.org/page_module_filter_chain.html
- PipeWire NEWS (Feature-Historie filter-graph) — https://raw.githubusercontent.com/PipeWire/pipewire/master/NEWS
- Quellcode 1.6.8 filter-graph (plugin_builtin.c, plugin_ladspa.c, plugin_lv2.c) — https://github.com/PipeWire/pipewire/tree/1.6.8/spa/plugins/filter-graph
- WirePlumber Smart Filters — https://pipewire.pages.freedesktop.org/wireplumber/policies/smart_filters.html
- Collabora: Smart audio filters with WirePlumber 0.5 — https://www.collabora.com/news-and-blog/blog/2024/06/26/smart-audio-filters-with-wireplumber-0.5/

Bestehende Projekte
- Decky Virtual Surround Sound — https://github.com/DeckSettings/decky-virtual-surround-sound
- DeckSP — https://github.com/jessebofill/DeckSP ; AudioForge — https://github.com/neoseek/AudioForge
- Volume Boost — https://github.com/saumya-banthia/volume-boost
- Bazzite ROG Ally RC71L Filter-Chain — https://github.com/ublue-os/bazzite/tree/main/system_files/deck/shared/usr/share/pipewire/hardware-profiles
- speaker-tuning-to-easyeffects (DAX3 → PipeWire) — https://github.com/antoinecellerier/speaker-tuning-to-easyeffects
- EasyEffects-Diskussion DAX3-Konverter — https://github.com/wwmm/easyeffects/discussions/4899
- Decky Plugin Template — https://github.com/SteamDeckHomebrew/decky-plugin-template ; Decky Loader Sandbox (Root-Flag) — https://github.com/SteamDeckHomebrew/decky-loader/blob/main/backend/decky_loader/plugin/sandboxed_plugin.py
- Decky-Store-API (Audio-Plugins) — https://plugins.deckbrew.xyz/plugins
- LSP Plugins — https://lsp-plug.in/

Dolby
- Dolby Volume Leveler / Dialogue Enhancer / IEQ / Virtualizer — https://professional.dolby.com/tv/dolby-home-theater-v4/
- PC Guide: Ally-X-Nutzer empfehlen Dolby-Preset "Custom 1" — https://www.pcguide.com/news/rog-ally-x-users-recommend-changing-this-default-sound-setting-to-improve-audio-quality/

Nachtrag (Gerätediagnose und DAX3)
- ASUS Support-API RC73XA (Treiberliste als JSON) — https://www.asus.com/support/webapi/ProductV2/GetPDDrivers?website=us&model=rog+xbox+ally+x+%EF%BC%882025%EF%BC%89+rc73xa&pdhashedid=&osid=52
- ASUS Support-Seite RC73XA — https://www.asus.com/us/supportonly/rog%20xbox%20ally%20x%20(2025)%20rc73xa/helpdesk_download/
- ASUS Dolby Atmos driver V11.130.1340.46 — https://dlcdnets.asus.com/pub/ASUS/IOTHMD/Image/Software/SoftwareandUtility/17507/DolbyAtmosdriverforConsumer_ASUS_Z_V11.130.1340.46_17507.exe
- ASUS TI Smart Amplifier Driver V3.1.52.0 — https://dlcdnets.asus.com/pub/ASUS/IOTHMD/Image/Driver/Audio/43586/SmartAMP_TI_DCH_ROG_TexasInstruments_Z_V3.1.52.0_43586_1.exe
- Microsoft Update Catalog, Suche nach Hardware-ID — https://www.catalog.update.microsoft.com/Search.aspx?q=HDAUDIO%5CFUNC_01%26VEN_10EC%26DEV_0294%26SUBSYS_10431384
- speaker-tuning-to-easyeffects, Abschnitt „Extracting the XML“ — https://github.com/antoinecellerier/speaker-tuning-to-easyeffects#extracting-the-xml

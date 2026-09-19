# Plan: Decky-Plugin „Ally DSP“ für den ROG Xbox Ally X

Stand: 19.09.2026. Baut auf `docs/recherche-ideensammlung.md` auf (dort Abschnitt 10: Gerätediagnose und verifizierte DAX3-Beschaffung). Name: **Ally DSP** (entschieden am 19.09.2026). Der Name in `plugin.json` wird gleichzeitig Ordnername unter `~/homebrew/plugins/` und muss beim Self-Update stabil bleiben. Verteilung ausschließlich über GitHub Releases, keine Store-Einreichung.

---

## 1. Ziel und Umfang

**Ziel:** Ein Decky-Plugin, das dem Xbox Ally X unter SteamOS das Lautsprecher-Tuning zurückgibt, das unter Windows Dolby Atmos liefert. Das Tuning stammt aus ASUS' eigenem Treiberpaket und wird auf dem Gerät in eine PipeWire-Filter-Chain übersetzt.

**Kernfunktionen (Anforderungen aus dem Gespräch):**

1. **Setup-Schritt**: Download des ASUS-Pakets „Dolby Atmos driver“, Extraktion der passenden DAX3-XML, Konvertierung in Presets, Aktivierung.
2. **Self-Update über GitHub Releases**: Prüfung, signierte Verifikation, Installation ohne Root über Deckys eigene Install-API.
3. **Globales Preset oder Per-Game-Preset**: Automatisches Umschalten beim Spielstart, Rückfall auf global beim Beenden.
4. **Presets wie in der Atmos-App**: Dynamic, Game, Movie, Music, Voice, Custom 1–3, jeweils mit Voicing Balanced / Detailed / Warm.

**Nicht-Ziele (v1):** Kopfhörer-Tuning (Dolby nutzt dafür eine generische XML, später möglich), Kernel- oder Firmware-Eingriffe, eigene Klangregler jenseits der Dolby-Parameter, Unterstützung anderer Geräte als RC73XA/RC73YA (Architektur lässt es zu, Tests nicht).

**Grundsätze:** kein Root (`"flags": []`), keine Änderung am Read-only-Rootfs, alles unter `/home`, proprietäre Tuning-Daten werden nur auf dem Gerät des Nutzers heruntergeladen und nie mit dem Plugin ausgeliefert.

---

## 2. Verifizierte Grundlagen, auf denen der Plan steht

| Baustein | Status | Beleg |
|---|---|---|
| Amp-Ebene funktioniert auf SteamOS 3.8.16 | ✅ | Codec ALC294 an 2× TAS2781 gebunden, Firmware identisch mit Windows (Recherche 10.1) |
| Kein Host-DSP vorhanden | ✅ | steamdeck-dsp nutzt `default`-Profil, nur Mikrofonkette aktiv |
| DAX3-XML ohne Windows beschaffbar | ✅ | ASUS-API liefert Paket-URL **und SHA-256**; Paket = Inno-EXE mit 7z-Archiv; `DEV_0294_SUBSYS_10431384_PCI_SUBSYS_13841043.xml` extrahiert, Hash lokal und am Gerät identisch |
| Konverter erzeugt PipeWire-Konfiguration | ✅ | `dolby_to_pipewire.py` schrieb `Dolby_Balanced.conf` + `.irs` (Kette: Convolver L/R → LSP PEQ x16 LR „dialog“ → LSP Multiband-Kompressor „reg“ → LSP Limiter „lim“, Smart-Filter auf `alsa_output.pci-0000_64_00.6.analog-stereo`) |
| LSP-LV2 aus Nutzerverzeichnis ladbar | ✅ | `lsp-plugins-lv2` 1.2.22 aus dem SteamOS-Spiegel, `ldd` vollständig, `lv2info` über `LV2_PATH` erfolgreich, kein Root |
| Decky führt Backends in eigenem Python 3.11 aus | ✅ | `multiprocessing.Process` im PyInstaller-Bundle → numpy/scipy nicht im Plugin-Prozess nutzbar, Konverter läuft als Subprozess in eigener venv (Python 3.13 des Systems) |
| Root-freier Update-Pfad | ✅ | Frontend kann `window.DeckyBackend.callable('utilities/install_plugin')(url, name, version, sha256, installType)` aufrufen; Decky zeigt Bestätigungsdialog, lädt, prüft SHA-256, deinstalliert alt, entpackt, lädt Plugin neu |
| Per-Game-Erkennung | ✅ Muster | DeckSP: MobX-Reaction auf `SteamUIStore.MainRunningAppID`, Namen über `appStore.GetAppOverviewByAppID()` |
| Systemd-User-Unit für eigenen PipeWire-Prozess | ✅ Muster | Valves `filter-chain.service` (`pipewire -c filter-chain.conf`, `BindsTo=pipewire.service`) |

Noch **nicht** verifiziert: Klang und Latenz der aktiven Kette, Zusammenspiel mit Valves Loopback-Smart-Filter (Reihenfolge), Verhalten bei Suspend/Resume und PipeWire-Neustart, Lautstärkeverhalten gegenüber Windows (Dolby-Leveler ist im Tuning ab Werk aus).

---

## 3. Architektur

```
┌──────────────────────────── Steam Gaming Mode ────────────────────────────┐
│  Decky Loader (Python 3.11, root)                                          │
│   └─ Plugin-Backend „Ally DSP“ (läuft als deck, flags: [])                 │
│        py_modules/allydsp/                                                  │
│        ├─ hardware.py    SSID/Codec, DMI, Sink-Name, Kopfhörer-Route         │
│        ├─ asus_fetch.py  ASUS-API → Paket-URL+SHA256 → Download → 7z-Extrakt │
│        ├─ convert.py     Subprozess: venv/bin/python converter/… → conf+irs  │
│        ├─ dsp_runtime.py systemd --user ally-dsp.service (pipewire -c conf)  │
│        ├─ profiles.py    global / per-App, Voicing, Extras (JSON)            │
│        ├─ jack_watch.py  Kopfhörer erkannt → Kette pausieren                 │
│        ├─ updater.py     GitHub Releases, SHA256SUMS + minisign, Hand-off    │
│        └─ diagnostics.py Health-Report                                       │
│                                                                             │
│  Frontend (React/TS, @decky/ui, @decky/api)                                 │
│   ├─ QAM-Panel: Status · Preset · Voicing · Per-Game · Extras · Update       │
│   ├─ Setup-Wizard (Route) · Diagnose (Route)                                │
│   └─ MobX-Reaction MainRunningAppID → backend.on_running_app_changed()      │
└─────────────────────────────────────────────────────────────────────────────┘
          │ systemctl --user                      │ ASUS CDN / GitHub API (https)
          ▼                                       ▼
┌────────────────────────── Audio-Laufzeit (User-Session) ───────────────────┐
│ ally-dsp.service: /usr/bin/pipewire -c ~/homebrew/data/Ally DSP/active.conf │
│   Environment=LV2_PATH=~/homebrew/plugins/Ally DSP/bin/lv2:/usr/lib/lv2      │
│   filter-chain: conv_l/conv_r → dialog(PEQ) → reg(MBC) → lim → Smart-Filter  │
│   filter.smart.target = { node.name = "alsa_output.pci-…analog-stereo" }     │
└─────────────────────────────────────────────────────────────────────────────┘
          │ WirePlumber Smart-Filter-Policy (transparent, Steam sieht weiter den echten Sink)
          ▼
   Lautsprecher-Sink → ALC294 → TAS2781-Firmware (Schutz/Tuning) → Lautsprecher
```

### 3.1 Warum ein eigener PipeWire-Prozess statt `pw-cli load-module`

- Valve macht es genauso (`filter-chain.service`); Absturz oder Neustart der DSP-Kette berührt den Haupt-Daemon nicht.
- Eigene Umgebung: `LV2_PATH` zeigt auf das Plugin-Verzeichnis, kein Eingriff in `~/.lv2` oder Systempfade.
- Preset-Wechsel = Unit-Neustart mit anderer Konfiguration (kurze Lücke unter einer Sekunde), sauber und deterministisch.
- `BindsTo=pipewire.service` sorgt dafür, dass die Kette bei PipeWire-Neustart mit neu startet.

### 3.2 Datenablage auf dem Gerät

| Pfad | Inhalt | Lebensdauer |
|---|---|---|
| `~/homebrew/plugins/Ally DSP/` | Plugin-Code, `dist/`, `py_modules/`, `bin/lv2/lsp-plugins.lv2/`, `defaults/converter/` | wird bei Update ersetzt |
| `~/homebrew/settings/Ally DSP/settings.json` | Presets, Per-Game-Zuordnung, Extras, Update-Kanal | bleibt erhalten |
| `~/homebrew/data/Ally DSP/dax3/` | XML + INF + `provenance.json` (URL, Version, SHA-256, Datum) | bleibt erhalten |
| `~/homebrew/data/Ally DSP/venv/` | Python-venv mit numpy/scipy (≈220 MB) | bleibt erhalten, wird bei Python-Versionswechsel neu gebaut |
| `~/homebrew/data/Ally DSP/presets/<profil>/<voicing>/{chain.conf,ir.irs,meta.json}` | 30 vorkonvertierte Presets | bei Änderung der Extras neu erzeugt |
| `~/homebrew/data/Ally DSP/active/` | Kopie des aktiven Presets, auf das die Unit zeigt | bei jedem Wechsel |
| `~/.config/systemd/user/ally-dsp.service` | Unit-Datei | bis Deinstallation |
| `~/homebrew/logs/Ally DSP/` | Plugin-Log (`decky.logger`) | rotiert von Decky |

---

## 4. Funktionsblöcke im Detail

### 4.1 Setup-Wizard (erster Start, jederzeit wiederholbar)

| Schritt | Backend | Frontend | Fehlerfall |
|---|---|---|---|
| 1 Hardware-Check | `hardware.detect()` liest `/proc/asound/card*/codec#*` (Vendor 0x10ec0294, Subsystem 0x10431384), DMI-Produktname, Sink-Name via `pw-dump`, prüft `Speaker Program Id`-Control (Amp gebunden) | Ampelanzeige; unbekannte SSID → „Gerät nicht unterstützt“ mit Option „trotzdem versuchen“ | Abbruch mit Diagnose-Link |
| 2 Paketquelle | `asus_fetch.resolve()` fragt die ASUS-API `ProductV2/GetPDDrivers` (Modell RC73XA, osid 52) nach dem Eintrag „Dolby Atmos driver“ (Titel, Version, `DownloadUrl.Global`, `sha256`). Fallback: im Plugin gepinnte URL + SHA-256 der zuletzt bekannten Version | zeigt Version/Größe (≈10 MB) | API nicht erreichbar → Fallback-URL; keine Netzverbindung → Hinweis |
| 3 Download | `curl -fL --retry 3 -C -` nach `data/tmp/`, Fortschritt per `decky.emit("setup_progress", …)`, SHA-256-Vergleich mit API-Wert | Fortschrittsbalken | Hash-Fehler → löschen, erneut |
| 4 Extraktion | 7z-Signatur (`37 7A BC AF 27 1C`) im EXE suchen, Payload ab Offset schreiben, `/usr/bin/7z e -r` nur `DEV_<codec>_SUBSYS_<ssid>*.xml` + `dax3_ext_rtk.inf`; INF-Zeile für die SSID als Gegenprobe; Ablage in `data/dax3/` mit `provenance.json` | Anzeige der gefundenen XML | kein `7z` → gebündeltes statisches `7zz` in `bin/`; keine passende XML → manueller Import (Datei-Picker, z. B. USB-Stick mit Windows-DriverStore) |
| 5 Konverter-Umgebung | `python3 -m venv data/venv`, `pip install numpy scipy` mit gepinnten Versionen; `venv/meta.json` merkt Python-Version | Fortschritt, Hinweis auf ≈220 MB | pip scheitert → Retry; offline → Schritt später nachholen |
| 6 Konvertierung | für Profile × Voicings: `venv/bin/python defaults/converter/dolby_to_pipewire.py <xml> --profile <p> --variant <v> --output-dir data/presets/<p>/<v> --no-activate` mit `LV2_PATH` auf `bin/lv2`; danach Nachbearbeitung der `.conf` (Abschnitt 4.3) | Liste mit Häkchen pro Preset | einzelnes Preset fehlgeschlagen → markieren, Rest nutzbar |
| 7 Aktivierung | Unit schreiben, `systemctl --user enable --now ally-dsp.service`, Default „Game / Balanced“; Verifikation via `pw-dump` (Knoten `effect_input.*` vorhanden und mit Sink verlinkt) | „Fertig“, A/B-Knopf (Bypass) | Unit startet nicht → Log anzeigen, Bypass |

Dauer beim ersten Lauf: Download und venv dominieren, geschätzt 2–5 Minuten je nach Netz. Alle Schritte idempotent; „Setup erneut ausführen“ überspringt vorhandene Artefakte.

### 4.2 Presets und Voicings

| Dolby-Profil in der XML | Anzeige im Plugin | Bemerkung |
|---|---|---|
| `dynamic` | Dynamic (Auto) | Dolby-Default |
| `game` | Game | Standard nach Setup |
| `movie` | Movie | |
| `music` | Music | |
| `voice` | Voice | |
| `personalize_user1..3` | Custom 1–3 | Ally-X-Nutzer empfehlen unter Windows „Custom 1“ |
| `voice_onlinecourse`, `off` | ausgeblendet | `off` = Bypass-Funktion des Plugins |

Voicing (IEQ): Balanced (Default), Detailed, Warm → drei Varianten pro Profil, also 24 sichtbare Presets, 30 erzeugte.

Extras (erfordern Neukonvertierung, Sekunden): Volume Leveler (`--enable autogain`; Dolby-Leveler ist im Tuning ab Werk aus, dadurch unter Linux leiser als Windows; **Standard im Plugin: an**, im UI abschaltbar, bei hörbarem Pumpen ausschalten), Dialog-Enhancer aus (`--disable dialog`), Regulator aus (`--disable regulator`), Virtual Bass (experimentell, `--enable virtual-bass`). Ein Pre-Gain-Regler (±6 dB) wird direkt in der `.conf` gesetzt (Control `g_in` des Limiters oder ein `linear`-Builtin vor dem Limiter), ohne Neukonvertierung.

### 4.3 Nachbearbeitung der erzeugten `.conf`

Der Konverter liefert eine vollständige `context.modules`-Datei für `~/.config/pipewire/pipewire.conf.d/`. Für den eigenen Prozess wird sie zu einer eigenständigen Konfiguration zusammengesetzt:

```
context.properties = { log.level = 2 }
context.spa-libs   = { audio.convert.* = audioconvert/libspa-audioconvert  support.* = support/libspa-support }
context.modules = [
  { name = libpipewire-module-rt  flags = [ ifexists nofail ] }
  { name = libpipewire-module-protocol-native }
  { name = libpipewire-module-client-node }
  { name = libpipewire-module-adapter }
  { name = libpipewire-module-filter-chain  flags = [ ifexists nofail ]
    args = { … Kette aus dem Konverter …
      capture.props = {
        node.name = "effect_input.ally_dsp"   node.description = "Ally DSP · Game (Balanced)"
        media.class = Audio/Sink   priority.session = -1
        filter.smart = true   filter.smart.name = ally-dsp
        filter.smart.target = { node.name = "alsa_output.pci-0000_64_00.6.analog-stereo" }
        # filter.smart.after/before: Reihenfolge zu Valves Loopback-Filter im PoC bestimmen
      }
      playback.props = { node.name = "effect_output.ally_dsp"  node.passive = true  node.link-group = "ally_dsp" }
    } }
]
```

Regeln der Nachbearbeitung: IR-Pfad absolut auf `data/active/ir.irs` setzen; `filter.smart.target` aus `hardware.detect()` einsetzen (nur der PCI-Analog-Sink, nie Bluetooth/HDMI/USB); feste Knotennamen, damit Verifikation und WirePlumber-Regeln stabil bleiben; Kommentarkopf mit Preset, Voicing, Konverter-Commit, XML-Hash.

### 4.4 DSP-Laufzeit (`dsp_runtime.py`)

- Unit-Datei (Vorlage in `defaults/ally-dsp.service.tmpl`):

```
[Unit]
Description=Ally DSP speaker filter chain
After=pipewire.service wireplumber.service
BindsTo=pipewire.service
[Service]
Type=simple
Environment=LV2_PATH=%h/homebrew/plugins/Ally DSP/bin/lv2:/usr/lib/lv2
Environment=MALLOC_ARENA_MAX=1
ExecStart=/usr/bin/pipewire -c %h/homebrew/data/Ally DSP/active/chain.conf
Restart=on-failure
RestartSec=1
LimitMEMLOCK=102400K
Slice=session.slice
[Install]
WantedBy=default.target
```

- API: `apply(profile, voicing)` kopiert Preset atomar nach `active/` (Temp-Verzeichnis + `rename`), `systemctl --user restart ally-dsp.service`, wartet bis `pw-dump` den Knoten zeigt (Timeout 3 s), meldet Ergebnis per Event. `bypass(on)` stoppt oder startet die Unit. `status()` liefert aktiv/inaktiv, Preset, Uptime, letzte Fehlerzeile aus `journalctl --user -u ally-dsp`.
- Verhalten bei Decky-Reload: Unit läuft weiter (unabhängig), Backend liest Zustand beim Start. Bei `_uninstall`: Unit stoppen, deaktivieren, Datei entfernen.
- Valves Härtungen (`MemoryDenyWriteExecute`, Syscall-Filter) werden zunächst **nicht** übernommen, weil LSP gegen Cairo/X11 gelinkt ist; später einzeln testen.

### 4.5 Globale und Per-Game-Presets (`profiles.py` + Frontend)

Settings-Schema (`settings.json`):

```json
{
  "schema": 1,
  "enabled": true,
  "global": { "profile": "game", "voicing": "balanced" },
  "perApp": { "1245620": { "profile": "movie", "voicing": "warm", "enabled": true } },
  "extras": { "autogain": false, "dialog": true, "regulator": true, "virtualBass": false, "preGainDb": 0 },
  "update": { "channel": "stable", "lastCheck": 0, "latest": null, "autoCheck": true },
  "setup": { "done": true, "xmlSha256": "…", "packageVersion": "V11.130.1340.46", "converterCommit": "bde5653" }
}
```

Ablauf: Frontend registriert beim Laden eine MobX-Reaction auf `SteamUIStore.MainRunningAppID` und ruft `backend.on_running_app_changed(appId | null)`. Backend löst auf: `perApp[appId]` falls vorhanden und `enabled`, sonst `global`; wendet nur an, wenn sich Preset oder Voicing ändern (kein unnötiger Neustart). Beim Beenden (`null`) zurück zu global. Im QAM zeigt die Per-Game-Sektion das laufende Spiel (Name über `appStore.GetAppOverviewByAppID`), einen Schalter „Eigenes Preset für dieses Spiel“ und die Auswahl. Ohne laufendes Spiel: Liste der gespeicherten Per-Game-Einträge mit Löschen. Non-Steam-Shortcuts funktionieren über ihre App-ID genauso.

### 4.6 Kopfhörer-Erkennung (`jack_watch.py`)

Der 3,5-mm-Ausgang ist derselbe ALSA-Sink mit Routenwechsel (`analog-output-headphones`, aktuell `available=no`). Backend pollt `pw-dump` alle 2 s (oder verfolgt `pw-mon` als Subprozess) und stoppt die Unit, solange Kopfhörer aktiv sind; danach Wiederanlauf mit dem zuletzt aktiven Preset. Toast „Ally DSP pausiert (Kopfhörer)“. Bluetooth/HDMI/USB sind vom Smart-Filter-Target ohnehin ausgeschlossen.

### 4.7 Self-Update über GitHub Releases (`updater.py`)

Vorbild ist der Updater des Referenz-Plugins (WiFi Optimizer Streaming, Fork unter demselben GitHub-Konto wie dieses Projekt, Lizenz BSD-3-Clause mit Copyright Arcada Labs). Updater, minisign-Prüfung und Release-Workflow lassen sich daraus direkt übernehmen. Ein entscheidender Unterschied: Wir brauchen kein Root, weil die Installation an Decky delegiert wird.

1. **Prüfen**: `curl -fsSL` auf `https://api.github.com/repos/<owner>/<repo>/releases/latest` (Kanal „stable“). Versionsvergleich semver gegen `decky.DECKY_PLUGIN_VERSION`. Ergebnis 6 Stunden gecacht (GitHub erlaubt 60 anonyme Anfragen pro Stunde). Prüfung beim Öffnen des Panels, wenn `autoCheck`. Ein zweiter Kanal ist für v1 nicht vorgesehen; falls später gewünscht, als „Pre-Release“-Kanal über GitHub-Pre-Releases mit derselben signierten Pipeline (Abschnitt 10).
2. **Verifizieren im Backend**: Download von `SHA256SUMS` und `SHA256SUMS.minisig`; Signaturprüfung gegen den im Plugin gepinnten Public Key (pure-Python minisign/ed25519 nach dem Muster der Referenz; deren Lizenz ist BSD-3-Clause, Übernahme mit Namensnennung möglich); daraus die erwartete SHA-256 des Release-Zips lesen.
3. **Installieren über Decky**: Frontend ruft `window.DeckyBackend.callable('utilities/install_plugin')(zipUrl, "Ally DSP", version, sha256, InstallType.UPDATE)`. Decky zeigt den eigenen Bestätigungsdialog, lädt das Zip, prüft die SHA-256 selbst (Abbruch bei Abweichung), deinstalliert die alte Version, entpackt nach `~/homebrew/plugins/Ally DSP/`, setzt Rechte, lädt das Plugin neu. Kein `plugin_loader`-Neustart, kein Root. Hinweis: Decky versucht danach, einen Store-Zähler zu erhöhen, was für ein Nicht-Store-Plugin nur eine Logzeile erzeugt.
4. **Nach dem Update**: `_migration()` prüft `settings.schema`, `venv/meta.json` (Python-Version) und `converterCommit`; bei geändertem Konverter werden die Presets neu erzeugt (Nutzer wird gefragt).
5. **Erstinstallation**: `install.sh` wie im Referenzprojekt (`curl … | sudo bash`): lädt das neueste Release-Zip, prüft es gegen `SHA256SUMS`, entpackt nach `~/homebrew/plugins/Ally DSP/`, startet `plugin_loader` neu. Deckys Entwicklermodus „Install from URL“ bleibt nur als undokumentierter Notweg.

Sicherheitsregeln: nur HTTPS, `curl -f` mit Timeouts, Signatur vor Prüfsumme vor Inhalt, Zip nur an Decky übergeben (kein eigenes Entpacken), keine Interpolation von Nutzerdaten in Shell-Aufrufe (`subprocess` mit Argumentlisten).

### 4.8 Diagnose (`diagnostics.py`, eigene Route)

Ohne Root lesbar: Kernel-Version, Codec/SSID, TAS-Controls und Werte, Firmware-Dateien vorhanden, Unit-Status und letzte Log-Zeilen, `pw-dump`-Auszug (Sink, Filter-Knoten, Links, Route), `lv2ls`-Treffer für die drei LSP-URIs, Konverter- und venv-Version, DAX3-Provenienz, Quantum/Rate. Export als Textblock (Kopieren für Bug-Reports).

---

## 5. Repository-Struktur

```
decky-ally-dsp/
├── plugin.json                 # name "Ally DSP", flags [], api_version 1
├── package.json                # version = Release-Tag ohne "v"; remote_binary optional
├── main.py                     # Plugin-Klasse: dünne Fassade über py_modules/allydsp
├── py_modules/allydsp/         # Backend-Module (Abschnitt 3), pure Python 3.11
├── defaults/
│   ├── ally-dsp.service.tmpl
│   ├── converter/              # gepinnter Checkout von speaker-tuning-to-easyeffects (MIT)
│   └── fallback-sources.json   # gepinnte ASUS-URL + SHA-256 als API-Fallback
├── bin/lv2/lsp-plugins.lv2/    # DSP-Bibliothek + TTLs aus lsp-plugins-lv2 1.2.22 (LGPL-3), UI-Bibliothek entfernt
├── src/                        # Frontend: index.tsx, components/, hooks/, backend.ts, types.ts
├── tests/                      # pytest: ASUS-JSON-Parser, 7z-Offset, INF-Parser, semver, minisign-Vektoren, conf-Nachbearbeitung
├── scripts/                    # dev-deploy.sh (scp + reload), fetch-lsp.sh, package.sh
├── .github/workflows/release.yml
├── install.sh
├── minisign.pub
├── docs/
└── local/                      # git-ignoriert: XML, Presets, Testartefakte
```

LSP-Bündelung: CI lädt `lsp-plugins-lv2-1.2.22-1-x86_64.pkg.tar.zst` vom SteamOS-Spiegel (gepinnter SHA-256), entpackt nur `lsp-plugins-lv2.so`, `manifest.ttl` und die drei benötigten TTLs, legt LGPL-Text und Quellenhinweis bei. Alternative, um das Zip klein zu halten: Deckys `remote_binary` in `package.json` (Einträge `{name, url, sha256hash}`, Decky lädt sie beim Installieren nach `bin/` und prüft die SHA-256). **Entscheidung: direkt im Release-Zip bündeln** (reproduzierbar, offline installierbar, ≈15–20 MB).

---

## 6. Release-Pipeline (`release.yml`, nach Referenz)

1. Trigger: Tag `v*`. Prüfen, dass Tag = `package.json`-Version (sonst bietet der Updater ewig ein „Update“ an).
2. Build: `pnpm install --frozen-lockfile`, `pnpm build`, `tsc --noEmit`, `python3 -m compileall`, `pytest`, `pnpm audit --prod`.
3. LSP holen und prüfen (`scripts/fetch-lsp.sh`), Konverter-Checkout auf gepinnten Commit prüfen.
4. Zip mit Top-Level-Ordner `Ally DSP/` (Decky erwartet genau einen `plugin.json` eine Ebene tief), `SHA256SUMS` erzeugen.
5. `SHA256SUMS` mit minisign signieren (Seed als Repo-Secret), sofort gegen `minisign.pub` verifizieren.
6. `gh release create` mit Zip, `SHA256SUMS`, `SHA256SUMS.minisig`, generierten Notes.

---

## 7. Frontend-Skizze (QAM)

```
[Ally DSP]                                 ● aktiv · Game (Balanced)
  Setup nötig? → [Setup starten]           (nur bis Setup fertig)
  ─ Klang ─────────────────────────────────
  Preset (global)      [Game ▾]
  Voicing              [Balanced ▾]
  Bypass (A/B)         [  ○ ]
  ─ Dieses Spiel: Elden Ring ──────────────
  Eigenes Preset       [ ● ]   Preset [Movie ▾]  Voicing [Warm ▾]
  ─ Extras ────────────────────────────────
  Volume Leveler [ ○ ]  Dialog [ ● ]  Regulator [ ● ]  Pre-Gain [ 0 dB ]
  ─ Wartung ───────────────────────────────
  Update: v0.3.0 verfügbar   [Installieren]
  [Diagnose]  [Setup erneut]  [Log kopieren]
```

Backend-Methoden (per `callable`): `get_state`, `run_setup(step?)`, `cancel_setup`, `set_global(profile, voicing)`, `set_per_app(appId, entry|null)`, `on_running_app_changed(appId|null)`, `set_bypass(on)`, `set_extras(extras)` (löst Neukonvertierung aus), `check_for_update`, `prepare_update` (liefert verifizierte URL + SHA-256 für den Decky-Aufruf), `get_diagnostics`. Events (`decky.emit`): `setup_progress`, `dsp_state`, `update_state`, `toast`.

---

## 8. Meilensteine

| Meilenstein | Inhalt | Definition of Done | Aufwand |
|---|---|---|---|
| **M0 Gerüst** | Decky-Template, Repo-Layout, CI ohne Release, `dev-deploy.sh` (scp + `loader/reload_plugin`) | Leeres Plugin erscheint im QAM auf dem Ally | 1–2 Tage |
| **M1 Laufzeit-PoC** | Unit + `dsp_runtime.py` mit dem bereits erzeugten `Dolby_Balanced.conf`, LSP aus `bin/lv2`, Bypass-Schalter, Verifikation via `pw-dump` | Hörbarer Unterschied per A/B im Gaming-Modus; Reihenfolge zu Valves Loopback-Filter geklärt; Suspend/Resume und PipeWire-Neustart überstanden | 2–3 Tage |
| **M2 Setup-Wizard** | ASUS-API, Download mit SHA-256, 7z-Extraktion, venv, Konvertierung aller Presets, Provenienz, Fehlerpfade, manueller XML-Import | Frisches Gerät → fertiges Setup ohne Konsole | 3–5 Tage |
| **M3 Presets & Per-Game** | Preset/Voicing-UI, Per-Game-Reaction, Settings-Schema, Kopfhörer-Pause, Extras mit Neukonvertierung | Spielstart wechselt Preset automatisch; Kopfhörer pausieren die Kette | 3–4 Tage |
| **M4 Update & Release** | `updater.py` mit minisign, Decky-Install-Aufruf, `release.yml`, `install.sh`, `minisign.pub`, Beta-Kanal optional | v0.1.0 → v0.1.1 per Knopf im QAM aktualisiert, Signaturbruch wird abgelehnt | 2–3 Tage |
| **M5 Diagnose & Politur** | Diagnose-Route, Log-Export, Toasts, Lokalisierung DE/EN, README, Lizenzhinweise | Bug-Report-fähig, dokumentiert | 2–3 Tage |
| **M6 Beta** | Tests mit weiteren Ally-X/Ally-Nutzern, Messung Windows vs. Linux, Feinschliff Presets, Entscheidung Store-Einreichung | Feedback eingearbeitet | offen |

Empfohlene Reihenfolge: M1 vor M2, weil der Klanggewinn das Fundament rechtfertigt und die offenen Laufzeitfragen früh klärt.

---

## 9. Risiken und Gegenmaßnahmen

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| Reihenfolge/Interaktion mit Valves Loopback-Smart-Filter | Kette greift nicht oder doppelt | In M1 mit `pw-dump`/`pw-link -l` prüfen; `filter.smart.before/after` setzen; Fallback `target.object` |
| Systemd-User-Unit startet in der Gaming-Session nicht wie erwartet | Kein DSP nach Boot | `WantedBy=default.target`, `BindsTo=pipewire.service`; Backend prüft beim Start und repariert |
| SteamOS-Update ändert System-Python | venv kaputt, Konvertierung scheitert | `venv/meta.json` vergleicht Version, automatischer Neuaufbau; fertige Presets bleiben nutzbar |
| Anonyme GitHub-API-Limits | Update-Check scheitert | Cache 6 h, `-f`-Fehler still behandeln, manueller Check-Knopf |
| ASUS ändert API oder Paketstruktur | Setup scheitert | Gepinnter Fallback (URL + SHA-256), manueller XML-Import, klare Fehlermeldung |
| Klang ohne Dolby-Leveler leiser als Windows | Enttäuschung | Extras: Autogain, Pre-Gain; Dokumentation |
| LSP gegen Cairo/X11 gelinkt | Abhängigkeit von Systembibliotheken | Aktuell vorhanden (verifiziert); Diagnose meldet `ldd`-Fehler; alternativ später eigenes Faust-LV2 ohne UI-Abhängigkeiten |
| Lizenz/Redistribution | Rechtliches | XML nie ausliefern; LSP LGPL-3 mit Lizenztext und Quelle; Konverter MIT; Referenz-Code BSD-3-Clause mit Namensnennung |
| Decky-API-Änderungen (`utilities/install_plugin`) | Updater bricht | Fallback `install.sh`; Versionstest in CI gegen aktuellen Decky-Loader |

---

## 10. Entscheidungen (Stand 19.09.2026)

| # | Frage | Entscheidung |
|---|---|---|
| 1 | Name | **Ally DSP** |
| 2 | LSP-LV2 | **im Release-Zip bündeln** (kein `remote_binary`) |
| 3 | Beta-Kanal | **offen**, Empfehlung unten: v1 nur Stable, später optional Pre-Release-Kanal |
| 4 | Erstinstallation | **`install.sh` wie im Referenzprojekt** (sudo), kein Store-Release |
| 5 | Verteilung | **nur GitHub Releases** |
| 6 | Volume Leveler | **standardmäßig an**, im UI abschaltbar |

### 10.1 Beta-Kanal: was die Referenz macht und was ich empfehle

In der Referenz gibt es im Panel die Wahl „Stable / Beta“:

- **Stable** = letztes GitHub-Release (Tag `vX.Y.Z`). Geladen wird das CI-Zip, geprüft gegen `SHA256SUMS`, deren minisign-Signatur gegen den im Plugin gepinnten Schlüssel. Update nur, wenn die Version höher ist.
- **Beta** = Tarball des Git-Branches `beta` (`archive/refs/heads/beta.tar.gz`). Aktualisiert wird, sobald die Version **anders** ist (erlaubt also auch den Weg zurück zu Stable). Für Branch-Tarballs gibt es weder Prüfsumme noch Signatur; der Kanal vertraut nur TLS und dem Repo. Außerdem muss der Branch ein fertig gebautes `dist/index.js` enthalten, also Build-Artefakte im Git. Im Referenz-Repo existiert derzeit gar kein `beta`-Branch, der Kanal ist dort ein toter Pfad.

Nutzen eines Beta-Kanals: Tester bekommen Zwischenstände ohne offizielles Release. Kosten: zweiter, schwächer gesicherter Update-Pfad, Build-Artefakte im Git, mehr Support-Fälle („welche Version hast du?“).

**Empfehlung:** v1 nur Stable. Wenn Tester gebraucht werden, statt Branch-Tarballs einen **Pre-Release-Kanal** anbieten: Tag `v0.4.0-beta.1`, `gh release create --prerelease`, dieselbe signierte Pipeline. Der Schalter im Panel entscheidet nur, ob Pre-Releases berücksichtigt werden (`/releases` statt `/releases/latest`). Ein Code-Pfad, gleiche Sicherheit, kein `dist/` im Git.

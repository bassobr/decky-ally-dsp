"""The setup wizard's backend: hardware check, package resolution, download,
extraction, venv, conversion, activation. Shared by main.py and the CLI."""
from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, Optional

from . import asus_fetch, convert, dsp_runtime, hardware, paths, settings
from .constants import SUPPORTED_SSIDS
from .log import logger
from .util import read_json

STEPS = ["hardware", "resolve", "download", "extract", "venv", "convert", "activate"]
RANGES = {"hardware": (0, 3), "resolve": (3, 6), "download": (6, 30), "extract": (30, 35),
          "venv": (35, 60), "convert": (60, 95), "activate": (95, 100)}
Progress = Callable[[Dict[str, Any]], None]


class Cancelled(RuntimeError):
    pass


def _emit(progress: Progress, step: str, status: str, message: str, sub: float = 0.0, **extra) -> None:
    lo, hi = RANGES[step]
    pct = lo + (hi - lo) * max(0.0, min(1.0, sub / 100.0))
    if status == "done" or status == "skipped":
        pct = hi
    payload = {"step": step, "index": STEPS.index(step), "total": len(STEPS), "status": status,
               "message": message, "percent": round(pct, 1)}
    payload.update(extra)
    progress(payload)


def run_setup(progress: Progress, force: bool = False, use_network: bool = True, allow_unsupported: bool = False,
              cancel: Optional[Callable[[], bool]] = None, activate: bool = True) -> Dict[str, Any]:
    cancel = cancel or (lambda: False)

    def check_cancel():
        if cancel():
            raise Cancelled("setup cancelled")

    st = settings.load()

    # 1 hardware
    _emit(progress, "hardware", "running", "Reading codec and audio graph")
    hw = hardware.summary()
    codec = hw.get("codec")
    if not codec:
        raise RuntimeError("No Realtek HDA codec found in /proc/asound")
    if not codec["supported"] and not allow_unsupported:
        raise RuntimeError(f"Unsupported device: codec subsystem {codec['ssid']} (supported: {', '.join(SUPPORTED_SSIDS)})")
    sink = hw.get("sink")
    if not sink:
        raise RuntimeError("No internal analog PipeWire sink found (is PipeWire running?)")
    if not hw["tools"].get("7z") or not hw["tools"].get("curl"):
        raise RuntimeError("Required tools missing: 7z and curl must be available")
    lv2 = hardware.lv2_check()
    if not lv2["ok"]:
        raise RuntimeError(f"Bundled LV2 plugins not loadable: missing {lv2['missing']}")
    _emit(progress, "hardware", "done", f"{codec['codec']} · {codec.get('model') or codec['ssid']} · sink {sink['name']}")
    check_cancel()

    # 2 resolve
    _emit(progress, "resolve", "running", "Querying ASUS support API")
    pkg = asus_fetch.resolve_package(use_network=use_network)
    _emit(progress, "resolve", "done", f"{pkg.get('title')} {pkg.get('version')} ({pkg.get('source')})", package=pkg)
    check_cancel()

    # 3 download + 4 extract (skip if provenance matches)
    prov = asus_fetch.provenance()
    xml = asus_fetch.current_xml()
    same_pkg = bool(prov and xml and (prov.get("package") or {}).get("sha256") == pkg.get("sha256")
                    and (prov.get("codec") or {}).get("ssid") == codec["ssid"])
    if same_pkg and not force:
        _emit(progress, "download", "skipped", "Package already processed")
        _emit(progress, "extract", "skipped", prov.get("xml_name", ""))
    else:
        os.makedirs(paths.TMP_DIR, exist_ok=True)
        exe = os.path.join(paths.TMP_DIR, os.path.basename(pkg["url"]))
        _emit(progress, "download", "running", f"Downloading {pkg.get('title')} ({pkg.get('size_text') or ''})")
        size = pkg.get("size") if isinstance(pkg.get("size"), int) else None
        asus_fetch.download(pkg["url"], exe, pkg.get("sha256"), size,
                            progress=lambda pct, msg: (_emit(progress, "download", "running", msg, pct), check_cancel()))
        _emit(progress, "download", "done", "Download verified")
        check_cancel()
        _emit(progress, "extract", "running", "Extracting tuning XML")
        prov = asus_fetch.extract_dax3(exe, codec, progress=lambda pct, msg: _emit(progress, "extract", "running", msg, pct),
                                       package=pkg)
        try:
            os.unlink(exe)
        except OSError:
            pass
        xml = asus_fetch.current_xml()
        _emit(progress, "extract", "done", prov.get("xml_name", ""))
    check_cancel()

    # 5 venv
    _emit(progress, "venv", "running", "Preparing converter environment")
    convert.ensure_venv(progress=lambda pct, msg: (_emit(progress, "venv", "running", msg, pct), check_cancel()))
    if not convert.converter_ok():
        raise RuntimeError("Converter files missing from the plugin (defaults/converter)")
    _emit(progress, "venv", "done", "Converter ready")

    # 6 convert
    extras = st.get("extras", {})
    sig = settings.extras_signature(extras)
    presets = convert.list_presets()
    all_present = all(v for p in presets.values() for v in p.values())
    setup_prev = st.get("setup", {})
    if all_present and not force and setup_prev.get("extrasSignature") == sig \
            and setup_prev.get("xmlSha256") == (prov or {}).get("xml_sha256") \
            and setup_prev.get("targetSink") == sink["name"]:
        _emit(progress, "convert", "skipped", "Presets up to date")
        results = {}
    else:
        _emit(progress, "convert", "running", "Converting Dolby profiles")
        results = convert.convert_all(xml, sink["name"], extras,
                                      progress=lambda pct, msg: _emit(progress, "convert", "running", msg, pct),
                                      cancel=cancel)
        failed = {k: v for k, v in results.items() if v != "ok"}
        if len(failed) == len(results):
            raise RuntimeError("All conversions failed: " + next(iter(failed.values())))
        _emit(progress, "convert", "done", f"{len(results) - len(failed)} presets ready" + (f", {len(failed)} failed" if failed else ""))
    check_cancel()

    # 7 activate
    st = settings.load()
    st["setup"].update({"done": True, "xmlSha256": (prov or {}).get("xml_sha256"),
                        "packageVersion": pkg.get("version"), "converterVersion": convert.converter_version(),
                        "completedAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "extrasSignature": sig,
                        "targetSink": sink["name"]})
    settings.save(st)
    if activate:
        _emit(progress, "activate", "running", "Starting the filter chain")
        res = settings.resolve(st, None)
        dsp_runtime.ensure_unit()
        dsp_runtime.enable(True)
        active = dsp_runtime.apply_preset(res["profile"], res["voicing"], settings.clamp_pregain(extras.get("preGainDb", 0)))
        _emit(progress, "activate", "done", f"Active: {res['profile']} / {res['voicing']}" + ("" if active.get("verified") else " (node not verified yet)"))
    else:
        _emit(progress, "activate", "skipped", "Not activated")
    return {"ok": True, "codec": codec, "sink": sink, "package": pkg, "provenance": prov, "results": results}

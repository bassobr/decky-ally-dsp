"""Decky Loader entry point; async facade over py_modules/allydsp."""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
from typing import Any, Dict, Optional

import decky  # type: ignore

sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

from allydsp import asus_fetch, convert, diagnostics, dsp_runtime, hardware, paths, settings, setup_flow, updater  # noqa: E402
from allydsp.constants import PROFILES, VOICING_LABELS, VOICINGS  # noqa: E402
from allydsp.jackwatch import JackWatcher  # noqa: E402


class Plugin:
    # ---------------------------------------------------------------- lifecycle
    async def _main(self):
        self.loop = asyncio.get_event_loop()
        paths.ensure_dirs()
        self.settings: Dict[str, Any] = settings.load()
        self.running_app: Optional[str] = None
        self.setup_task: Optional[asyncio.Task] = None
        self.setup_cancel = False
        self.setup_last: Optional[Dict[str, Any]] = None
        self.convert_task: Optional[asyncio.Task] = None
        self.convert_last: Optional[Dict[str, Any]] = None
        self.lv2_cache: Optional[Dict[str, Any]] = None
        self.jack = JackWatcher(on_change=self._on_jack_change)
        self.jack.start(self._should_run)
        self.loop.create_task(self._startup())
        decky.logger.info("Ally DSP backend started (plugin dir %s)", paths.PLUGIN_DIR)

    async def _unload(self):
        tasks = [t for t in (getattr(self.jack, "_task", None), self.setup_task, self.convert_task) if t and not t.done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        decky.logger.info("Ally DSP backend unloaded (filter chain keeps running)")

    async def _uninstall(self):
        # Decky also calls this while replacing the plugin during an update.
        if updater.update_in_progress():
            decky.logger.info("update in progress: keeping unit and runtime data")
            return
        try:
            await asyncio.to_thread(dsp_runtime.remove_unit)
            shutil.rmtree(paths.RUNTIME_DIR, ignore_errors=True)
            decky.logger.info("uninstalled: unit removed, runtime data deleted")
        except Exception as e:
            decky.logger.error("uninstall cleanup failed: %s", e)

    async def _startup(self):
        try:
            if updater.update_in_progress():
                updater.clear_update_marker()
                await decky.emit("update_installed", {"version": decky.DECKY_PLUGIN_VERSION,
                                                      "autoRestart": bool(self.settings["update"].get("autoRestartSteam", True))})
            if self.settings["setup"].get("done"):
                await self._reconcile()
            if self.settings["update"].get("autoCheck", True):
                await self.check_for_update(False)
        except Exception as e:
            decky.logger.error("startup reconcile failed: %s", e)

    async def _reconcile(self) -> None:
        """Bring unit and active preset back after an update or lost data."""
        res = settings.resolve(self.settings, self.running_app)
        have_presets = any(v for p in convert.list_presets().values() for v in p.values())
        if not have_presets or not asus_fetch.current_xml() or not await asyncio.to_thread(convert.venv_ok):
            decky.logger.warning("setup data incomplete, running setup again")
            await self.run_setup(False, False)
            return
        await asyncio.to_thread(dsp_runtime.ensure_unit)
        if self.settings.get("enabled"):
            await asyncio.to_thread(dsp_runtime.enable, True)
            if not convert.preset_available(res["profile"], res["voicing"]):
                return
            active = dsp_runtime.active_meta() or {}
            if not os.path.isfile(dsp_runtime.ACTIVE_CONF) or active.get("profile") != res["profile"] \
                    or active.get("voicing") != res["voicing"]:
                await self._apply_current(force_restart=True)
            elif not await asyncio.to_thread(dsp_runtime.is_active):
                dump = await asyncio.to_thread(hardware.pw_dump)
                if not hardware.headphones_active(hardware.output_route(dump)):
                    await asyncio.to_thread(dsp_runtime.start)

    # ---------------------------------------------------------------- helpers
    def _should_run(self) -> bool:
        return bool(self.settings.get("enabled") and self.settings["setup"].get("done"))

    def _emit_threadsafe(self, event: str, payload: Any) -> None:
        self.loop.call_soon_threadsafe(lambda: self.loop.create_task(decky.emit(event, payload)))

    async def _on_jack_change(self, state: Dict[str, Any]):
        await decky.emit("dsp_state", await self._dsp_state())

    async def _dsp_state(self) -> Dict[str, Any]:
        st = await asyncio.to_thread(dsp_runtime.status, False)
        st["jack"] = self.jack.state()
        st["enabled_setting"] = bool(self.settings.get("enabled"))
        return st

    def _save(self) -> None:
        settings.save(self.settings)

    async def _apply_current(self, force_restart: bool = False) -> Optional[Dict[str, Any]]:
        """Apply the resolved preset; restart the unit only when it changes."""
        res = settings.resolve(self.settings, self.running_app)
        if not convert.preset_available(res["profile"], res["voicing"]):
            decky.logger.warning("preset %s/%s not available yet", res["profile"], res["voicing"])
            return None
        pregain = settings.clamp_pregain(self.settings["extras"].get("preGainDb", 0))
        active = dsp_runtime.active_meta() or {}
        unchanged = (active.get("profile") == res["profile"] and active.get("voicing") == res["voicing"]
                     and abs(float(active.get("preGainDb", 0) or 0) - pregain) < 1e-6)
        want_running = self._should_run() and not self.jack.paused
        if unchanged and not force_restart:
            if want_running and not await asyncio.to_thread(dsp_runtime.is_active):
                await asyncio.to_thread(dsp_runtime.start)
            return active
        result = await asyncio.to_thread(dsp_runtime.apply_preset, res["profile"], res["voicing"], pregain, want_running)
        if not want_running and await asyncio.to_thread(dsp_runtime.is_active):
            await asyncio.to_thread(dsp_runtime.stop)
        await decky.emit("dsp_state", await self._dsp_state())
        return result

    # ---------------------------------------------------------------- state
    async def get_state(self) -> Dict[str, Any]:
        dump = await asyncio.to_thread(hardware.pw_dump)
        codec = await asyncio.to_thread(hardware.codec_info)
        if self.lv2_cache is None:
            self.lv2_cache = await asyncio.to_thread(hardware.lv2_check)
        route = hardware.output_route(dump)
        setup = dict(self.settings["setup"])
        setup.update({
            "xmlPresent": bool(asus_fetch.current_xml()),
            "venvOk": await asyncio.to_thread(convert.venv_ok),
            "presets": convert.list_presets(),
            "inProgress": bool(self.setup_task and not self.setup_task.done()),
            "last": self.setup_last,
            "converting": bool(self.convert_task and not self.convert_task.done()),
            "convertLast": self.convert_last,
        })
        return {
            "version": decky.DECKY_PLUGIN_VERSION,
            "setup": setup,
            "hardware": {"codec": codec, "dmi": hardware.dmi(), "kernel": hardware.kernel(),
                         "sink": hardware.find_speaker_sink(dump), "route": route,
                         "headphones": hardware.headphones_active(route), "lv2": self.lv2_cache},
            "dsp": await self._dsp_state(),
            "settings": self.settings,
            "runningApp": {"appId": self.running_app, "resolved": settings.resolve(self.settings, self.running_app)},
            "update": updater.check(self.settings["update"], decky.DECKY_PLUGIN_VERSION, force=False)
            if self.settings["update"].get("latest") else {"currentVersion": decky.DECKY_PLUGIN_VERSION,
                                                              "updateAvailable": False, "latestVersion": None,
                                                              "error": self.settings["update"].get("error")},
            "profiles": [{"id": p, "label": l} for p, l in PROFILES],
            "voicings": [{"id": v, "label": VOICING_LABELS[v]} for v in VOICINGS],
        }

    # ---------------------------------------------------------------- setup
    async def run_setup(self, force: bool = False, allow_unsupported: bool = False) -> Dict[str, Any]:
        if self.setup_task and not self.setup_task.done():
            return {"started": False, "reason": "already running"}
        self.setup_cancel = False
        self.setup_last = None

        def progress(ev: Dict[str, Any]) -> None:
            self.setup_last = ev
            self._emit_threadsafe("setup_progress", ev)

        async def runner():
            try:
                await asyncio.to_thread(setup_flow.run_setup, progress, bool(force), True, bool(allow_unsupported),
                                        lambda: self.setup_cancel, True)
                self.settings = settings.load()
                self.lv2_cache = None
                ev = {"step": "finished", "status": "done", "message": "Setup complete", "percent": 100,
                      "index": len(setup_flow.STEPS), "total": len(setup_flow.STEPS)}
            except setup_flow.Cancelled:
                ev = {"step": "finished", "status": "cancelled", "message": "Setup cancelled", "percent": 0,
                      "index": len(setup_flow.STEPS), "total": len(setup_flow.STEPS)}
            except Exception as e:
                decky.logger.error("setup failed: %s", e)
                ev = {"step": (self.setup_last or {}).get("step", "hardware"), "status": "error", "message": str(e),
                      "percent": (self.setup_last or {}).get("percent", 0), "index": (self.setup_last or {}).get("index", 0),
                      "total": len(setup_flow.STEPS)}
            self.setup_last = ev
            await decky.emit("setup_progress", ev)
            await decky.emit("dsp_state", await self._dsp_state())

        self.setup_task = self.loop.create_task(runner())
        return {"started": True}

    async def cancel_setup(self) -> Dict[str, Any]:
        self.setup_cancel = True
        return {"cancelling": bool(self.setup_task and not self.setup_task.done())}

    async def get_setup_progress(self) -> Optional[Dict[str, Any]]:
        return self.setup_last

    async def import_xml(self, path: str) -> Dict[str, Any]:
        codec = await asyncio.to_thread(hardware.codec_info)
        if not codec:
            raise RuntimeError("no Realtek codec found")
        prov = await asyncio.to_thread(asus_fetch.import_xml, path, codec)
        return {"ok": True, "provenance": prov}

    # ---------------------------------------------------------------- presets
    async def set_global(self, profile: str, voicing: str) -> Dict[str, Any]:
        if not (settings.valid_profile(profile) and settings.valid_voicing(voicing)):
            raise ValueError("invalid profile or voicing")
        self.settings["global"] = {"profile": profile, "voicing": voicing}
        self._save()
        await self._apply_current()
        return {"ok": True, "resolved": settings.resolve(self.settings, self.running_app)}

    async def set_per_app(self, app_id: str, entry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        app_id = str(app_id)
        per = self.settings.setdefault("perApp", {})
        if entry is None:
            per.pop(app_id, None)
        else:
            if not (settings.valid_profile(entry.get("profile")) and settings.valid_voicing(entry.get("voicing"))):
                raise ValueError("invalid profile or voicing")
            per[app_id] = {"profile": entry["profile"], "voicing": entry["voicing"],
                           "enabled": bool(entry.get("enabled", True)), "name": str(entry.get("name", ""))[:80]}
        self._save()
        if self.running_app == app_id:
            await self._apply_current()
        return {"ok": True, "perApp": per}

    async def on_running_app_changed(self, app_id: Optional[str]) -> Dict[str, Any]:
        new = str(app_id) if app_id not in (None, "", "0", 0) else None
        if new != self.running_app:
            self.running_app = new
            decky.logger.info("running app changed: %s", new)
            if self._should_run():
                await self._apply_current()
        return {"appId": self.running_app, "resolved": settings.resolve(self.settings, self.running_app)}

    async def set_enabled(self, enabled: bool) -> Dict[str, Any]:
        self.settings["enabled"] = bool(enabled)
        self._save()
        if enabled:
            await asyncio.to_thread(dsp_runtime.ensure_unit)
            await asyncio.to_thread(dsp_runtime.enable, True)
            await self._apply_current(force_restart=True)
        else:
            await asyncio.to_thread(dsp_runtime.stop)
            await asyncio.to_thread(dsp_runtime.enable, False)
        state = await self._dsp_state()
        await decky.emit("dsp_state", state)
        return state

    async def set_extras(self, extras: Dict[str, Any]) -> Dict[str, Any]:
        old = dict(self.settings["extras"])
        new = dict(old)
        for k in ("autogain", "dialog", "regulator", "virtualBass"):
            if k in extras:
                new[k] = bool(extras[k])
        if "preGainDb" in extras:
            new["preGainDb"] = settings.clamp_pregain(extras["preGainDb"])
        self.settings["extras"] = new
        self._save()
        if settings.extras_signature(new) != settings.extras_signature(old):
            await self._start_reconvert()
        elif abs(float(new.get("preGainDb", 0)) - float(old.get("preGainDb", 0))) > 1e-6:
            await self._apply_current()
        return {"ok": True, "extras": new, "reconverting": bool(self.convert_task and not self.convert_task.done())}

    async def _start_reconvert(self) -> None:
        if self.convert_task and not self.convert_task.done():
            return
        xml = asus_fetch.current_xml()
        sink = self.settings["setup"].get("targetSink")
        if not xml or not sink:
            return

        def progress(pct: float, msg: str) -> None:
            self.convert_last = {"percent": pct, "message": msg, "status": "running"}
            self._emit_threadsafe("convert_progress", self.convert_last)

        async def runner():
            try:
                await asyncio.to_thread(convert.convert_all, xml, sink, self.settings["extras"], progress)
                self.settings["setup"]["extrasSignature"] = settings.extras_signature(self.settings["extras"])
                self._save()
                self.convert_last = {"percent": 100, "message": "Presets regenerated", "status": "done"}
                await self._apply_current(force_restart=True)
            except Exception as e:
                decky.logger.error("reconvert failed: %s", e)
                self.convert_last = {"percent": 0, "message": str(e), "status": "error"}
            await decky.emit("convert_progress", self.convert_last)

        self.convert_task = self.loop.create_task(runner())

    # ---------------------------------------------------------------- updates
    async def check_for_update(self, force: bool = False) -> Dict[str, Any]:
        res = await asyncio.to_thread(updater.check, self.settings["update"], decky.DECKY_PLUGIN_VERSION, bool(force))
        self._save()
        await decky.emit("update_state", res)
        return res

    async def set_update_prefs(self, prefs: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("autoRestartSteam", "autoCheck"):
            if key in prefs:
                self.settings["update"][key] = bool(prefs[key])
        self._save()
        return dict(self.settings["update"])

    async def prepare_update(self) -> Dict[str, Any]:
        latest = self.settings["update"].get("latest")
        if not latest:
            latest = await asyncio.to_thread(updater.fetch_latest)
            self.settings["update"]["latest"] = latest
            self._save()
        info = await asyncio.to_thread(updater.verify_release, latest)
        updater.mark_update_pending()
        return info

    # ---------------------------------------------------------------- diagnostics
    async def get_diagnostics(self) -> Dict[str, Any]:
        d = await asyncio.to_thread(diagnostics.collect)
        text = diagnostics.render_text(d)
        try:
            os.makedirs(paths.LOG_DIR, exist_ok=True)
            with open(os.path.join(paths.LOG_DIR, "diagnostics.txt"), "w", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass
        return {"text": text}

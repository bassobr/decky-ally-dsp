import asyncio
import importlib.util
import logging
import os
import sys
import types

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)


def _load_main(monkeypatch):
    decky = types.ModuleType("decky")
    decky.logger = logging.getLogger("decky-test")
    decky.DECKY_PLUGIN_VERSION = "0.0.0"

    async def emit(event, *args):
        pass

    decky.emit = emit
    monkeypatch.setitem(sys.modules, "decky", decky)
    spec = importlib.util.spec_from_file_location("ally_main", os.path.join(ROOT, "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _finishes_without_suspending(coro) -> bool:
    try:
        coro.send(None)
    except StopIteration:
        return True
    coro.close()
    return False


def test_stop_hooks_never_wait_on_the_event_loop(monkeypatch):
    main = _load_main(monkeypatch)
    scheduled = []
    monkeypatch.setattr(main.dsp_runtime, "schedule_removal", lambda: scheduled.append(1) or True)
    loop = asyncio.new_event_loop()
    try:
        p = main.Plugin()
        p.jack = main.JackWatcher()
        p.jack._task = loop.create_task(asyncio.sleep(3600))
        p.setup_task = p.convert_task = p.update_task = None
        assert _finishes_without_suspending(p._unload())
        loop.run_until_complete(asyncio.sleep(0))
        assert p.jack._task.cancelled()
        assert _finishes_without_suspending(p._uninstall()) and scheduled == [1]
    finally:
        loop.close()

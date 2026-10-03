from allydsp import settings, updater


def test_resolve_prefers_enabled_app_entry():
    s = settings._merge(settings.DEFAULTS, {"global": {"profile": "music", "voicing": "warm"},
                                            "perApp": {"42": {"profile": "movie", "voicing": "detailed"},
                                                       "43": {"profile": "voice", "voicing": "balanced", "enabled": False},
                                                       "44": {"profile": "bogus", "voicing": "balanced"}}})
    assert settings.resolve(s, "42") == {"profile": "movie", "voicing": "detailed", "source": "app", "appId": "42"}
    assert settings.resolve(s, "43")["source"] == "global"
    assert settings.resolve(s, "44")["profile"] == "music"
    assert settings.resolve(s, None) == {"profile": "music", "voicing": "warm", "source": "global", "appId": None}


def test_defaults_merge_and_clamp():
    s = settings._merge(settings.DEFAULTS, {"extras": {"autogain": False}, "unknown": 1})
    assert s["extras"]["dialog"] is True and s["extras"]["autogain"] is False and s["unknown"] == 1
    assert settings.clamp_pregain(99) == 6.0 and settings.clamp_pregain("x") == 0.0
    sig_a = settings.extras_signature({"autogain": True, "dialog": True, "regulator": True, "virtualBass": False, "preGainDb": 3})
    sig_b = settings.extras_signature({"autogain": True, "dialog": True, "regulator": True, "virtualBass": False, "preGainDb": -3})
    assert sig_a == sig_b  # pre-gain does not require reconversion
    assert sig_a != settings.extras_signature({"autogain": False})


def test_version_compare_and_sums():
    assert updater.parse_version("v1.2.3") == (1, 2, 3)
    assert updater.parse_version("0.1") == (0, 1, 0)
    assert updater.is_newer("0.2.0", "0.1.9") and not updater.is_newer("0.1.0", "0.1.0")
    assert not updater.is_newer("0.1.0-beta.1", "0.1.0")
    sums = updater.parse_sums("abc\n" + "a" * 64 + "  ally-dsp-0.1.0.zip\n" + "b" * 64 + " *other.zip\n")
    assert sums == {"ally-dsp-0.1.0.zip": "a" * 64, "other.zip": "b" * 64}


def test_update_check_can_read_only_the_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(updater, "fetch_latest", lambda: calls.append(1) or {"version": "9.9.9"})
    state = {"latest": {"version": "0.2.0", "html_url": "u"}, "lastCheck": 0}  # stale cache
    res = updater.check(state, "0.1.0", fetch=False)
    assert calls == [] and res["updateAvailable"] and res["latestVersion"] == "0.2.0"
    assert updater.check_due(state)


def test_failed_update_check_waits_before_retry(monkeypatch):
    def offline():
        raise RuntimeError("offline")
    monkeypatch.setattr(updater, "fetch_latest", offline)
    state = {"latest": None, "lastCheck": 0}
    res = updater.check(state, "0.1.0")
    assert res["error"] == "offline" and not res["updateAvailable"]
    assert not updater.check_due(state)
    assert updater.check_due(state, now=state["lastAttempt"] + updater.UPDATE_RETRY_S)


def test_backend_save_keeps_setup_written_by_setup_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.paths, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    backend = settings.load()  # the backend's copy, taken while setup still runs
    settings.update_section("setup", {"done": True, "targetSink": "sink"})  # setup_flow finishes
    backend["enabled"] = False
    settings.save_keeping(backend, "setup")  # a toggle in the panel
    disk = settings.load()
    assert disk["setup"]["done"] is True and disk["setup"]["targetSink"] == "sink"
    assert disk["enabled"] is False and backend["setup"]["done"] is True


def test_legacy_marker_removed(tmp_path, monkeypatch):
    marker = tmp_path / ".update-pending"
    marker.write_text("0")
    monkeypatch.setattr(updater, "LEGACY_UPDATE_MARKER", str(marker))
    updater.remove_legacy_marker()
    updater.remove_legacy_marker()
    assert not marker.exists()

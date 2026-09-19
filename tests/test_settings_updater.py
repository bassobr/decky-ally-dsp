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

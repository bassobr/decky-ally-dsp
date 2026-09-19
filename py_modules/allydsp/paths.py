"""Filesystem layout. Under Decky the DECKY_* variables win; the CLI falls back
to the standard Decky locations so both share one on-disk state."""
from __future__ import annotations

import os

from .constants import PLUGIN_NAME


def _plugin_dir_default() -> str:
    here = os.path.dirname(os.path.abspath(__file__))  # .../py_modules/allydsp
    return os.path.abspath(os.path.join(here, os.pardir, os.pardir))


HOME = os.environ.get("DECKY_USER_HOME") or os.path.expanduser("~")
USER = os.environ.get("DECKY_USER") or os.environ.get("USER") or "deck"
PLUGIN_DIR = os.environ.get("ALLYDSP_PLUGIN_DIR") or os.environ.get("DECKY_PLUGIN_DIR") or _plugin_dir_default()
SETTINGS_DIR = os.environ.get("DECKY_PLUGIN_SETTINGS_DIR") or os.path.join(HOME, "homebrew", "settings", PLUGIN_NAME)
RUNTIME_DIR = os.environ.get("DECKY_PLUGIN_RUNTIME_DIR") or os.path.join(HOME, "homebrew", "data", PLUGIN_NAME)
LOG_DIR = os.environ.get("DECKY_PLUGIN_LOG_DIR") or os.path.join(HOME, "homebrew", "logs", PLUGIN_NAME)

SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")
DAX3_DIR = os.path.join(RUNTIME_DIR, "dax3")
VENV_DIR = os.path.join(RUNTIME_DIR, "venv")
PRESETS_DIR = os.path.join(RUNTIME_DIR, "presets")
ACTIVE_DIR = os.path.join(RUNTIME_DIR, "active")
TMP_DIR = os.path.join(RUNTIME_DIR, "tmp")
PROVENANCE_FILE = os.path.join(DAX3_DIR, "provenance.json")

DEFAULTS_DIR = os.path.join(PLUGIN_DIR, "defaults")
CONVERTER_DIR = os.path.join(DEFAULTS_DIR, "converter")
LV2_DIR = os.path.join(PLUGIN_DIR, "bin", "lv2")
UNIT_TEMPLATE = os.path.join(DEFAULTS_DIR, "ally-dsp.service.tmpl")
FALLBACK_SOURCES = os.path.join(DEFAULTS_DIR, "fallback-sources.json")
CONVERTER_REQUIREMENTS = os.path.join(DEFAULTS_DIR, "converter-requirements.txt")
PUBKEY_FILE = os.path.join(PLUGIN_DIR, "minisign.pub")

UNIT_NAME = "ally-dsp.service"
UNIT_PATH = os.path.join(HOME, ".config", "systemd", "user", UNIT_NAME)
SYSTEM_PYTHON = "/usr/bin/python3"


def ensure_dirs() -> None:
    for d in (SETTINGS_DIR, RUNTIME_DIR, DAX3_DIR, PRESETS_DIR, ACTIVE_DIR, TMP_DIR, LOG_DIR,
              os.path.dirname(UNIT_PATH)):
        os.makedirs(d, exist_ok=True)

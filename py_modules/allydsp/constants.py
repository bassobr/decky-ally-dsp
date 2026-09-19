"""Static configuration shared by backend, CLI and tests."""
from __future__ import annotations

PLUGIN_NAME = "Ally DSP"
GITHUB_REPO = "bassobr/decky-ally-dsp"
RELEASE_ZIP_TEMPLATE = "ally-dsp-{version}.zip"
USER_AGENT = "ally-dsp/decky (+https://github.com/bassobr/decky-ally-dsp)"

# Realtek HDA codec subsystem IDs the Dolby package carries a speaker tuning for.
SUPPORTED_SSIDS = {
    "10431384": "ROG Xbox Ally X (RC73XA)",
    "10431394": "ROG Xbox Ally (RC73YA)",
}

# Dolby profile ids in the DAX3 XML and their labels in the UI, in display order.
PROFILES = [
    ("game", "Game"),
    ("dynamic", "Dynamic"),
    ("movie", "Movie"),
    ("music", "Music"),
    ("voice", "Voice"),
    ("personalize_user1", "Custom 1"),
    ("personalize_user2", "Custom 2"),
    ("personalize_user3", "Custom 3"),
]
PROFILE_IDS = [p for p, _ in PROFILES]
PROFILE_LABELS = dict(PROFILES)
VOICINGS = ["balanced", "detailed", "warm"]
VOICING_LABELS = {"balanced": "Balanced", "detailed": "Detailed", "warm": "Warm"}
DEFAULT_PROFILE = "game"
DEFAULT_VOICING = "balanced"

# LV2 plugins the converted chain needs; bundled in bin/lv2 (LGPL-3, see THIRD_PARTY_LICENSES.md).
LSP_URIS = [
    "http://lsp-plug.in/plugins/lv2/para_equalizer_x16_lr",
    "http://lsp-plug.in/plugins/lv2/mb_compressor_stereo",
    "http://lsp-plug.in/plugins/lv2/limiter_stereo",
    "http://lsp-plug.in/plugins/lv2/autogain_stereo",
    "http://lsp-plug.in/plugins/lv2/filter_stereo",
]
# Virtual bass additionally needs Calf (not bundled); the option is offered only if Calf is installed system-wide.
CALF_SATURATOR_URI = "http://calf.sourceforge.net/plugins/Saturator"

# Node names inside the generated PipeWire filter chain.
NODE_BASE = "ally_dsp"
INPUT_NODE = f"effect_input.{NODE_BASE}"
OUTPUT_NODE = f"effect_output.{NODE_BASE}"
SMART_FILTER_NAME = "ally-dsp"

UPDATE_CHECK_INTERVAL_S = 6 * 3600
PREGAIN_MIN_DB = -6.0
PREGAIN_MAX_DB = 6.0

import subprocess

from allydsp import dsp_runtime


def _removal(tmp_path, monkeypatch, plugin_installed):
    plugin_dir = tmp_path / "plugins" / "Ally DSP"
    runtime_dir = tmp_path / "data" / "Ally DSP"
    unit_path = tmp_path / "systemd" / "ally-dsp.service"
    plugin_dir.mkdir(parents=True)
    (runtime_dir / "venv").mkdir(parents=True)
    unit_path.parent.mkdir()
    unit_path.write_text("[Unit]\n")
    if plugin_installed:
        (plugin_dir / "plugin.json").write_text("{}")
    calls = tmp_path / "systemctl.log"
    stub = tmp_path / "bin" / "systemctl"
    stub.parent.mkdir()
    stub.write_text(f'#!/bin/sh\necho "$@" >> "{calls}"\n')
    stub.chmod(0o755)
    monkeypatch.setattr(dsp_runtime.paths, "PLUGIN_DIR", str(plugin_dir))
    monkeypatch.setattr(dsp_runtime.paths, "UNIT_PATH", str(unit_path))
    monkeypatch.setattr(dsp_runtime.paths, "RUNTIME_DIR", str(runtime_dir))
    cmd = dsp_runtime.removal_command("ally-dsp-removal-test")
    assert cmd[:2] == ["systemd-run", "--user"] and f"--on-active={dsp_runtime.REMOVAL_DELAY_S}" in cmd
    subprocess.run(cmd[cmd.index("/bin/sh"):], check=True, env={"PATH": f"{stub.parent}:/usr/bin:/bin"})
    return runtime_dir, unit_path, calls


def test_removal_keeps_everything_when_plugin_is_back(tmp_path, monkeypatch):
    runtime_dir, unit_path, calls = _removal(tmp_path, monkeypatch, plugin_installed=True)
    assert runtime_dir.is_dir() and unit_path.is_file() and not calls.exists()


def test_removal_cleans_up_after_real_uninstall(tmp_path, monkeypatch):
    runtime_dir, unit_path, calls = _removal(tmp_path, monkeypatch, plugin_installed=False)
    assert not runtime_dir.exists() and not unit_path.exists()
    assert calls.read_text().splitlines() == ["--user disable --now ally-dsp.service", "--user daemon-reload"]

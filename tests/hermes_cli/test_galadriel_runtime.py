from __future__ import annotations

from pathlib import Path

import pytest

from hermes_cli import galadriel_runtime as gr


def test_oral_written_split_keeps_written_clean(monkeypatch):
    monkeypatch.setattr(gr, "load_config", lambda: {"voice": {"pronunciations": {"Scorpheus": "Scorpféuss"}}})

    split = gr.extract_oral_written_split("à l'oral bonjour Scorpheus et à l'écrit Galadriel")

    assert split == ("Bonjour Scorpféuss.", "Galadriel.")


def test_spoken_summary_falls_back_to_reply_excerpt(monkeypatch):
    monkeypatch.setattr(gr, "load_config", lambda: {"voice": {"pronunciations": {"Scorpheus": "Scorpféuss"}}})

    payload = gr.derive_spoken_summary("résume", "Bonjour, Scorpheus. Le détail reste écrit.")

    assert payload["source"] == "reply_excerpt"
    assert payload["spoken_summary"].startswith("Bonjour, Scorpféuss")
    assert payload["display_spoken_summary"].startswith("Bonjour, Scorpheus")


def test_galadriel_project_root_detects_companion_layout(tmp_path, monkeypatch):
    project = tmp_path / "GaladrielCompanionApp"
    home = project / "hermes_core" / "home"
    home.mkdir(parents=True)
    monkeypatch.setattr(gr, "get_hermes_home", lambda: home)
    monkeypatch.delenv("GALADRIEL_PROJECT_ROOT", raising=False)

    assert gr._project_root_from_home() == project.resolve()


def test_galadriel_diagnostics_shape_with_mocked_checks(tmp_path, monkeypatch):
    project = tmp_path / "GaladrielCompanionApp"
    assets = project / "hermes_core" / "home" / "galadriel" / "avatar-assets" / "app-galadriel-frames"
    assets.mkdir(parents=True)
    for idx in range(2):
        (assets / f"frame_r00_c0{idx}.png").write_bytes(b"png")
    data = project / "data"
    data.mkdir()
    (data / "galadriel_state.db").write_bytes(b"")

    home = project / "hermes_core" / "home"
    config = home / "config.yaml"
    config.write_text(
        "model:\n  provider: local_llama\n  default: honcho-qwen14b-128k-q4\n"
        "memory:\n  provider: honcho\n  memory_enabled: true\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(gr, "get_hermes_home", lambda: home)
    monkeypatch.setattr(gr, "get_config_path", lambda: config)
    monkeypatch.setattr(gr, "_http_health", lambda url, timeout=1.5: {"ok": True, "url": url})
    monkeypatch.setattr(gr, "_import_available", lambda module, symbol=None: {"ok": True, "module": module})

    payload = gr.build_galadriel_diagnostics()

    assert payload["ok"] is True
    assert payload["project_root"] == str(project.resolve())
    assert payload["checks"]["config"]["memory_provider"] == "honcho"
    assert payload["checks"]["avatar_assets"]["frame_count"] == 2
    assert payload["checks"]["data_paths"]["state_db_exists"] is True

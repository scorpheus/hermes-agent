from __future__ import annotations

from pathlib import Path

import pytest

from hermes_cli import galadriel_runtime as gr


def test_oral_written_split_keeps_written_clean(monkeypatch):
    monkeypatch.setattr(gr, "load_config", lambda: {"voice": {"pronunciations": {"Scorpheus": "Skorféuss"}}})

    split = gr.extract_oral_written_split("à l'oral bonjour Scorpheus et à l'écrit Galadriel")

    assert split == ("Bonjour Skorféuss.", "Galadriel.")


def test_spoken_summary_falls_back_to_reply_excerpt(monkeypatch):
    monkeypatch.setattr(gr, "load_config", lambda: {"voice": {"pronunciations": {"Scorpheus": "Skorféuss"}}})

    payload = gr.derive_spoken_summary("résume", "Bonjour, Scorpheus. Le détail reste écrit.")

    assert payload["source"] == "reply_excerpt"
    assert payload["spoken_summary"].startswith("Bonjour, Skorféuss")
    assert payload["display_spoken_summary"].startswith("Bonjour, Scorpheus")


def test_spoken_summary_filters_screen_only_technical_details(monkeypatch):
    monkeypatch.setattr(gr, "load_config", lambda: {"voice": {"pronunciations": {"Scorpheus": "Skorféuss"}}})

    reply = """
    C:\\Users\\scorp\\Documents\\Projets_Perso\\GaladrielCompanionApp\\hermes_core\\hermes-agent\\apps\\desktop\\src\\lib\\voice-playback.ts
    changed_files: ["hermes_cli/galadriel_runtime.py"]
    C’est prêt, Scorpheus. Les détails techniques restent affichés à l’écran.
    """

    payload = gr.derive_spoken_summary("résume", reply)

    assert payload["spoken_summary"] == "C’est prêt, Skorféuss. Les détails techniques restent affichés à l’écran."
    assert "C:\\" not in payload["spoken_summary"]
    assert "changed_files" not in payload["spoken_summary"]


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
    monkeypatch.setattr(gr, "_runtime_log_probe", lambda project_root: {"ok": True, "files_scanned": 0})
    monkeypatch.setattr(gr, "_vehigraph_runtime_probe", lambda: {"ok": True, "repo_exists": False})
    monkeypatch.setattr(gr, "_kanban_db_probe", lambda: {"ok": True, "exists": False})

    payload = gr.build_galadriel_diagnostics()

    assert payload["ok"] is True
    assert payload["project_root"] == str(project.resolve())
    assert payload["checks"]["config"]["memory_provider"] == "honcho"
    assert payload["checks"]["avatar_assets"]["frame_count"] == 2
    assert payload["checks"]["data_paths"]["state_db_exists"] is True
    assert "runtime_logs" in payload["checks"]
    assert "vehigraph_runtime" in payload["checks"]
    assert "kanban_db" in payload["checks"]


def test_runtime_log_probe_flags_backend_disconnect_signatures(tmp_path, monkeypatch):
    project = tmp_path / "GaladrielCompanionApp"
    home = project / "hermes_core" / "home"
    logs = home / "logs"
    data_logs = project / "data" / "logs"
    logs.mkdir(parents=True)
    data_logs.mkdir(parents=True)
    (logs / "desktop.log").write_text(
        "2026-06-24 10:40: compacting context\n"
        "2026-06-24 10:41: Hermes backend exited (3221225477)\n",
        encoding="utf-8",
    )
    (data_logs / "hermes-desktop-dev.log").write_text("Error: read ECONNRESET\n", encoding="utf-8")
    monkeypatch.setattr(gr, "get_hermes_home", lambda: home)

    probe = gr._runtime_log_probe(project)

    assert probe["ok"] is False
    assert probe["matches"]["backend_exit"] == 1
    assert probe["matches"]["windows_access_violation"] == 1
    assert probe["matches"]["electron_connection_reset"] == 1


def test_kanban_db_probe_counts_tasks_read_only(tmp_path, monkeypatch):
    db = tmp_path / "kanban.db"
    import sqlite3

    conn = sqlite3.connect(db)
    try:
        conn.execute("create table tasks (id text, status text, updated_at real)")
        conn.executemany(
            "insert into tasks values (?, ?, ?)",
            [("a", "running", 0), ("b", "blocked", 1), ("c", "blocked", 2)],
        )
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setenv("HERMES_KANBAN_DB", str(db))

    probe = gr._kanban_db_probe()

    assert probe["ok"] is True
    assert probe["task_counts"] == {"blocked": 2, "running": 1}
    assert probe["stale_running_count"] == 1


def test_debug_report_persists_payload(tmp_path, monkeypatch):
    home = tmp_path / "GaladrielCompanionApp" / "hermes_core" / "home"
    home.mkdir(parents=True)
    monkeypatch.setattr(gr, "get_hermes_home", lambda: home)
    monkeypatch.setattr(gr, "build_galadriel_diagnostics", lambda: {"ok": True, "checks": {}})

    result = gr.build_galadriel_debug_report(crash_dir=tmp_path / "reports")

    report_path = Path(result["path"])
    assert result["ok"] is True
    assert report_path.exists()
    assert '"source": "native_desktop_backend"' in report_path.read_text(encoding="utf-8")

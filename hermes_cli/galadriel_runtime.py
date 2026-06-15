"""Galadriel runtime helpers for the desktop/dashboard backend.

This module absorbs the useful read-only/runtime pieces that previously lived in
Scorpheus' external Galadriel Companion bridge: local service diagnostics,
voice/speech text preparation, and Galadriel asset discovery.  It deliberately
stays side-effect-light so it can be called from the clean Hermes dashboard
backend without starting the legacy bridge.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import yaml

from hermes_cli.config import get_config_path, get_hermes_home, load_config


_LOCAL_SERVICE_URLS = {
    "honcho": "http://127.0.0.1:8000/health",
    "local_llm": "http://127.0.0.1:8080/health",
    "embeddings": "http://127.0.0.1:8081/health",
}

_ORAL_PRONUNCIATIONS = {
    "Scorpheus": "Skorféuss",
}


def _http_health(url: str, timeout: float = 1.5) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=timeout) as response:
            body = response.read(1200).decode("utf-8", "replace")
            parsed: Any
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = body
            return {"ok": 200 <= response.status < 300, "status": response.status, "body": parsed}
    except (OSError, URLError, TimeoutError) as exc:
        return {"ok": False, "error": str(exc)}


def _project_root_from_home() -> Path | None:
    """Best-effort GaladrielCompanionApp root detection.

    In Scorpheus' layout HERMES_HOME is
    ``<project>/hermes_core/home``.  Stock Hermes installs won't have this
    wrapper root, so return None instead of inventing one.
    """
    explicit = os.environ.get("GALADRIEL_PROJECT_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()

    home = get_hermes_home().resolve()
    if home.name == "home" and home.parent.name == "hermes_core":
        return home.parent.parent
    return None


def _python_executable() -> Path:
    return Path(sys.executable).resolve()


def _import_available(module_name: str, symbol_name: str | None = None) -> dict[str, Any]:
    code = (
        "import importlib\n"
        f"m=importlib.import_module({module_name!r})\n"
        + (f"assert hasattr(m, {symbol_name!r}), {symbol_name!r}\n" if symbol_name else "")
        + "print('ok')\n"
    )
    try:
        proc = subprocess.run(
            [str(_python_executable()), "-c", code],
            cwd=str(Path(__file__).resolve().parent.parent),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=6,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()[-500:]}
    return {"ok": True}


def _config_probe() -> dict[str, Any]:
    try:
        path = get_config_path()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        voice = data.get("voice") or {}
        tts = data.get("tts") or {}
        stt = data.get("stt") or {}
        memory = data.get("memory") or {}
        provider = data.get("model", {}).get("provider") if isinstance(data.get("model"), dict) else None
        model = data.get("model", {}).get("default") if isinstance(data.get("model"), dict) else None
        return {
            "ok": True,
            "path": str(path),
            "model_provider": provider,
            "model_default": model,
            "voice_enabled": voice.get("enabled"),
            "voice_tts": voice.get("tts"),
            "voice_auto_tts": voice.get("auto_tts"),
            "pronunciations": voice.get("pronunciations") or {},
            "tts_provider": tts.get("provider"),
            "tts_edge_voice": (tts.get("edge") or {}).get("voice"),
            "stt_provider": stt.get("provider"),
            "stt_model": (stt.get("local") or {}).get("model"),
            "stt_language": (stt.get("local") or {}).get("language"),
            "memory_provider": memory.get("provider"),
            "memory_enabled": memory.get("memory_enabled"),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _avatar_assets_probe(project_root: Path | None) -> dict[str, Any]:
    if project_root is None:
        return {"ok": False, "error": "Galadriel project root not detected"}
    assets = project_root / "hermes_core" / "home" / "galadriel" / "avatar-assets"
    frames = assets / "app-galadriel-frames"
    if not assets.exists():
        return {"ok": False, "path": str(assets), "error": "Avatar assets directory not found"}
    frame_count = len(list(frames.glob("frame_*.png"))) if frames.exists() else 0
    return {
        "ok": True,
        "path": str(assets),
        "frames_path": str(frames),
        "frame_count": frame_count,
        "spritesheet": str(assets / "app-galadriel-spritesheet.webp"),
        "spritesheet_exists": (assets / "app-galadriel-spritesheet.webp").exists(),
    }


def _data_paths_probe(project_root: Path | None) -> dict[str, Any]:
    if project_root is None:
        return {"ok": False, "error": "Galadriel project root not detected"}
    data = project_root / "data"
    state_db = data / "galadriel_state.db"
    return {
        "ok": data.exists(),
        "path": str(data),
        "state_db": str(state_db),
        "state_db_exists": state_db.exists(),
        "crash_reports": str(data / "crash_reports"),
        "crash_reports_exists": (data / "crash_reports").exists(),
        "attachments": str(data / "attachments"),
        "attachments_exists": (data / "attachments").exists(),
        "audio": str(data / "audio"),
        "audio_exists": (data / "audio").exists(),
    }


def build_galadriel_diagnostics() -> dict[str, Any]:
    """Return a native diagnostics payload replacing the bridge health panel.

    The payload is intentionally read-only and safe to call from the Desktop
    backend.  It checks local services, config, optional voice modules, and the
    Galadriel-specific asset/data roots when this install has them.
    """
    project_root = _project_root_from_home()
    checks: dict[str, dict[str, Any]] = {
        "desktop_backend": {"ok": True, "detail": "Native Hermes dashboard backend is serving Galadriel diagnostics"},
        "hermes_python": {"ok": _python_executable().exists(), "path": str(_python_executable())},
        "config": _config_probe(),
        "tts_module": _import_available("tools.tts_tool", "text_to_speech_tool"),
        "stt_module": _import_available("tools.transcription_tools", "transcribe_audio"),
        "avatar_assets": _avatar_assets_probe(project_root),
        "data_paths": _data_paths_probe(project_root),
    }
    for name, url in _LOCAL_SERVICE_URLS.items():
        checks[name] = _http_health(url)

    return {
        "ok": all(bool(item.get("ok")) for item in checks.values()),
        "name": "Galadriel Runtime Diagnostics",
        "hermes_home": str(get_hermes_home()),
        "project_root": str(project_root) if project_root is not None else None,
        "checks": checks,
    }


def build_galadriel_debug_report(*, crash_dir: Path | None = None) -> dict[str, Any]:
    """Persist a local Galadriel runtime report for post-mortem inspection."""
    project_root = _project_root_from_home()
    if crash_dir is None:
        if project_root is None:
            raise RuntimeError("Galadriel project root not detected")
        crash_dir = project_root / "data" / "crash_reports"
    crash_dir.mkdir(parents=True, exist_ok=True)
    report_id = time.strftime("report_%Y%m%d_%H%M%S") + f"_{uuid.uuid4().hex[:6]}"
    path = crash_dir / f"{report_id}.json"
    payload = {
        "ok": True,
        "report_id": report_id,
        "created_at": time.time(),
        "source": "native_desktop_backend",
        "diagnostics": build_galadriel_diagnostics(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "report_id": report_id, "path": str(path)}


def _configured_pronunciations() -> dict[str, str]:
    pronunciations = dict(_ORAL_PRONUNCIATIONS)
    try:
        cfg = load_config()
        configured = ((cfg.get("voice") or {}).get("pronunciations") or {}) if isinstance(cfg, dict) else {}
        if isinstance(configured, dict):
            for written, spoken in configured.items():
                if isinstance(written, str) and isinstance(spoken, str) and written and spoken:
                    pronunciations[written] = spoken
    except Exception:
        pass
    return pronunciations


def apply_oral_pronunciations(text: str) -> str:
    """Apply written→spoken substitutions for TTS only.

    This preserves clean written UI text while letting the configured voice say
    Scorpheus and other local names naturally.
    """
    spoken_text = text
    for written, spoken in _configured_pronunciations().items():
        spoken_text = spoken_text.replace(written, spoken)
    return spoken_text


def spoken_to_display(text: str) -> str:
    display = text
    for written, spoken in _configured_pronunciations().items():
        display = display.replace(spoken, written)
    return display


def _clean_split_channel_phrase(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip(" ,;:.!?\n\t")
    cleaned = re.sub(r"\b(?:et|puis)$", "", cleaned, flags=re.IGNORECASE).strip(" ,;:.!?\n\t")
    if not cleaned:
        return ""
    if cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    if cleaned[-1] not in ".!?…":
        cleaned += "."
    return cleaned


def extract_oral_written_split(user_message: str) -> tuple[str, str] | None:
    """Parse explicit Galadriel tests such as: oral A / écrit B."""
    normalized = re.sub(r"\s+", " ", user_message).strip()
    if len(normalized) > 260:
        return None
    oral_marker = r"(?:à|a)\s+l['’]?oral|oralement"
    written_marker = r"(?:à|a)\s+l['’]?[ée]crit|par\s+[ée]crit|[ée]crit"

    written_match = None
    oral_match = None
    for candidate in re.finditer(written_marker, normalized, flags=re.IGNORECASE):
        previous_orals = [
            marker
            for marker in re.finditer(oral_marker, normalized[: candidate.start()], flags=re.IGNORECASE)
        ]
        if previous_orals:
            written_match = candidate
            oral_match = previous_orals[-1]
            break
    if written_match is None or oral_match is None:
        return None

    oral = _clean_split_channel_phrase(normalized[oral_match.end() : written_match.start()])
    written = _clean_split_channel_phrase(normalized[written_match.end() :])
    if not oral or not written:
        return None
    return apply_oral_pronunciations(oral), written


_TECHNICAL_LINE_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|(?:^|\s)/(?:mnt|home|tmp|var|etc|Users)/|[\\/][\w.-]+[\\/][\w.-]+|"
    r"\b(?:traceback|diff --git|@@|changed_files|tests_run|metadata|json|stdout|stderr|exit_code)\b|"
    r"^\s*(?:[-*+]\s*)?[\w./\\-]+\.(?:py|ts|tsx|js|json|yaml|yml|md|toml)(?::\d+)?)",
    re.IGNORECASE,
)


def _strip_technical_oral_details(text: str) -> str:
    """Remove details that belong on screen, not in Galadriel's spoken channel."""
    without_blocks = re.sub(r"```[\s\S]*?```", " ", text)
    without_urls = re.sub(r"https?://\S+", "", without_blocks)
    lines = []
    for raw_line in without_urls.splitlines():
        line = raw_line.strip()
        if not line or _TECHNICAL_LINE_RE.search(line):
            continue
        lines.append(line)
    cleaned = " ".join(lines)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"[*_#>]+", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def reply_excerpt_for_spoken_summary(assistant_reply: str, *, max_chars: int = 180) -> str:
    text = _strip_technical_oral_details(assistant_reply)
    if not text:
        return apply_oral_pronunciations("J’ai préparé la réponse, Scorpheus. Le texte complet reste affiché à l’écran.")
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    summary = sentences[0].strip()
    if len(summary) < 40 and len(sentences) > 1:
        summary = f"{summary} {sentences[1].strip()}"
    words = summary.split()
    if len(words) > 30:
        summary = " ".join(words[:30]).rstrip(" ,;:") + "…"
    if len(summary) > max_chars:
        summary = summary[: max_chars - 1].rstrip() + "…"
    return apply_oral_pronunciations(summary)


def derive_spoken_summary(user_message: str, assistant_reply: str) -> dict[str, str]:
    split = extract_oral_written_split(user_message)
    if split is not None:
        spoken, written = split
        return {"spoken_summary": spoken, "display_spoken_summary": written, "source": "explicit_split"}
    spoken = reply_excerpt_for_spoken_summary(assistant_reply)
    return {"spoken_summary": spoken, "display_spoken_summary": spoken_to_display(spoken), "source": "reply_excerpt"}

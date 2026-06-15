"""Tests for optional local-LLM post-processing of STT transcripts."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def tiny_wav(tmp_path):
    path = tmp_path / "voice.wav"
    path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    return str(path)


def test_postprocess_disabled_returns_raw_transcript_without_http_call():
    from tools.transcription_tools import _maybe_postprocess_transcription_result

    result = {"success": True, "transcript": "galadrielle et oncho", "provider": "local"}

    with patch("requests.post", side_effect=AssertionError("HTTP should not be called")):
        processed = _maybe_postprocess_transcription_result(result, {"postprocess": {"enabled": False}})

    assert processed is result
    assert processed["transcript"] == "galadrielle et oncho"
    assert "raw_transcript" not in processed


def test_postprocess_enabled_uses_local_llama_and_preserves_raw_transcript():
    from tools.transcription_tools import _maybe_postprocess_transcription_result

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [
            {"message": {"content": "Galadriel et Honcho"}}
        ]
    }
    result = {"success": True, "transcript": "galadrielle et oncho", "provider": "local"}
    stt_config = {
        "postprocess": {
            "enabled": True,
            "base_url": "http://127.0.0.1:8080/v1",
            "model": "honcho-qwen14b-128k-q4",
            "timeout": 7,
            "glossary": ["Galadriel", "Honcho"],
        }
    }

    with patch("requests.post", return_value=response) as mock_post:
        processed = _maybe_postprocess_transcription_result(result, stt_config)

    assert processed is result
    assert processed["raw_transcript"] == "galadrielle et oncho"
    assert processed["transcript"] == "Galadriel et Honcho"
    assert processed["postprocessed_by"] == "local_llama"
    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["timeout"] == 7
    assert kwargs["json"]["model"] == "honcho-qwen14b-128k-q4"
    prompt = kwargs["json"]["messages"][1]["content"]
    assert "Galadriel" in prompt
    assert "Honcho" in prompt
    assert "galadrielle et oncho" in prompt


def test_postprocess_failure_keeps_raw_transcript_and_records_error():
    from tools.transcription_tools import _maybe_postprocess_transcription_result

    response = MagicMock()
    response.status_code = 500
    response.text = "server exploded"
    result = {"success": True, "transcript": "texte brut", "provider": "local"}

    with patch("requests.post", return_value=response):
        processed = _maybe_postprocess_transcription_result(
            result,
            {"postprocess": {"enabled": True}},
        )

    assert processed["transcript"] == "texte brut"
    assert processed["raw_transcript"] == "texte brut"
    assert "postprocess_error" in processed


def test_transcribe_audio_applies_postprocess_to_local_provider(tiny_wav):
    from tools.transcription_tools import transcribe_audio

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{"message": {"content": "Galadriel parle de Vehigraph"}}]
    }
    stt_config = {
        "enabled": True,
        "provider": "local",
        "local": {"model": "large-v3", "language": "fr"},
        "postprocess": {"enabled": True},
    }

    with patch("tools.transcription_tools._load_stt_config", return_value=stt_config), \
         patch("tools.transcription_tools._HAS_FASTER_WHISPER", True), \
         patch(
             "tools.transcription_tools._transcribe_local",
             return_value={"success": True, "transcript": "galadrielle parle de véigraph", "provider": "local"},
         ), \
         patch("requests.post", return_value=response):
        result = transcribe_audio(tiny_wav)

    assert result["raw_transcript"] == "galadrielle parle de véigraph"
    assert result["transcript"] == "Galadriel parle de Vehigraph"
    assert result["postprocessed_by"] == "local_llama"

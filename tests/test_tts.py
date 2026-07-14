"""
Unit tests for the TTS Lambda handler.
Tests script cleaning, SSML generation, and Polly integration.
"""
import sys
import os
import re
import importlib
import pytest


def _load_tts_handler():
    """Load TTS handler via importlib to avoid handler.py name collision."""
    spec = importlib.util.spec_from_file_location(
        "tts_handler",
        os.path.join(os.path.dirname(__file__), "..", "services", "tts", "handler.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestScriptCleaning:
    """Tests for cleaning scripts before TTS."""

    def test_removes_timestamps(self):
        """Should remove [MM:SS] and [HH:MM:SS] timestamps."""
        mod = _load_tts_handler()
        script = "[00:00] Hello world. [00:15] Second line. [01:30:00] Third."
        result = mod.clean_script_for_tts(script)
        assert "[00:00]" not in result
        assert "[00:15]" not in result
        assert "Hello world" in result
        assert "Second line" in result

    def test_removes_delivery_cues(self):
        """Should remove [pause], [emphasis], [slower], [faster]."""
        mod = _load_tts_handler()
        script = "This is important. [pause] Really important. [emphasis] Very much so. [slower] Take it in."
        result = mod.clean_script_for_tts(script)
        assert "[pause]" not in result
        assert "[emphasis]" not in result
        assert "[slower]" not in result
        assert "This is important" in result

    def test_collapses_whitespace(self):
        """Should collapse excessive whitespace."""
        mod = _load_tts_handler()
        script = "Line one.\n\n\n\n\nLine two."
        result = mod.clean_script_for_tts(script)
        assert "\n\n\n" not in result
        assert "Line one" in result
        assert "Line two" in result

    def test_preserves_narration_text(self, sample_script):
        """Should keep the actual narration words intact."""
        mod = _load_tts_handler()
        result = mod.clean_script_for_tts(sample_script)
        assert "Python" in result
        assert "programming language" in result
        assert "subscribe" in result


class TestSSMLGeneration:
    """Tests for SSML script conversion."""

    def test_wraps_in_speak_tags(self):
        """SSML output should be wrapped in <speak> tags."""
        mod = _load_tts_handler()
        ssml = mod.script_to_ssml("Hello world. This is a test.")
        assert ssml.startswith("<speak>")
        assert ssml.endswith("</speak>")

    def test_includes_prosody(self):
        """SSML should include prosody rate and volume."""
        mod = _load_tts_handler()
        ssml = mod.script_to_ssml("Hello world.", rate="fast", volume="loud")
        assert 'rate="fast"' in ssml
        assert 'volume="loud"' in ssml

    def test_adds_paragraph_breaks(self):
        """SSML should wrap paragraphs in <p> tags."""
        mod = _load_tts_handler()
        ssml = mod.script_to_ssml("Paragraph one.\n\nParagraph two.")
        assert "<p>" in ssml
        assert "Paragraph one." in ssml
        assert "Paragraph two." in ssml

    def test_adds_break_between_paragraphs(self):
        """SSML should include breaks between paragraphs."""
        mod = _load_tts_handler()
        ssml = mod.script_to_ssml("Para one.\n\nPara two.")
        assert '<break time="500ms"/>' in ssml

    def test_default_rate_is_medium(self):
        """Default prosody rate should be medium."""
        mod = _load_tts_handler()
        ssml = mod.script_to_ssml("Test.")
        assert 'rate="medium"' in ssml

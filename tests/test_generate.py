"""
Unit tests for the Generation Lambda handler.
Tests prompt loading, JSON parsing, and S3 output.
"""
import sys
import os
import json
import importlib
import pytest
from pathlib import Path


# Use importlib to avoid sys.path collision with other handler.py files
def _load_generate_handler():
    """Load generate handler explicitly to avoid name collision."""
    spec = importlib.util.spec_from_file_location(
        "generate_handler",
        os.path.join(os.path.dirname(__file__), "..", "services", "generate", "handler.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPromptTemplates:
    """Verify all prompt templates exist and are valid."""

    PROMPTS_DIR = Path(__file__).parent.parent / "services" / "generate" / "prompts"

    @pytest.mark.parametrize("prompt_name", [
        "system", "plan", "script", "metadata", "captions", "render_plan"
    ])
    def test_prompt_file_exists(self, prompt_name):
        """Each prompt template file should exist."""
        path = self.PROMPTS_DIR / f"{prompt_name}.txt"
        assert path.exists(), f"Missing prompt template: {prompt_name}.txt"

    @pytest.mark.parametrize("prompt_name", [
        "system", "plan", "script", "metadata", "captions", "render_plan"
    ])
    def test_prompt_file_not_empty(self, prompt_name):
        """Each prompt template should have content."""
        path = self.PROMPTS_DIR / f"{prompt_name}.txt"
        content = path.read_text(encoding="utf-8")
        assert len(content) > 50, f"Prompt {prompt_name}.txt seems too short"

    def test_plan_prompt_has_placeholders(self):
        """Plan prompt should contain required format placeholders."""
        content = (self.PROMPTS_DIR / "plan.txt").read_text(encoding="utf-8")
        assert "{source_text}" in content
        assert "{target_duration_sec}" in content
        assert "{tone}" in content

    def test_script_prompt_has_placeholders(self):
        """Script prompt should contain required format placeholders."""
        content = (self.PROMPTS_DIR / "script.txt").read_text(encoding="utf-8")
        assert "{plan_json}" in content
        assert "{tone}" in content

    def test_metadata_prompt_has_placeholders(self):
        """Metadata prompt should contain required format placeholders."""
        content = (self.PROMPTS_DIR / "metadata.txt").read_text(encoding="utf-8")
        assert "{script}" in content
        assert "{audience}" in content

    def test_captions_prompt_has_placeholders(self):
        """Captions prompt should contain required format placeholders."""
        content = (self.PROMPTS_DIR / "captions.txt").read_text(encoding="utf-8")
        assert "{script}" in content
        assert "{target_duration_sec}" in content


class TestJsonParsing:
    """Test JSON extraction from Nova responses."""

    def _parse(self, text):
        mod = _load_generate_handler()
        return mod.parse_json_response(text)

    def test_parse_clean_json(self):
        """Should parse clean JSON strings."""
        result = self._parse('{"title": "Test", "scenes": []}')
        assert result["title"] == "Test"

    def test_parse_json_with_markdown_fences(self):
        """Should strip markdown fences and parse JSON."""
        result = self._parse('```json\n{"title": "Test", "scenes": []}\n```')
        assert result["title"] == "Test"

    def test_parse_json_with_plain_fences(self):
        """Should strip plain fences and parse JSON."""
        result = self._parse('```\n{"key": "value"}\n```')
        assert result["key"] == "value"

    def test_parse_invalid_json_raises(self):
        """Should raise on invalid JSON."""
        with pytest.raises(json.JSONDecodeError):
            self._parse("this is not json")


class TestS3Output:
    """Test S3 artifact saving."""

    def _save(self, job_id, filename, content):
        mod = _load_generate_handler()
        return mod.save_to_s3(job_id, filename, content)

    def test_save_to_s3(self, mock_aws_services):
        """save_to_s3 should write content to the renders bucket."""
        s3_key = self._save("test-job-001", "test.json", '{"hello": "world"}')
        assert s3_key == "test-job-001/test.json"

        obj = mock_aws_services["s3"].get_object(
            Bucket="eyeread-renders-test", Key=s3_key
        )
        body = json.loads(obj["Body"].read().decode("utf-8"))
        assert body["hello"] == "world"

    def test_save_multiple_artifacts(self, mock_aws_services):
        """Should save multiple artifacts under the same job_id."""
        self._save("test-job-001", "plan.json", '{"plan": true}')
        self._save("test-job-001", "script.md", "# Script")
        self._save("test-job-001", "metadata.json", '{"meta": true}')

        s3 = mock_aws_services["s3"]
        for key in ["plan.json", "script.md", "metadata.json"]:
            obj = s3.get_object(Bucket="eyeread-renders-test", Key=f"test-job-001/{key}")
            assert obj["Body"].read()

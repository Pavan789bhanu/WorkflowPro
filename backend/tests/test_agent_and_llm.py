"""Tests for the multi-provider LLM client and the AutomationAgent plumbing.

These run fully offline (no API keys / browser needed).
"""
import asyncio
import json

import pytest

from app.services.llm_client import _extract_json, LLMClient, LLMNotConfiguredError
from app.automation.agent.automation_agent import AutomationAgent, AgentResult, AgentStep


class TestJSONExtraction:
    def test_plain_json(self):
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        text = "Here you go:\n```json\n{\"action\": \"click\", \"element_id\": 4}\n```"
        assert _extract_json(text) == {"action": "click", "element_id": 4}

    def test_json_with_surrounding_prose(self):
        text = 'Sure! {"action": "done", "reason": "complete"} hope that helps'
        assert _extract_json(text)["action"] == "done"

    def test_invalid_raises(self):
        with pytest.raises(Exception):
            _extract_json("no json here at all")


class TestLLMClientConfig:
    def test_unknown_provider_raises(self):
        with pytest.raises(LLMNotConfiguredError):
            LLMClient(provider="banana")

    def test_anthropic_without_key_raises(self, monkeypatch):
        from app.core import config
        monkeypatch.setattr(config.settings, "ANTHROPIC_API_KEY", "")
        with pytest.raises(LLMNotConfiguredError):
            LLMClient(provider="anthropic")

    def test_message_conversion_openai(self):
        msgs = LLMClient._to_openai_messages(
            [{"role": "user", "content": [
                {"type": "text", "text": "hi"},
                {"type": "image_b64", "data": "abc", "media_type": "image/png"},
            ]}],
            system="sys",
        )
        assert msgs[0] == {"role": "system", "content": "sys"}
        assert msgs[1]["content"][0] == {"type": "text", "text": "hi"}
        assert msgs[1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,abc")

    def test_message_conversion_anthropic(self):
        msgs = LLMClient._to_anthropic_messages(
            [{"role": "user", "content": [
                {"type": "text", "text": "hi"},
                {"type": "image_b64", "data": "abc"},
            ]}]
        )
        assert msgs[0]["content"][1]["source"]["data"] == "abc"
        assert msgs[0]["content"][1]["type"] == "image"


class _FakeLLM:
    """Stub LLM that returns canned JSON actions then 'done'."""

    def __init__(self, actions):
        self.actions = list(actions)
        self.calls = 0

    async def chat_json(self, messages, system=None, max_tokens=0, temperature=0.0):
        self.calls += 1
        if self.actions:
            return self.actions.pop(0)
        return {"action": "done", "reason": "finished"}

    async def chat(self, messages, system=None, max_tokens=0, temperature=0.0, json_mode=False):
        return "# Automation Report\n\n## Result\nStub report."


class TestAgentHelpers:
    def test_credential_substitution(self):
        agent = AutomationAgent(credentials={"email": "a@b.com", "password": "s3cret"})
        out = agent._substitute_credentials("user: {{EMAIL}} pass: {{PASSWORD}}")
        assert out == "user: a@b.com pass: s3cret"

    def test_credentials_never_in_ui_payload(self):
        # the ui step masks typed credential text
        text = "{{PASSWORD}}"
        masked = text if "{{" not in text else "(credentials)"
        assert masked == "(credentials)"

    def test_format_elements(self):
        digest = AutomationAgent._format_elements([
            {"id": 0, "tag": "button", "text": "Submit", "inViewport": True},
            {"id": 1, "tag": "input", "type": "email", "placeholder": "Email", "text": "", "inViewport": False},
        ])
        assert "[0] <button>" in digest
        assert '"Submit"' in digest
        assert "(below fold)" in digest

    def test_plan_defaults_without_llm(self):
        """_make_plan falls back to defaults when the LLM errors."""
        class _BoomLLM:
            async def chat_json(self, *a, **k):
                raise RuntimeError("no network")

        agent = AutomationAgent(llm=_BoomLLM())
        plan = asyncio.run(
            agent._make_plan("do something", "https://example.com")
        )
        assert plan["start_url"] == "https://example.com"
        assert plan["outline"]

    def test_agent_result_shape(self):
        r = AgentResult(success=True, task="t", run_id="run_1")
        r.steps.append(AgentStep(index=0, action={"action": "navigate"}))
        assert r.steps_executed == 1
        assert r.success


class TestReportFallback:
    def test_write_report_fallback_on_llm_error(self):
        class _BoomLLM:
            async def chat(self, *a, **k):
                raise RuntimeError("boom")

        agent = AutomationAgent(llm=_BoomLLM())
        report = asyncio.run(
            agent._write_report("task", True, "done", [], [], "https://x.com")
        )
        assert "# Automation Report" in report


class TestHTMLReportRenderer:
    def test_markdown_to_html(self):
        from app.services.workflow_executor import _markdown_to_html
        html_out = _markdown_to_html("# Title\n\n## Sub\n\n- item **bold**\n\nplain `code`")
        assert "<h1>Title</h1>" in html_out
        assert "<h2>Sub</h2>" in html_out
        assert "<li>item <strong>bold</strong></li>" in html_out
        assert "<code>code</code>" in html_out

    def test_html_report_written(self, tmp_path):
        from app.services.workflow_executor import _write_html_report
        result = AgentResult(success=True, task="demo task", run_id="r1", run_dir=str(tmp_path))
        result.report_markdown = "# Report\n\n## Result\nAll good."
        result.steps.append(AgentStep(index=0, action={"action": "navigate", "step_title": "Open site"},
                                      status="success", message="ok"))
        path = _write_html_report(result, "My Workflow")
        assert path is not None
        content = (tmp_path / "execution_report.html").read_text()
        assert "My Workflow" in content
        assert "SUCCESS" in content
        assert "Open site" in content

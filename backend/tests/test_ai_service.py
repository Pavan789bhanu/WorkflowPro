"""Unit tests for AIService — intent inference, URL extraction, and workflow helpers.

All tests run fully offline; no API keys, browser, or network required.
"""
import asyncio
import pytest

from app.services.ai_service import AIService, ai_service
from app.services.llm_client import _extract_json


# ---------------------------------------------------------------------------
# _extract_json  (regression + new edge cases)
# ---------------------------------------------------------------------------

class TestExtractJsonEdgeCases:
    def test_prose_after_json_containing_braces(self):
        """Strategy 3 (depth-tracking) must win when trailing prose has braces."""
        text = '{"action": "click"} See the note (it was created in {2024} by {team})'
        result = _extract_json(text)
        assert result == {"action": "click"}

    def test_nested_objects_survive(self):
        text = '{"outer": {"inner": 1}, "key": "value"}'
        assert _extract_json(text) == {"outer": {"inner": 1}, "key": "value"}

    def test_string_with_brace_inside_value(self):
        """Braces inside a JSON string must not confuse the depth counter."""
        text = '{"msg": "use {placeholder} here"}'
        assert _extract_json(text)["msg"] == "use {placeholder} here"

    def test_fenced_with_braces_in_prose(self):
        text = "Here:\n```json\n{\"x\": 1}\n```\nsome {trailing} text"
        assert _extract_json(text) == {"x": 1}

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Empty"):
            _extract_json("")

    def test_no_json_at_all_raises(self):
        with pytest.raises(ValueError):
            _extract_json("plain text, no braces at all")


# ---------------------------------------------------------------------------
# _infer_app_from_intent
# ---------------------------------------------------------------------------

class TestInferAppFromIntent:
    def setup_method(self):
        self.svc = AIService()

    def test_explicit_medium_mention(self):
        app, url, reason = self.svc._infer_app_from_intent("summarize articles on Medium")
        assert app == "Medium"
        assert "medium.com" in url

    def test_google_doc_mention(self):
        app, url, reason = self.svc._infer_app_from_intent("open a Google doc and write something")
        assert app == "Google Docs"
        assert "docs.google.com" in url

    def test_google_sheet_mention(self):
        app, url, reason = self.svc._infer_app_from_intent("create a Google sheet for Q1 data")
        assert app == "Google Sheets"
        assert "sheets.google.com" in url

    def test_app_name_in_url_mapping(self):
        """Any app in APP_URL_MAPPING should be found by pattern 3."""
        app, url, reason = self.svc._infer_app_from_intent("post something to LinkedIn")
        assert app is not None
        assert url is not None

    def test_no_app_identified(self):
        app, url, reason = self.svc._infer_app_from_intent("do something vague")
        assert app is None
        assert url is None
        assert "Unable" in reason

    def test_spreadsheet_inference(self):
        app, url, reason = self.svc._infer_app_from_intent("create a spreadsheet for my budget")
        assert app == "Google Sheets"

    def test_create_document_inference(self):
        app, url, reason = self.svc._infer_app_from_intent("create a document for my notes")
        assert app == "Google Docs"

    def test_case_insensitive(self):
        app, url, _ = self.svc._infer_app_from_intent("MEDIUM article summarize")
        assert app == "Medium"


# ---------------------------------------------------------------------------
# _extract_url_from_query
# ---------------------------------------------------------------------------

class TestExtractUrlFromQuery:
    def setup_method(self):
        self.svc = AIService()

    def test_explicit_https_url(self):
        url = self.svc._extract_url_from_query("login to https://myapp.example.com/auth")
        assert url == "https://myapp.example.com/auth"

    def test_explicit_url_strips_trailing_punctuation(self):
        url = self.svc._extract_url_from_query("go to https://example.com.")
        assert url == "https://example.com"

    def test_bare_domain(self):
        url = self.svc._extract_url_from_query("open myapp.com dashboard")
        assert url == "https://myapp.com"

    def test_known_app_name_fallback(self):
        url = self.svc._extract_url_from_query("search in github")
        assert url is not None and "github" in url

    def test_no_url_returns_none(self):
        url = self.svc._extract_url_from_query("do something vague with no site mentioned")
        assert url is None


# ---------------------------------------------------------------------------
# _decompose_intent
# ---------------------------------------------------------------------------

class TestDecomposeIntent:
    def setup_method(self):
        self.svc = AIService()

    def test_create_document_intent(self):
        intent = self.svc._decompose_intent("Create a Google document named My Project")
        assert "create" in intent["actions"]
        assert intent["object_type"] == "document"
        assert intent["app_name"] == "Google Docs"

    def test_login_intent(self):
        intent = self.svc._decompose_intent("login to my account on GitHub")
        assert "login" in intent["actions"]

    def test_search_intent(self):
        intent = self.svc._decompose_intent("find articles about machine learning on Medium")
        assert "search" in intent["actions"] or "read" in intent["actions"]

    def test_name_extraction(self):
        intent = self.svc._decompose_intent("Create a project named Q1 Planning and describe goals")
        assert intent["metadata"].get("name") == "Q1 Planning"

    def test_content_extraction(self):
        intent = self.svc._decompose_intent("write about artificial intelligence")
        assert intent["content"] is not None
        assert "artificial intelligence" in intent["content"]

    def test_object_type_spreadsheet(self):
        intent = self.svc._decompose_intent("create a spreadsheet for sales data")
        assert intent["object_type"] == "spreadsheet"

    def test_original_query_preserved(self):
        q = "do something interesting on Notion"
        intent = self.svc._decompose_intent(q)
        assert intent["original_query"] == q


# ---------------------------------------------------------------------------
# validate_workflow
# ---------------------------------------------------------------------------

class TestValidateWorkflow:
    def setup_method(self):
        self.svc = AIService()

    def test_empty_workflow_is_error(self):
        result = asyncio.run(self.svc.validate_workflow([]))
        assert result["valid"] is False
        assert any(i["severity"] == "error" for i in result["issues"])

    def test_missing_first_navigate_is_warning(self):
        steps = [{"type": "click", "selector": "button"}]
        result = asyncio.run(self.svc.validate_workflow(steps))
        severities = [i["severity"] for i in result["issues"]]
        assert "warning" in severities

    def test_missing_selector_is_error(self):
        steps = [
            {"type": "navigate", "url": "https://example.com"},
            {"type": "click"},  # no selector
        ]
        result = asyncio.run(self.svc.validate_workflow(steps))
        assert result["valid"] is False
        errors = [i for i in result["issues"] if i["severity"] == "error"]
        assert any("Missing selector" in e["message"] for e in errors)

    def test_valid_workflow(self):
        steps = [
            {"type": "navigate", "url": "https://example.com"},
            {"type": "click", "selector": "button"},
        ]
        result = asyncio.run(self.svc.validate_workflow(steps))
        assert result["valid"] is True

    def test_very_long_workflow_warns(self):
        steps = [{"type": "navigate", "url": "https://x.com"}] + [
            {"type": "click", "selector": f"#el{i}"} for i in range(25)
        ]
        result = asyncio.run(self.svc.validate_workflow(steps))
        warnings = [i for i in result["issues"] if i["severity"] == "warning"]
        assert any("many steps" in w["message"].lower() for w in warnings)


# ---------------------------------------------------------------------------
# optimize_workflow
# ---------------------------------------------------------------------------

class TestOptimizeWorkflow:
    def setup_method(self):
        self.svc = AIService()

    def test_adds_wait_after_navigate(self):
        steps = [
            {"type": "navigate", "url": "https://example.com"},
            {"type": "click", "selector": "button"},
        ]
        result = asyncio.run(self.svc.optimize_workflow(steps))
        assert result[0]["type"] == "navigate"
        assert result[1]["type"] == "wait"
        assert result[2]["type"] == "click"

    def test_no_duplicate_waits(self):
        steps = [
            {"type": "navigate", "url": "https://example.com"},
            {"type": "wait", "timeout": 2000},
            {"type": "wait", "timeout": 1000},
        ]
        result = asyncio.run(self.svc.optimize_workflow(steps))
        wait_count = sum(1 for s in result if s["type"] == "wait")
        assert wait_count == 1

    def test_no_wait_added_when_already_present(self):
        steps = [
            {"type": "navigate", "url": "https://example.com"},
            {"type": "wait", "timeout": 2000},
            {"type": "click", "selector": "button"},
        ]
        result = asyncio.run(self.svc.optimize_workflow(steps))
        # navigate → existing wait → click; no extra wait inserted
        assert result[0]["type"] == "navigate"
        assert result[1]["type"] == "wait"
        assert result[2]["type"] == "click"
        assert len(result) == 3

    def test_empty_workflow_stays_empty(self):
        result = asyncio.run(self.svc.optimize_workflow([]))
        assert result == []


# ---------------------------------------------------------------------------
# _mock_parse (integration-level; covers intent → workflow generation)
# ---------------------------------------------------------------------------

class TestMockParse:
    def setup_method(self):
        self.svc = AIService()

    def test_login_workflow_generates_login_steps(self):
        result = asyncio.run(
            self.svc.parse_task_description(
                "login to my GitHub account",
                target_url="https://github.com",
            )
        )
        action_types = [s.type for s in result.steps]
        assert "navigate" in action_types
        assert result.requires_auth is True

    def test_search_workflow_has_type_and_navigate(self):
        result = asyncio.run(
            self.svc.parse_task_description(
                "find articles about python on Medium",
            )
        )
        action_types = [s.type for s in result.steps]
        assert "navigate" in action_types

    def test_confidence_higher_when_app_identified(self):
        with_app = asyncio.run(
            self.svc.parse_task_description("search github for python repos")
        )
        without_app = asyncio.run(
            self.svc.parse_task_description("do something vague with no site")
        )
        assert with_app.confidence >= without_app.confidence

    def test_create_document_workflow(self):
        result = asyncio.run(
            self.svc.parse_task_description(
                "Create a Google document named My Report and write about AI"
            )
        )
        action_types = [s.type for s in result.steps]
        assert "navigate" in action_types
        assert "type" in action_types

    def test_warnings_list_is_populated(self):
        result = asyncio.run(
            self.svc.parse_task_description("login to Slack")
        )
        assert len(result.warnings) > 0

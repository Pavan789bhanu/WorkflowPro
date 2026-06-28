"""End-to-end test of the AutomationAgent loop with a fake LLM + fake page.

Verifies the complete orchestration offline:
  plan → observe → decide → act → events → report
including the exact event protocol the frontend consumes.
"""
import asyncio

import pytest

from app.automation.agent.automation_agent import AutomationAgent


class FakeLocator:
    def __init__(self, page):
        self._page = page

    @property
    def first(self):
        return self

    async def count(self):
        return 1

    async def is_visible(self):
        # No overlays on the fake page — keeps _dismiss_overlays a no-op.
        return False

    async def click(self, timeout=None):
        self._page.clicks += 1
        if self._page.dom_toggles_on_click:
            # Modal open/close: DOM changes notably but URL/progress doesn't.
            self._page._dom_len += 400 if self._page.clicks % 2 else -400

    async def fill(self, text, timeout=None):
        self._page.typed.append(text)

    async def inner_text(self, timeout=None):
        return "Element text content"

    async def evaluate(self, script):
        return None

    async def select_option(self, value=None, label=None, timeout=None):
        return None

    async def scroll_into_view_if_needed(self, timeout=None):
        return None


class FakeKeyboard:
    def __init__(self, page):
        self._page = page

    async def press(self, key):
        self._page.keys.append(key)

    async def type(self, text, delay=None):
        self._page.typed.append(text)


class FakeMouse:
    async def wheel(self, dx, dy):
        return None


class FakePage:
    """Implements the minimal Playwright Page surface the agent touches."""

    def __init__(self):
        self.url = "about:blank"
        self.clicks = 0
        self.typed = []
        self.keys = []
        self.keyboard = FakeKeyboard(self)
        self.mouse = FakeMouse()
        self._dom_len = 1000
        self.challenge = ""          # set to simulate a captcha/anti-bot page
        self.dom_toggles_on_click = False  # simulate modal open/close churn

    @property
    def frames(self):
        return []

    @property
    def main_frame(self):
        return self

    async def wait_for_load_state(self, state, timeout=None):
        return None

    async def screenshot(self, timeout=None):
        # tiny valid PNG header + filler
        return b"\x89PNG\r\n\x1a\n" + b"0" * 64

    async def title(self):
        return "Example Domain"

    async def goto(self, url, wait_until=None, timeout=None):
        self.url = url
        self._dom_len += 5000  # navigation changes the page

    async def go_back(self, wait_until=None, timeout=None):
        self.url = "about:blank"

    async def evaluate(self, script):
        if "captcha widget present" in script:  # CHALLENGE_SCAN_JS
            return self.challenge
        if "data-agent-id" in script:
            return [
                {"id": 0, "tag": "a", "text": "Top Story: AI breakthrough", "href": "/story", "inViewport": True},
                {"id": 1, "tag": "input", "type": "search", "placeholder": "Search", "text": "", "inViewport": True},
            ]
        if "innerHTML.length" in script:
            return self._dom_len
        # PAGE_TEXT_JS — content depends on the URL so that extractions on
        # different pages produce different content (like the real web).
        return f"[{self.url}] Example Domain. Top Story: AI breakthrough. More news content here."

    def locator(self, selector):
        return FakeLocator(self)

    def is_closed(self):
        return False


class FakeLLM:
    """Returns: plan → extract action → done. chat() returns the report."""

    def __init__(self):
        self.json_calls = 0

    async def chat_json(self, messages, system=None, max_tokens=0, temperature=0.0):
        self.json_calls += 1
        if self.json_calls == 1:  # planning call
            return {
                "start_url": "https://example.com",
                "app_name": "Example",
                "outline": ["Open example.com", "Read content", "Summarize"],
                "success_criteria": "Content extracted",
                "requires_auth": False,
                "warnings": [],
            }
        if self.json_calls == 2:
            return {
                "action": "extract", "value": "page", "label": "page_content",
                "step_title": "Extract page text", "reason": "Need the content to summarize",
            }
        return {"action": "done", "reason": "Content gathered, task complete."}

    async def chat(self, messages, system=None, max_tokens=0, temperature=0.0, json_mode=False):
        return "# Automation Report\n\n## Result\nAI breakthrough story found.\n\n## Steps Taken\n1. Extracted page"


@pytest.fixture
def agent(tmp_path, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "SCREENSHOT_DIR", tmp_path)

    fake_page = FakePage()
    agent = AutomationAgent(llm=FakeLLM(), headless=True, use_storage_state=False)

    async def fake_start():
        agent.page = fake_page

    async def fake_close():
        return None

    agent._start_browser = fake_start
    agent.close = fake_close
    agent._test_page = fake_page  # test handle
    return agent


def test_agent_full_loop(agent):
    events = []

    async def capture(e):
        events.append(e)

    agent.on_event = capture
    result = asyncio.run(
        agent.run("Summarize the top story on example.com")
    )

    # ── Result object ────────────────────────────────────────────────
    assert result.success is True
    assert result.final_message == "Content gathered, task complete."
    assert "AI breakthrough" in result.report_markdown
    assert len(result.extracted) == 1
    assert result.extracted[0]["label"] == "page_content"
    # navigate + extract executed
    actions = [s.action["action"] for s in result.steps]
    assert actions == ["navigate", "extract"]
    assert all(s.status == "success" for s in result.steps)

    # ── Event protocol (what the frontend relies on) ─────────────────
    types = [e["type"] for e in events]
    for expected in ["planning_start", "planning_complete", "browser_starting",
                     "browser_ready", "step_start", "step_complete",
                     "report_generating", "execution_complete"]:
        assert expected in types, f"missing event: {expected}"
    # ordering
    assert types.index("planning_complete") < types.index("browser_starting")
    assert types.index("step_start") < types.index("step_complete")
    assert types[-1] == "execution_complete"

    planning = next(e for e in events if e["type"] == "planning_complete")
    assert planning["mode"] == "agent"
    assert len(planning["steps"]) == 3  # outline items

    complete = next(e for e in events if e["type"] == "execution_complete")
    assert complete["success"] is True
    assert "Result" in complete["report"]

    step_completes = [e for e in events if e["type"] == "step_complete"]
    assert all("result" in e and "status" in e["result"] for e in step_completes)
    # screenshots are streamed as base64
    assert all(isinstance(e["result"].get("screenshot", ""), str) for e in step_completes)

    # ── Artifacts persisted ──────────────────────────────────────────
    from pathlib import Path
    run_dir = Path(result.run_dir)
    assert (run_dir / "report.md").exists()
    assert (run_dir / "result.json").exists()


def test_agent_fail_action(agent):
    """LLM returning 'fail' should end the run unsuccessfully with the reason."""
    class FailingLLM(FakeLLM):
        async def chat_json(self, messages, system=None, max_tokens=0, temperature=0.0):
            self.json_calls += 1
            if self.json_calls == 1:
                return {"start_url": "https://example.com", "outline": ["try"]}
            return {"action": "fail", "reason": "CAPTCHA blocks the page"}

    agent._llm = FailingLLM()
    result = asyncio.run(agent.run("impossible task"))
    assert result.success is False
    assert "CAPTCHA" in result.final_message


def test_no_effect_click_is_failure_and_loop_hard_stops(agent):
    """A click that changes nothing must be recorded as a failure, and a
    model that keeps repeating it must be cut off early (cost guard) —
    this reproduces the 'steps 7-14 repeating' bug.
    """
    class StubbornLLM(FakeLLM):
        """Always clicks the same element, forever."""
        async def chat_json(self, messages, system=None, max_tokens=0, temperature=0.0):
            self.json_calls += 1
            if self.json_calls == 1:
                return {"start_url": "https://example.com", "outline": ["click around"]}
            return {
                "action": "click", "element_id": 0,
                "step_title": "Click top story", "reason": "trying again",
            }

    llm = StubbornLLM()
    agent._llm = llm
    # FakePage.click never changes _dom_len → page_changed stays False.
    result = asyncio.run(agent.run("read the top story"))

    assert result.success is False
    assert "Stopped early" in result.final_message
    # Every executed click was demoted to failure (no page change)
    clicks = [s for s in result.steps if s.action.get("action") == "click"]
    assert clicks and all(s.status == "error" for s in clicks)
    assert all("did not change" in s.message for s in clicks)
    # Cost guard: far fewer LLM calls than max_steps would allow
    # (1 plan + at most 4 identical decisions before the hard stop)
    assert llm.json_calls <= 6
    assert len(result.steps) <= 5  # navigate + ≤4 clicks


def test_query_rewriting_flows_through(agent):
    """The plan's rewritten_task drives the run and lands on the result."""
    rewritten = ("Find recent articles about multi-agent communication protocols "
                 "and large-scale agent architectures, then summarize them.")

    class RewritingLLM(FakeLLM):
        async def chat_json(self, messages, system=None, max_tokens=0, temperature=0.0):
            self.json_calls += 1
            if self.json_calls == 1:
                return {
                    "start_url": "https://example.com",
                    "rewritten_task": rewritten,
                    "search_terms": ["multi-agent communication protocols"],
                    "sub_goals": ["Find articles", "Summarize them"],
                    "outline": ["Search", "Read", "Summarize"],
                }
            if self.json_calls == 2:
                # The decide prompt must contain the REWRITTEN task + sub-goals
                text = messages[0]["content"][0]["text"]
                assert rewritten in text
                assert "ORDERED SUB-GOALS" in text
                return {"action": "extract", "value": "page", "label": "content",
                        "step_title": "Extract", "reason": "gather"}
            return {"action": "done", "reason": "complete"}

    agent._llm = RewritingLLM()
    result = asyncio.run(
        agent.run("find agentic comunication articles")  # vague + typo
    )
    assert result.success is True
    assert result.rewritten_task == rewritten
    assert result.task == "find agentic comunication articles"


def test_plan_rewrite_defaults_to_original_task():
    """If the planner LLM fails, the original task is used unchanged."""
    class BoomLLM:
        async def chat_json(self, *a, **k):
            raise RuntimeError("offline")

    agent = AutomationAgent(llm=BoomLLM(), use_storage_state=False)
    plan = asyncio.run(
        agent._make_plan("original query", None)
    )
    assert plan["rewritten_task"] == "original query"
    assert plan["sub_goals"] == []
    assert plan["search_terms"] == []


def test_captcha_challenge_fail_fast(agent):
    """A persistent human-verification page must stop the run quickly
    instead of burning LLM calls trying to click through it."""
    class ClickyLLM(FakeLLM):
        async def chat_json(self, messages, system=None, max_tokens=0, temperature=0.0):
            self.json_calls += 1
            if self.json_calls == 1:
                return {"start_url": "https://example.com", "outline": ["browse"]}
            return {"action": "click", "element_id": 0,
                    "step_title": "Try clicking", "reason": "attempt"}

    llm = ClickyLLM()
    agent._llm = llm
    agent._test_page.challenge = "verification text: \"verify you are human\""
    result = asyncio.run(agent.run("read articles"))

    assert result.success is False
    assert "verification" in result.final_message.lower() or "challenge" in result.final_message.lower()
    # Fail-fast: planning + at most 2 decisions before the streak guard trips
    assert llm.json_calls <= 4


def test_progress_watchdog_stops_modal_churn(agent):
    """Clicks that keep flipping a modal open/closed LOOK effective (DOM
    changes) but achieve nothing — the Medium sign-in trap. The watchdog
    must intervene and stop the run."""
    class ModalChurnLLM(FakeLLM):
        """Alternates two different clicks forever (defeats repeat-guard)."""
        async def chat_json(self, messages, system=None, max_tokens=0, temperature=0.0):
            self.json_calls += 1
            if self.json_calls == 1:
                return {"start_url": "https://example.com", "outline": ["browse"]}
            eid = self.json_calls % 2
            return {"action": "click", "element_id": eid,
                    "step_title": f"Click thing {eid}", "reason": "open/close modal"}

    llm = ModalChurnLLM()
    agent._llm = llm
    agent._test_page.dom_toggles_on_click = True
    result = asyncio.run(agent.run("read articles"))

    assert result.success is False
    assert "no real progress" in result.final_message.lower()
    # Stopped well before max_steps (25) — bounded API spend
    assert len(result.steps) <= 12


def test_action_signature_uses_target_text():
    """Signatures must rely on element text, not volatile numeric ids."""
    sig_a = AutomationAgent._action_signature(
        {"action": "click", "element_id": 7, "_target": "Accept Cookies"})
    sig_b = AutomationAgent._action_signature(
        {"action": "click", "element_id": 12, "_target": "accept cookies"})
    assert sig_a == sig_b  # same element text → same signature despite id shift
    sig_c = AutomationAgent._action_signature(
        {"action": "click", "element_id": 12, "_target": "Sign in"})
    assert sig_a != sig_c


def test_action_signature_is_page_aware():
    """'extract page' on three different pages = three DIFFERENT actions.
    (The missing page-URL previously made a healthy research run look like
    a 4x repeat and killed it.)"""
    a = AutomationAgent._action_signature({"action": "extract", "value": "page"},
                                          page_url="https://duckduckgo.com/html/?q=x")
    b = AutomationAgent._action_signature({"action": "extract", "value": "page"},
                                          page_url="https://google.com/search?q=x")
    c = AutomationAgent._action_signature({"action": "extract", "value": "page"},
                                          page_url="https://blog.example.com/a2a")
    assert len({a, b, c}) == 3
    # …but the same extract on the same page IS the same action
    assert a == AutomationAgent._action_signature(
        {"action": "extract", "value": "page"}, page_url="https://duckduckgo.com/html/?q=x#frag")


def test_multi_page_research_run_not_killed(agent):
    """Reproduces the A2A-report failure: extract on several pages in a row
    must NOT trip the repeat guard — these are productive actions."""
    class ResearchLLM(FakeLLM):
        """navigate → extract, three sources, then done."""
        def __init__(self):
            super().__init__()
            self.script = [
                {"action": "extract", "value": "page", "label": "search results",
                 "step_title": "Extract search results", "reason": "scan"},
                {"action": "navigate", "url": "https://blog.example.com/a2a",
                 "step_title": "Open A2A article", "reason": "read"},
                {"action": "extract", "value": "page", "label": "A2A article",
                 "step_title": "Extract article", "reason": "save"},
                {"action": "navigate", "url": "https://blog.example.com/mas",
                 "step_title": "Open MAS article", "reason": "read"},
                {"action": "extract", "value": "page", "label": "MAS article",
                 "step_title": "Extract article", "reason": "save"},
                {"action": "done", "reason": "Three sources gathered and saved."},
            ]

        async def chat_json(self, messages, system=None, max_tokens=0, temperature=0.0):
            self.json_calls += 1
            if self.json_calls == 1:
                return {"start_url": "https://duckduckgo.com/html/?q=a2a", "outline": ["research"]}
            return self.script.pop(0)

    agent._llm = ResearchLLM()
    result = asyncio.run(
        agent.run("research agent-to-agent communication articles")
    )
    assert result.success is True
    assert "Stopped early" not in result.final_message
    assert len(result.extracted) == 3
    assert [e["label"] for e in result.extracted] == ["search results", "A2A article", "MAS article"]


def test_duplicate_extract_rejected_with_guidance(agent):
    """Re-extracting identical content must fail with an instructive message
    (data is already saved) instead of silently storing duplicates."""
    class ReExtractLLM(FakeLLM):
        """extract → extract same page again → done."""
        async def chat_json(self, messages, system=None, max_tokens=0, temperature=0.0):
            self.json_calls += 1
            if self.json_calls == 1:
                return {"start_url": "https://example.com", "outline": ["read"]}
            if self.json_calls in (2, 3):
                return {"action": "extract", "value": "page", "label": "article",
                        "step_title": "Extract article", "reason": "save"}
            return {"action": "done", "reason": "have the data"}

    agent._llm = ReExtractLLM()
    result = asyncio.run(agent.run("read the article"))
    assert result.success is True
    assert len(result.extracted) == 1  # duplicate was rejected
    dup_step = result.steps[-1]
    assert dup_step.status == "error"
    assert "ALREADY EXTRACTED" in dup_step.message


def test_early_stop_with_data_is_partial_success(agent):
    """If the run is cut off but data was gathered, report it as success so
    the user still gets their summaries (previously discarded as 'failed')."""
    class ExtractThenStuckLLM(FakeLLM):
        async def chat_json(self, messages, system=None, max_tokens=0, temperature=0.0):
            self.json_calls += 1
            if self.json_calls == 1:
                return {"start_url": "https://example.com", "outline": ["go"]}
            if self.json_calls == 2:
                return {"action": "extract", "value": "page", "label": "article",
                        "step_title": "Extract", "reason": "save"}
            # then get stuck clicking the same dead element forever
            return {"action": "click", "element_id": 0,
                    "step_title": "Click dead link", "reason": "stuck"}

    agent._llm = ExtractThenStuckLLM()
    result = asyncio.run(agent.run("research task"))
    assert "Stopped early" in result.final_message
    assert result.success is True          # data exists → partial success
    assert len(result.extracted) == 1
    assert "gathered" in result.final_message


def test_transient_llm_error_retried_once(agent):
    """A single transient LLM error must NOT kill the run — the agent retries.
    Only two consecutive errors should terminate the run."""
    class TransientErrorLLM(FakeLLM):
        """Fails once on decide (call 2), succeeds on retry (call 3), then done."""
        async def chat_json(self, messages, system=None, max_tokens=0, temperature=0.0):
            self.json_calls += 1
            if self.json_calls == 1:
                return {"start_url": "https://example.com", "outline": ["go"]}
            if self.json_calls == 2:
                raise ConnectionError("transient network hiccup")
            if self.json_calls == 3:
                return {"action": "extract", "value": "page", "label": "page_text",
                        "step_title": "Extract", "reason": "recovered"}
            return {"action": "done", "reason": "Task complete."}

    agent._llm = TransientErrorLLM()
    result = asyncio.run(agent.run("read the page"))

    # Run must complete successfully despite the one transient error
    assert result.success is True
    assert len(result.extracted) == 1
    assert result.error is None


def test_two_consecutive_llm_errors_terminate_run(agent):
    """Two consecutive decide failures must stop the run to avoid an infinite
    retry spiral.  result.error should be populated."""
    class DoubleFailLLM(FakeLLM):
        async def chat_json(self, messages, system=None, max_tokens=0, temperature=0.0):
            self.json_calls += 1
            if self.json_calls == 1:
                return {"start_url": "https://example.com", "outline": ["go"]}
            raise RuntimeError("persistent LLM failure")

    agent._llm = DoubleFailLLM()
    result = asyncio.run(agent.run("some task"))

    assert result.success is False
    assert result.error is not None
    assert "persistent LLM failure" in result.error
    # Only 1 plan + 2 decide attempts (streak=2 → break)
    assert agent._llm.json_calls <= 4

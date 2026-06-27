"""AutomationAgent — the core vision-driven browser automation loop.

This is the single engine behind both the Playground ("run this English
sentence right now") and saved Workflow executions. It replaces the legacy
plan-then-blindly-execute pipeline with a proper agentic loop:

    1. OBSERVE  – screenshot + structured digest of interactive elements
    2. DECIDE   – multimodal LLM picks ONE next action (JSON)
    3. ACT      – Playwright executes it (click/type/navigate/extract/…)
    4. VERIFY   – page-change detection, loop detection, progress tracking
    5. REPORT   – on finish, an LLM-written result report with the actual
                  answer/output of the task (not just "steps executed")

Design notes
------------
* Elements are tagged in the live DOM with `data-agent-id` during the scan,
  so the LLM refers to elements by ID instead of guessing CSS selectors.
  This is dramatically more reliable on real-world sites.
* Credentials are never sent to the LLM. The model uses the placeholders
  {{EMAIL}} / {{PASSWORD}} and the agent substitutes real values locally.
* Every step emits an event through `on_event` (async callback), which the
  WebSocket endpoints forward to the UI for real-time progress + screenshots.
* Each run gets its own ephemeral browser context (no shared profile dir),
  so concurrent runs never fight over a SingletonLock. Session state is
  loaded from / saved to STORAGE_STATE_PATH when available.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from app.core.config import settings, APP_URL_MAPPINGS
from app.automation.utils.logger import log
from app.services.llm_client import LLMClient, get_llm_client
from app.utils.ssrf_protector import SSRFProtector

EventCallback = Callable[[Dict[str, Any]], Awaitable[None]]

MAX_ELEMENTS_IN_DIGEST = 70
MAX_TEXT_EXCERPT = 1800
MAX_EXTRACTED_CHARS = 24000

# JavaScript injected on every observation: tags visible interactive elements
# with data-agent-id and returns a compact digest of each.
ELEMENT_SCAN_JS = """
() => {
  const selectors = [
    'a[href]', 'button', 'input', 'textarea', 'select',
    '[role="button"]', '[role="link"]', '[role="tab"]', '[role="menuitem"]',
    '[role="combobox"]', '[role="searchbox"]', '[role="checkbox"]',
    '[contenteditable="true"]', '[onclick]', 'summary', '[tabindex]:not([tabindex="-1"])'
  ];
  const seen = new Set();
  const items = [];
  let id = 0;
  for (const el of document.querySelectorAll(selectors.join(','))) {
    if (seen.has(el)) continue;
    seen.add(el);
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    const visible = rect.width > 2 && rect.height > 2 &&
      style.visibility !== 'hidden' && style.display !== 'none' &&
      rect.bottom > 0 && rect.top < (window.innerHeight + 300);
    if (!visible) { el.removeAttribute('data-agent-id'); continue; }
    el.setAttribute('data-agent-id', String(id));
    const tag = el.tagName.toLowerCase();
    let text = (el.innerText || el.value || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
    if (!text) {
      text = (el.getAttribute('aria-label') || el.getAttribute('placeholder') ||
              el.getAttribute('title') || el.getAttribute('alt') || '').slice(0, 80);
    }
    const item = {
      id: id,
      tag: tag,
      text: text,
      type: el.getAttribute('type') || undefined,
      placeholder: el.getAttribute('placeholder') || undefined,
      aria: (el.getAttribute('aria-label') || '').slice(0, 60) || undefined,
      role: el.getAttribute('role') || undefined,
      href: tag === 'a' ? (el.getAttribute('href') || '').slice(0, 120) : undefined,
      editable: el.getAttribute('contenteditable') === 'true' || undefined,
      inViewport: rect.top >= 0 && rect.top < window.innerHeight,
    };
    items.push(item);
    id++;
  }
  return items;
}
"""

PAGE_TEXT_JS = """
() => {
  const main = document.querySelector('main, article, [role="main"]') || document.body;
  return main ? main.innerText.replace(/\\n{3,}/g, '\\n\\n') : '';
}
"""

# Detects CAPTCHA / human-verification / anti-bot challenge pages.
CHALLENGE_SCAN_JS = """
() => {
  const sels = [
    'iframe[src*="recaptcha"]', 'iframe[src*="hcaptcha"]', 'iframe[src*="turnstile"]',
    'iframe[title*="challenge" i]', '#challenge-form', '#cf-challenge-running',
    'div.g-recaptcha', 'div.h-captcha', '#px-captcha'
  ];
  if (sels.some(s => document.querySelector(s))) return 'captcha widget present';
  const title = (document.title || '').toLowerCase();
  if (title.includes('just a moment') || title.includes('attention required') ||
      title.includes('access denied')) return 'anti-bot challenge page: ' + document.title;
  const body = (document.body ? document.body.innerText : '').slice(0, 2500).toLowerCase();
  const phrases = ['verify you are human', 'are you a robot', 'unusual traffic',
                   'complete the security check', 'enable javascript and cookies to continue'];
  const hit = phrases.find(p => body.includes(p));
  return hit ? 'verification text: "' + hit + '"' : '';
}
"""

# Stealth: mask the most common headless-automation fingerprints. Many sites
# (Medium included) serve hostile sign-in walls to detected bots.
STEALTH_INIT_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = window.chrome || { runtime: {} };
const origQuery = window.navigator.permissions && window.navigator.permissions.query;
if (origQuery) {
  window.navigator.permissions.query = (params) =>
    params.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : origQuery(params);
}
"""

# Direct search-URL patterns — navigating straight to results is far more
# reliable than clicking through home pages, modals and sign-in prompts.
SEARCH_URL_PATTERNS = {
    "medium": "https://medium.com/search?q={query}",
    "google": "https://www.google.com/search?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
    "github": "https://github.com/search?q={query}",
    "reddit": "https://www.reddit.com/search/?q={query}",
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={query}",
    "hacker news": "https://hn.algolia.com/?q={query}",
    "amazon": "https://www.amazon.com/s?k={query}",
    "arxiv": "https://arxiv.org/abs/{query}",
    "dev.to": "https://dev.to/search?q={query}",
    "stack overflow": "https://stackoverflow.com/search?q={query}",
}

# Common cookie-consent / overlay dismiss buttons, tried in order.
CONSENT_SELECTORS = [
    "#onetrust-accept-btn-handler",          # OneTrust (very common)
    "button#L2AGLb",                         # Google "I agree"
    "[data-testid='uc-accept-all-button']",  # Usercentrics
    "#sp-cc-accept",                         # Amazon
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
    "button:has-text('Allow all')",
    "button:has-text('Accept cookies')",
    "button:has-text('I agree')",
    "button:has-text('Agree')",
    "button:has-text('Accept')",
    "button:has-text('Got it')",
    "button:has-text('OK')",
    "[aria-label='Accept all']",
    "[aria-label='Close']",
    "[aria-label='close']",
    "[aria-label*='dismiss' i]",
    "[data-testid='close-button']",
]


@dataclass
class AgentStep:
    index: int
    action: Dict[str, Any]
    status: str = "success"          # success | error
    message: str = ""
    url: str = ""
    screenshot_path: Optional[str] = None
    duration_ms: int = 0
    page_changed: bool = False


@dataclass
class AgentResult:
    success: bool
    task: str
    rewritten_task: str = ""
    final_message: str = ""
    report_markdown: str = ""
    steps: List[AgentStep] = field(default_factory=list)
    extracted: List[Dict[str, str]] = field(default_factory=list)
    final_url: str = ""
    run_id: str = ""
    run_dir: Optional[str] = None
    error: Optional[str] = None

    @property
    def steps_executed(self) -> int:
        return len(self.steps)


SYSTEM_PROMPT = """You are an autonomous browser-automation agent. You control a real Chromium browser to complete the user's task end-to-end without human help.

Each turn you receive:
- A SCREENSHOT of the current page (your primary source of truth — trust it over assumptions)
- The current URL and page title
- A numbered list of INTERACTIVE ELEMENTS (refer to them by their numeric id)
- A short excerpt of the page text
- The history of your previous actions and their outcomes
- Data you have extracted so far

You respond with EXACTLY ONE action as a JSON object:

{
  "action": "navigate" | "click" | "type" | "press" | "scroll" | "select" | "extract" | "wait" | "back" | "done" | "fail",
  "element_id": <number, for click/type/select/extract on an element>,
  "url": "<for navigate>",
  "text": "<text to type, for type>",
  "key": "<keyboard key for press, e.g. Enter, Escape>",
  "value": "<option value for select / seconds for wait / 'page' to extract whole page>",
  "direction": "down" | "up"  (for scroll),
  "submit": true | false      (for type: press Enter after typing),
  "label": "<short label describing extracted data, for extract>",
  "step_title": "<very short human-readable description of this action>",
  "reason": "<one sentence: why this action, based on what you SEE>"
}

RULES:
1. ONE action per turn. Look at the screenshot FIRST and base decisions on what is actually visible.
2. Use element ids from the list. Never invent CSS selectors.
3. If a cookie banner / signup modal / overlay blocks content, close or dismiss it first (click its close/X/accept button, or press Escape). NEVER satisfy a signup modal by signing up — dismiss it.
4. If an action had no effect (history says page_changed=false), try a DIFFERENT element or approach — never repeat a failed action. A click that does not change the page IS a failure, even if no error was raised. Actions listed as BANNED in the hint must never be chosen again.
5. To read article/page content, use "extract" with element_id or value="page" and a descriptive label. Extract BEFORE summarizing — your final report can only use extracted data. Extract each page AT MOST ONCE: once it appears under EXTRACTED DATA it is permanently saved — re-extracting is a wasted, banned move. Research flow: open source → extract once → go to NEXT source (or finish). You never need to "extract a summary" — the report engine summarizes the saved data automatically after you finish.
6. NO LOGIN unless strictly necessary: never click "Sign in", "Get started", "Join", "Register", or "Subscribe" for reading/searching/browsing tasks — public content is accessible without an account. Only log in when the task explicitly requires an account action (posting, creating, account settings) AND credentials are available. For login forms type the literal placeholders {{EMAIL}} and {{PASSWORD}} — the system substitutes real credentials locally. Never invent credentials.
7. PREFER DIRECT URLS over clicking through UI. Most sites have direct search/result URLs — use "navigate" with them, e.g.:
   medium.com/search?q=X · bing.com/search?q=X · google.com/search?q=X ·
   github.com/search?q=X · reddit.com/search/?q=X · en.wikipedia.org/w/index.php?search=X ·
   hn.algolia.com/?q=X · stackoverflow.com/search?q=X
   (URL-encode the query). One navigate beats five fragile clicks.
8. IF A SITE BLOCKS YOU (login wall, paywall, CAPTCHA, anti-bot page): do not fight it. In order: (a) try the site's direct URL pattern; (b) search the topic on https://www.bing.com/search?q=<topic> (or Google) and use alternative sources; (c) if you already gathered useful data, finish with "done"; (d) otherwise "fail" with the reason. Never attempt to solve a CAPTCHA.
9. Use "scroll" to reveal content below the fold before deciding nothing is there.
10. When the task goal is fully achieved AND you have gathered any data the task asks for, use "done" with a clear summary in "reason".
11. If the task is impossible or you are stuck after trying alternatives, use "fail" with the reason.
12. After typing in a search box, set "submit": true (or press Enter) to actually search.
13. MAKE PROGRESS every turn: if your last 2-3 turns only opened/closed modals or re-clicked navigation, change strategy (direct URL, different source, or finish).
"""


class AutomationAgent:
    """Vision-driven agent that completes a natural-language task in a browser."""

    def __init__(
        self,
        headless: bool = True,
        llm: Optional[LLMClient] = None,
        credentials: Optional[Dict[str, str]] = None,
        on_event: Optional[EventCallback] = None,
        max_steps: Optional[int] = None,
        use_storage_state: bool = True,
    ) -> None:
        self.headless = headless
        self._llm = llm
        self.credentials = credentials or {}
        self.on_event = on_event
        self.max_steps = max_steps or settings.AGENT_MAX_STEPS
        self.use_storage_state = use_storage_state
        self.ssrf = SSRFProtector()

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    async def _emit(self, event: Dict[str, Any]) -> None:
        if self.on_event:
            try:
                await self.on_event(event)
            except Exception as exc:  # never let UI plumbing kill a run
                log(f"[AGENT] event callback error: {exc}")

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    async def _start_browser(self) -> None:
        self._playwright = await async_playwright().start()

        # Engine is switchable via BROWSER_ENGINE (chromium|firefox|webkit) —
        # Playwright drives all three, so no framework change is ever needed.
        engine_name = settings.BROWSER_ENGINE
        engine = getattr(self._playwright, engine_name, None) or self._playwright.chromium
        launch_kwargs: Dict[str, Any] = {"headless": self.headless}
        if engine_name == "chromium":
            launch_kwargs["args"] = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
            ]
        self._browser = await engine.launch(**launch_kwargs)

        context_kwargs: Dict[str, Any] = {
            "viewport": {"width": 1366, "height": 900},
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }
        if engine_name == "chromium":
            context_kwargs["user_agent"] = (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        storage_path = Path(settings.STORAGE_STATE_PATH)
        if self.use_storage_state and storage_path.exists():
            try:
                json.loads(storage_path.read_text())
                context_kwargs["storage_state"] = str(storage_path)
                log(f"[AGENT] Loaded session state from {storage_path}")
            except Exception:
                log("[AGENT] storage_state.json invalid — starting fresh session")
        self._context = await self._browser.new_context(**context_kwargs)
        self._context.set_default_timeout(settings.TIMEOUT)
        # Mask common automation fingerprints — many sites serve hostile
        # sign-in walls / challenges to detected bots.
        try:
            await self._context.add_init_script(STEALTH_INIT_JS)
        except Exception:
            pass
        self.page = await self._context.new_page()

        # Follow new tabs/popups automatically.
        def _on_page(new_page: Page) -> None:
            log(f"[AGENT] New tab opened: {new_page.url}")
            self.page = new_page
            _wire_page(new_page)

        # Auto-dismiss JS dialogs (alert/confirm/prompt) so actions never hang.
        def _wire_page(p: Page) -> None:
            try:
                p.on("dialog", lambda d: asyncio.create_task(d.dismiss()))
            except Exception:
                pass

        _wire_page(self.page)
        self._context.on("page", _on_page)

    async def _save_storage_state(self) -> None:
        if not (self.use_storage_state and self._context):
            return
        try:
            await self._context.storage_state(path=str(settings.STORAGE_STATE_PATH))
        except Exception as exc:
            log(f"[AGENT] Could not save storage state: {exc}")

    async def close(self) -> None:
        try:
            await self._save_storage_state()
        finally:
            for closer in (self._context, self._browser):
                try:
                    if closer:
                        await closer.close()
                except Exception:
                    pass
            try:
                if self._playwright:
                    await self._playwright.stop()
            except Exception:
                pass
            self._context = None
            self._browser = None
            self._playwright = None
            self.page = None

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    async def _observe(self, run_dir: Path, step_index: int) -> Dict[str, Any]:
        page = self.page
        assert page is not None
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass

        screenshot_path = run_dir / f"step_{step_index}.png"
        screenshot_b64 = ""
        for attempt in (1, 2):
            try:
                raw = await page.screenshot(timeout=8000)
                screenshot_path.write_bytes(raw)
                screenshot_b64 = base64.b64encode(raw).decode()
                break
            except Exception as exc:
                if attempt == 2:
                    log(f"[AGENT] screenshot failed: {exc}")
                else:
                    await asyncio.sleep(0.7)

        try:
            elements = await page.evaluate(ELEMENT_SCAN_JS)
        except Exception as exc:
            log(f"[AGENT] element scan failed: {exc}")
            elements = []
        try:
            page_text = (await page.evaluate(PAGE_TEXT_JS))[:MAX_TEXT_EXCERPT]
        except Exception:
            page_text = ""
        try:
            title = await page.title()
        except Exception:
            title = ""
        try:
            challenge = await page.evaluate(CHALLENGE_SCAN_JS)
        except Exception:
            challenge = ""

        return {
            "url": page.url,
            "title": title,
            "elements": elements[:MAX_ELEMENTS_IN_DIGEST],
            "page_text": page_text,
            "screenshot_b64": screenshot_b64,
            "screenshot_path": str(screenshot_path) if screenshot_b64 else None,
            "challenge": challenge or "",
        }

    @staticmethod
    def _format_elements(elements: List[Dict[str, Any]]) -> str:
        lines = []
        for el in elements:
            bits = [f"[{el['id']}] <{el['tag']}"]
            if el.get("type"):
                bits.append(f" type={el['type']}")
            if el.get("role"):
                bits.append(f" role={el['role']}")
            bits.append(">")
            if el.get("text"):
                bits.append(f" \"{el['text']}\"")
            if el.get("placeholder"):
                bits.append(f" placeholder=\"{el['placeholder']}\"")
            if el.get("aria") and el.get("aria") != el.get("text"):
                bits.append(f" aria=\"{el['aria']}\"")
            if el.get("editable"):
                bits.append(" (contenteditable)")
            if not el.get("inViewport"):
                bits.append(" (below fold)")
            lines.append("".join(bits))
        return "\n".join(lines) if lines else "(no interactive elements found)"

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------

    async def _decide(
        self,
        task: str,
        observation: Dict[str, Any],
        history: List[AgentStep],
        extracted: List[Dict[str, str]],
        hint: Optional[str],
        step_index: int,
    ) -> Dict[str, Any]:
        history_lines = []
        for s in history[-10:]:
            outcome = "ok" if s.status == "success" else "FAILED"
            change = "page_changed=true" if s.page_changed else "page_changed=false"
            history_lines.append(
                f"{s.index}. {s.action.get('action')} {s.action.get('step_title', '')} -> {outcome}, {change}"
                + (f" ({s.message})" if s.status != "success" and s.message else "")
            )
        # Show PREVIEWS, not just sizes — without them the model couldn't tell
        # whether an extraction captured what it needed and kept re-extracting.
        extracted_lines = [
            f"- [{i + 1}] \"{e['label']}\" from {e['url']} ({len(e['content'])} chars saved)\n"
            f"    preview: {e['content'][:220].strip()!r}"
            for i, e in enumerate(extracted)
        ]
        if extracted_lines:
            extracted_lines.append(
                "All of the above is SAVED and will be in the final report — never re-extract it. "
                "If this covers the task, finish with 'done'."
            )
        creds_note = (
            "Login credentials ARE available — use {{EMAIL}} / {{PASSWORD}} placeholders when typing into login forms."
            if self.credentials.get("email") and self.credentials.get("password")
            else "No login credentials are configured. If a login wall blocks the task, try to continue without an account, otherwise 'fail'."
        )

        challenge_note = ""
        if observation.get("challenge"):
            challenge_note = (
                f"⚠ ANTI-BOT CHALLENGE DETECTED ({observation['challenge']}). "
                "Do NOT try to solve it. Navigate to a different source "
                "(direct URL pattern or bing.com/search?q=...) or finish.\n\n"
            )

        text_prompt = (
            f"TASK: {task}\n\n"
            f"STEP {step_index + 1} of max {self.max_steps}\n"
            f"CURRENT URL: {observation['url']}\n"
            f"PAGE TITLE: {observation['title']}\n\n"
            f"{challenge_note}"
            f"PREVIOUS ACTIONS:\n" + ("\n".join(history_lines) if history_lines else "(none yet)") + "\n\n"
            "EXTRACTED DATA SO FAR:\n" + ("\n".join(extracted_lines) if extracted_lines else "(none)") + "\n\n"
            + (f"IMPORTANT HINT: {hint}\n\n" if hint else "")
            + f"{creds_note}\n\n"
            f"INTERACTIVE ELEMENTS (refer by id):\n{self._format_elements(observation['elements'])}\n\n"
            f"PAGE TEXT EXCERPT:\n{observation['page_text'][:1200]}\n\n"
            "Look at the screenshot and respond with the single best next action as JSON."
        )

        content: List[Dict[str, Any]] = [{"type": "text", "text": text_prompt}]
        if observation.get("screenshot_b64"):
            content.append({
                "type": "image_b64",
                "media_type": "image/png",
                "data": observation["screenshot_b64"],
            })

        return await self.llm.chat_json(
            messages=[{"role": "user", "content": content}],
            system=SYSTEM_PROMPT,
            max_tokens=600,
        )

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------

    def _substitute_credentials(self, text: str) -> str:
        if not text:
            return text
        return (
            text.replace("{{EMAIL}}", self.credentials.get("email", ""))
                .replace("{{PASSWORD}}", self.credentials.get("password", ""))
        )

    async def _locator_for(self, element_id: Any):
        assert self.page is not None
        return self.page.locator(f'[data-agent-id="{element_id}"]').first

    async def _dismiss_overlays(self) -> bool:
        """Try to close cookie-consent banners / modals that block clicks.

        Returns True if something was dismissed. Cheap (no LLM call) — used
        proactively after navigation and reactively when a click has no effect.
        """
        page = self.page
        if page is None:
            return False
        dismissed = False
        # Consent managers often live inside iframes (Sourcepoint, Quantcast…),
        # so scan the main frame plus the first few child frames.
        frames = [page]
        try:
            frames += [f for f in page.frames if f != page.main_frame][:5]
        except Exception:
            pass
        for frame in frames:
            for selector in CONSENT_SELECTORS:
                try:
                    loc = frame.locator(selector).first
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.click(timeout=1500)
                        log(f"[AGENT] dismissed overlay via {selector}")
                        dismissed = True
                        await asyncio.sleep(0.6)
                        break
                except Exception:
                    continue
            if dismissed:
                break
        if not dismissed:
            # Escape closes many custom modals/dropdowns.
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
        return dismissed

    @staticmethod
    def _action_signature(action: Dict[str, Any], page_url: str = "") -> tuple:
        """Stable identity of an action for repeat detection.

        Two hard-won lessons baked in:
        * Use the target element's *text* (resolved at decide time) rather than
          its numeric id — ids shift between page scans.
        * Include the CURRENT PAGE URL — "extract page" on three different
          pages is three different (legitimate) actions, not a loop. Without
          this, a healthy research run (extract DDG → extract Google → extract
          article) was killed as a "4x repeat".
        """
        return (
            (action.get("action") or "").lower(),
            str(action.get("_target") or action.get("element_id") or "")[:60].strip().lower(),
            (action.get("url") or "")[:80],
            (action.get("text") or "")[:40],
            (action.get("key") or ""),
            (action.get("direction") or ""),
            (action.get("label") or "")[:40],
            (page_url or "").split("#")[0][:100],
        )

    async def _execute(self, action: Dict[str, Any], extracted: List[Dict[str, str]]) -> str:
        """Execute one action. Returns a human-readable result message.

        Raises on failure — the caller records the error and continues the loop.
        """
        page = self.page
        assert page is not None
        kind = (action.get("action") or "").lower()

        if kind == "navigate":
            url = (action.get("url") or "").strip()
            if not url:
                raise ValueError("navigate requires url")
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            ok, err = self.ssrf.validate_url(url)
            if not ok:
                raise ValueError(f"URL blocked: {err}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(1.5)
            # Proactively clear cookie banners so they never block later clicks.
            await self._dismiss_overlays()
            return f"Navigated to {url}"

        if kind == "click":
            loc = await self._locator_for(action.get("element_id"))
            if await loc.count() == 0:
                raise ValueError(f"element {action.get('element_id')} no longer on page")
            try:
                await loc.click(timeout=8000)
            except Exception:
                # Fallback: force click via JS (overlays, custom widgets)
                await loc.evaluate("el => el.click()")
            await asyncio.sleep(1.2)
            return f"Clicked element {action.get('element_id')}"

        if kind == "type":
            loc = await self._locator_for(action.get("element_id"))
            if await loc.count() == 0:
                raise ValueError(f"element {action.get('element_id')} no longer on page")
            text = self._substitute_credentials(str(action.get("text") or ""))
            try:
                await loc.fill(text, timeout=8000)
            except Exception:
                # contenteditable / custom widgets: focus, select-all, retype
                await loc.click(timeout=5000)
                await page.keyboard.press("ControlOrMeta+A")
                await page.keyboard.type(text, delay=15)
            if action.get("submit"):
                await page.keyboard.press("Enter")
                await asyncio.sleep(1.5)
            shown = text if "{{" not in str(action.get("text") or "") else "(credentials)"
            return f"Typed into element {action.get('element_id')}: {shown[:60]}"

        if kind == "press":
            key = action.get("key") or "Enter"
            await page.keyboard.press(key)
            await asyncio.sleep(0.8)
            return f"Pressed {key}"

        if kind == "scroll":
            direction = (action.get("direction") or "down").lower()
            delta = 700 if direction == "down" else -700
            if action.get("element_id") is not None:
                try:
                    loc = await self._locator_for(action.get("element_id"))
                    await loc.scroll_into_view_if_needed(timeout=5000)
                    return f"Scrolled element {action.get('element_id')} into view"
                except Exception:
                    pass
            await page.mouse.wheel(0, delta)
            await asyncio.sleep(0.6)
            return f"Scrolled {direction}"

        if kind == "select":
            loc = await self._locator_for(action.get("element_id"))
            value = str(action.get("value") or action.get("text") or "")
            try:
                await loc.select_option(value, timeout=5000)
            except Exception:
                await loc.select_option(label=value, timeout=5000)
            return f"Selected '{value}'"

        if kind == "extract":
            import hashlib
            label = action.get("label") or f"extract_{len(extracted) + 1}"
            if str(action.get("value") or "") == "page" or action.get("element_id") is None:
                content = await page.evaluate(PAGE_TEXT_JS)
            else:
                loc = await self._locator_for(action.get("element_id"))
                content = await loc.inner_text(timeout=5000)
            content = (content or "").strip()
            if not content:
                raise ValueError("nothing extracted (element empty)")

            # Dedupe: re-extracting identical content burns LLM calls and
            # previously triggered loop guards. Fail with an INSTRUCTIVE
            # message so the model knows the data is already saved.
            content_hash = hashlib.md5(content[:8000].encode("utf-8", "ignore")).hexdigest()
            if any(e.get("hash") == content_hash for e in extracted):
                raise ValueError(
                    "This exact content is ALREADY EXTRACTED and saved for the report — "
                    "do not extract it again. Open a different source or finish with 'done'."
                )
            total = sum(len(e["content"]) for e in extracted)
            room = MAX_EXTRACTED_CHARS - total
            if room <= 0:
                raise ValueError(
                    "Extraction budget is full — you have plenty of data. "
                    "Finish with 'done'; the report will be written from the saved extractions."
                )
            extracted.append({
                "label": str(label)[:120],
                "url": page.url,
                "content": content[:room],
                "hash": content_hash,
            })
            return f"Extracted '{label}' ({len(content)} chars) — saved for the report"

        if kind == "wait":
            seconds = min(float(action.get("value") or 2), 10.0)
            await asyncio.sleep(seconds)
            return f"Waited {seconds:.0f}s"

        if kind == "back":
            await page.go_back(wait_until="domcontentloaded", timeout=10000)
            await asyncio.sleep(1)
            return "Went back"

        raise ValueError(f"Unknown action: {kind}")

    # ------------------------------------------------------------------
    # Planning + reporting
    # ------------------------------------------------------------------

    def _load_demo_examples(self, task: str, limit: int = 2) -> List[str]:
        """Match the task against the demonstration-video metadata in
        DATA_DIR/.video_cache and return short workflow examples for the
        planner. Zero LLM cost — keyword overlap only."""
        try:
            cache_dir = Path(settings.DATA_DIR) / ".video_cache"
            if not cache_dir.exists():
                return []
            task_words = set(re.findall(r"[a-z]{3,}", task.lower()))
            scored = []
            for meta_file in cache_dir.glob("*_metadata.json"):
                try:
                    meta = json.loads(meta_file.read_text())
                except Exception:
                    continue
                text = f"{meta.get('task_name', '')} {meta.get('description', '')}".lower()
                overlap = len(task_words & set(re.findall(r"[a-z]{3,}", text)))
                if overlap >= 2:
                    scored.append((overlap, meta))
            scored.sort(key=lambda pair: -pair[0])
            return [
                f"- {m.get('task_name')}: {m.get('description')}"
                for _, m in scored[:limit]
            ]
        except Exception as exc:
            log(f"[AGENT] demo example loading failed: {exc}")
            return []

    async def _make_plan(self, task: str, start_url: Optional[str]) -> Dict[str, Any]:
        """Planning + query rewriting in ONE LLM call (no extra API cost).

        Users often give vague, conversational, or typo-ridden queries. Before
        executing, the planner rewrites the task so the execution loop works
        from a precise instruction:

        1. CONTEXTUALIZE — make it self-contained: resolve pronouns/references,
           fix typos, state the implied website and expected output explicitly.
        2. EXPAND — translate slang/shorthand into the precise terms to type
           into site search boxes (with useful synonyms).
        3. SPLIT — a browser works sequentially, so multi-part questions become
           ORDERED sub-goals (not parallel queries like in RAG pipelines).
        """
        known_apps = ", ".join(sorted(APP_URL_MAPPINGS.keys()))
        prompt = (
            f"USER QUERY (verbatim, may be vague/typo-ridden): {task}\n"
            + (f"USER-PROVIDED START URL: {start_url}\n" if start_url else "")
            + "\nYou are planning a browser automation. First REWRITE the query, then plan. Return JSON:\n"
            "{\n"
            '  "rewritten_task": "<self-contained, precise rewrite of the query. Fix typos, resolve vague references, '
            "name the target site, state the expected output (e.g. 'a summary of each article found'). "
            "Preserve the user's intent exactly — never add new requirements.>\",\n"
            '  "search_terms": ["<1-3 concrete phrases to type into site search boxes — expand slang/shorthand into '
            'the formal terms sources actually use, e.g. \'agent communication\' → \'multi-agent communication protocols\'>"],\n'
            '  "sub_goals": ["<if the query has multiple parts, ORDERED concrete sub-goals; else empty list>"],\n'
            '  "start_url": "<best URL to start at (use the user-provided one if given)>",\n'
            '  "app_name": "<short site/app name>",\n'
            '  "outline": ["<3-7 short steps describing the expected flow>"],\n'
            '  "success_criteria": "<one sentence: what done looks like>",\n'
            '  "requires_auth": true|false,\n'
            '  "warnings": ["<only real concerns: login walls, paywalls, captchas>"]\n'
            "}\n\n"
            f"Known app homepage shortcuts (use if relevant): {known_apps}.\n"
            "If the task mentions a site without a URL, infer the canonical URL.\n\n"
            "IMPORTANT — for search/research tasks, set start_url DIRECTLY to the site's "
            "search-results URL (skips home pages, sign-in modals and popups entirely). "
            "Known patterns (replace {query} with the URL-encoded search phrase):\n"
            + "\n".join(f"  {site}: {pattern}" for site, pattern in SEARCH_URL_PATTERNS.items())
            + "\nIf no specific site is implied, use the bing pattern (do NOT use DuckDuckGo)."
        )
        demos = self._load_demo_examples(task)
        if demos:
            prompt += (
                "\n\nDEMONSTRATED WORKFLOWS (from recorded human demos of similar tasks — "
                "mirror their approach in the outline):\n" + "\n".join(demos)
            )
        try:
            plan = await self.llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                system="You are an expert automation planner and query rewriter. Respond with valid JSON only.",
                max_tokens=700,
            )
        except Exception as exc:
            log(f"[AGENT] planning failed ({exc}); using defaults")
            plan = {}
        if start_url:
            plan["start_url"] = start_url
        plan.setdefault("start_url", "")
        plan.setdefault("app_name", "")
        plan.setdefault("rewritten_task", task)
        plan.setdefault("search_terms", [])
        plan.setdefault("sub_goals", [])
        plan.setdefault("outline", [f"Complete task: {task}"])
        plan.setdefault("success_criteria", "Task goal achieved")
        plan.setdefault("requires_auth", False)
        plan.setdefault("warnings", [])
        if not str(plan.get("rewritten_task") or "").strip():
            plan["rewritten_task"] = task
        return plan

    async def _write_report(
        self,
        task: str,
        result_success: bool,
        final_message: str,
        steps: List[AgentStep],
        extracted: List[Dict[str, str]],
        final_url: str,
        rewritten_task: str = "",
    ) -> str:
        steps_log = "\n".join(
            f"{s.index}. [{s.action.get('action')}] {s.action.get('step_title') or ''} — "
            f"{'OK' if s.status == 'success' else 'FAILED'} ({s.message})"
            for s in steps
        )
        extracted_block = "\n\n".join(
            f"### {e['label']}\n(from {e['url']})\n\n{e['content'][:6000]}" for e in extracted
        )
        rewrite_line = (
            f"INTERPRETED AS: {rewritten_task}\n" if rewritten_task and rewritten_task != task else ""
        )
        prompt = (
            f"Write the final execution report for this browser automation run, in Markdown.\n\n"
            f"TASK: {task}\n"
            f"{rewrite_line}"
            f"OUTCOME: {'SUCCESS' if result_success else 'INCOMPLETE/FAILED'}\n"
            f"AGENT'S FINAL NOTE: {final_message}\n"
            f"FINAL URL: {final_url}\n\n"
            f"ACTIONS TAKEN:\n{steps_log or '(none)'}\n\n"
            f"EXTRACTED DATA:\n{extracted_block or '(none)'}\n\n"
            "Structure the report as:\n"
            "# Automation Report\n"
            "## Result  ← THE MOST IMPORTANT SECTION. If the task asked for information "
            "(summaries, findings, listings, comparisons), DELIVER that information here in full, "
            "well organized, based ONLY on the extracted data. If the task performed an action "
            "(created/booked/submitted something), state exactly what was accomplished.\n"
            "## Steps Taken  ← brief numbered list\n"
            "## Issues  ← only if there were any\n"
            "Keep it factual. Do not invent data that was not extracted."
        )
        try:
            return await self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                system="You are a precise technical writer producing automation run reports.",
                max_tokens=2500,
                temperature=0.3,
            )
        except Exception as exc:
            log(f"[AGENT] report generation failed: {exc}")
            status = "✅ Success" if result_success else "⚠️ Incomplete"
            return (
                f"# Automation Report\n\n## Result\n{status} — {final_message}\n\n"
                f"## Steps Taken\n{steps_log}\n"
            )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self, task: str, start_url: Optional[str] = None) -> AgentResult:
        run_id = f"run_{int(time.time() * 1000)}"
        run_dir = Path(settings.SCREENSHOT_DIR) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        result = AgentResult(success=False, task=task, run_id=run_id, run_dir=str(run_dir))
        steps: List[AgentStep] = []
        extracted: List[Dict[str, str]] = []
        started = time.time()

        await self._emit({"type": "planning_start", "message": "AI is planning your automation…"})
        plan = await self._make_plan(task, start_url)

        # Query rewriting: the loop works from the precise, self-contained
        # rewrite; the original stays on the result for reporting/UX.
        working_task = str(plan.get("rewritten_task") or task).strip() or task
        if working_task != task:
            log(f"[AGENT] query rewritten: {working_task[:160]}")
        task_for_agent = working_task
        sub_goals = [str(g) for g in (plan.get("sub_goals") or []) if str(g).strip()]
        search_terms = [str(s) for s in (plan.get("search_terms") or []) if str(s).strip()]
        if sub_goals:
            task_for_agent += "\nORDERED SUB-GOALS:\n" + "\n".join(
                f"  {i + 1}. {g}" for i, g in enumerate(sub_goals)
            )
        if search_terms:
            task_for_agent += "\nSUGGESTED SEARCH PHRASES: " + "; ".join(search_terms)

        outline_steps = [
            {"type": "agent", "description": item, "selector": None, "url": None, "value": None}
            for item in plan["outline"]
        ]
        await self._emit({
            "type": "planning_complete",
            "steps": outline_steps,
            "plan": plan,
            "confidence": 0.9 if plan.get("start_url") else 0.6,
            "requires_auth": bool(plan.get("requires_auth")),
            "warnings": plan.get("warnings", []),
            "estimated_duration": len(plan["outline"]) * 12,
            "mode": "agent",
        })

        await self._emit({"type": "browser_starting", "message": "Launching browser…"})
        try:
            await self._start_browser()
        except Exception as exc:
            result.error = f"Browser failed to start: {exc}"
            await self._emit({"type": "error", "message": result.error})
            await self.close()
            return result
        await self._emit({"type": "browser_ready"})

        # Initial navigation
        first_url = (plan.get("start_url") or "").strip()
        hint: Optional[str] = None
        if first_url:
            nav_action = {"action": "navigate", "url": first_url,
                          "step_title": f"Open {plan.get('app_name') or first_url}",
                          "reason": "Starting point for the task"}
            await self._run_step(nav_action, steps, extracted, run_dir, task)

        final_message = ""
        consecutive_failures = 0
        sig_history: List[tuple] = []
        banned_actions: List[str] = []
        steps_since_progress = 0      # progress = new URL, or successful extract/type/select
        challenge_streak = 0          # consecutive observations on an anti-bot page
        last_url = ""
        try:
            while len(steps) < self.max_steps:
                if time.time() - started > settings.MAX_INACTIVITY_SECONDS * 10:
                    final_message = "Run exceeded the global time budget."
                    break

                observation = await self._observe(run_dir, len(steps))

                # Anti-bot challenge handling: warn the model once, then stop —
                # captchas cannot be solved and every retry costs an LLM call.
                if observation.get("challenge"):
                    challenge_streak += 1
                    log(f"[AGENT] challenge detected ({challenge_streak}x): {observation['challenge']}")
                    if challenge_streak >= 3:
                        result.success = bool(extracted)
                        final_message = (
                            f"Stopped: persistent human-verification challenge ({observation['challenge']}). "
                            + ("Reporting the data gathered before the block." if extracted else
                               "The site blocks automated access — try a different source or run with "
                               "BROWSER_ENGINE=firefox / headful mode.")
                        )
                        break
                else:
                    challenge_streak = 0
                try:
                    action = await asyncio.wait_for(
                        self._decide(task_for_agent, observation, steps, extracted, hint, len(steps)),
                        timeout=settings.AGENT_STEP_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    msg = f"LLM decision timed out after {settings.AGENT_STEP_TIMEOUT}s"
                    log(f"[AGENT] {msg}")
                    await self._emit({"type": "error", "message": msg})
                    result.error = msg
                    break
                except Exception as exc:
                    log(f"[AGENT] decide failed: {exc}")
                    await self._emit({"type": "error", "message": f"LLM error: {exc}"})
                    result.error = str(exc)
                    break
                hint = None

                kind = (action.get("action") or "").lower()
                if kind == "done":
                    result.success = True
                    final_message = action.get("reason") or "Task completed."
                    break
                if kind == "fail":
                    result.success = False
                    final_message = action.get("reason") or "Agent determined the task cannot be completed."
                    break

                # Resolve the target element's TEXT now (ids shift between
                # scans) — used for repeat detection and clearer step logs.
                if action.get("element_id") is not None:
                    el = next(
                        (e for e in observation["elements"]
                         if str(e.get("id")) == str(action.get("element_id"))),
                        None,
                    )
                    if el:
                        action["_target"] = (
                            el.get("text") or el.get("aria") or el.get("placeholder") or f"element {el.get('id')}"
                        )

                step = await self._run_step(action, steps, extracted, run_dir, task)

                # ── Repeat / cost guards ─────────────────────────────────
                # Only INEFFECTIVE repeats count: extracting 5 different
                # articles or clicking "Next page" 5 times is legitimate work,
                # and the signature is page-URL-aware so the same action on a
                # new page is a new action.
                sig = self._action_signature(action, page_url=observation.get("url", ""))
                effective = step.status == "success" and step.page_changed
                sig_history.append((sig, effective))
                repeats = sum(1 for s, eff in sig_history[-6:] if s == sig and not eff)
                if effective:
                    repeats = 0  # this attempt worked — not stuck

                consecutive_failures = 0 if effective else consecutive_failures + 1

                # ── Progress watchdog ────────────────────────────────────
                # Modal open/close flips the DOM (looks "effective") without
                # achieving anything — the exact Medium sign-in trap. Real
                # progress = reaching a new URL or productive data/form work.
                made_progress = (
                    (step.url and step.url != last_url)
                    or (step.status == "success" and kind in ("extract", "type", "select"))
                )
                last_url = step.url or last_url
                steps_since_progress = 0 if made_progress else steps_since_progress + 1

                if steps_since_progress >= 9:
                    result.success = bool(extracted)
                    final_message = (
                        "Stopped: no real progress in the last 9 actions (cost guard). "
                        + ("Reporting the data gathered so far." if extracted else
                           "The site's UI may be blocking automation — consider a direct URL or another source.")
                    )
                    log("[AGENT] hard stop — progress watchdog")
                    break
                if steps_since_progress == 5 and not hint:
                    hint = (
                        "STRATEGY SHIFT REQUIRED: 5 actions with no real progress (no new page, no data). "
                        "Stop interacting with this screen. Navigate directly to a search-results URL "
                        "(e.g. medium.com/search?q=…, bing.com/search?q=…) or a different source, "
                        "or finish with done/fail."
                    )

                if repeats >= 4:
                    # Hard stop — burning LLM calls on the same dead end.
                    # If data was gathered, the run still produces its report
                    # (partial success) instead of discarding good work.
                    result.success = bool(extracted)
                    final_message = (
                        f"Stopped early: the action '{action.get('step_title') or kind}' failed "
                        f"{repeats} times. Aborting to avoid wasted API calls."
                        + (" Reporting the data gathered so far." if extracted else "")
                    )
                    log(f"[AGENT] hard stop — {repeats}x ineffective repeat of {sig[0]} on '{sig[1]}'")
                    break

                if consecutive_failures >= settings.AGENT_MAX_CONSECUTIVE_FAILURES:
                    result.success = bool(extracted)
                    final_message = (
                        f"Stopped early after {consecutive_failures} consecutive ineffective actions "
                        "(cost guard)."
                        + (" Reporting the data gathered so far." if extracted else
                           " The page may require login or be blocking automation.")
                    )
                    log("[AGENT] hard stop — consecutive failure budget exhausted")
                    break

                if repeats == 3:
                    target = action.get("_target") or action.get("url") or ""
                    banned_actions.append(f"{kind} on '{target}'")
                    hint = (
                        f"BANNED ACTIONS (tried 3x, zero effect): {'; '.join(banned_actions[-3:])}. "
                        "You MUST NOT repeat them. Pick a clearly different element, scroll to reveal "
                        "new options, go back, or finish with done/fail if the goal is already met."
                    )
                elif repeats == 2 and not effective:
                    # Second identical no-effect attempt → something is blocking
                    # the click. Clear overlays ourselves (no LLM cost) and tell
                    # the model what happened.
                    dismissed = await self._dismiss_overlays()
                    hint = (
                        "The same action had no effect twice. "
                        + ("An overlay/cookie banner was just dismissed — re-examine the page. "
                           if dismissed else
                           "No obvious overlay found. ")
                        + "Do NOT repeat the same action; choose a different element or approach."
                    )

                if step.status == "error" and not hint:
                    hint = f"Previous action failed: {step.message}. Try a different approach."

            else:
                final_message = (
                    f"Reached the maximum of {self.max_steps} steps. "
                    "Partial progress may have been made."
                )
        except Exception as exc:
            log(f"[AGENT] run crashed: {exc}")
            result.error = str(exc)
            final_message = f"Run aborted by error: {exc}"
        finally:
            result.final_url = self.page.url if self.page else ""

        # Heuristic: a data-gathering task that extracted something and ended by
        # exhausting steps still produced value — mark partial success if the
        # agent never explicitly failed.
        if not result.success and extracted and not result.error and "cannot" not in final_message.lower():
            result.success = len(extracted) > 0 and len(steps) > 0 and any(
                s.status == "success" for s in steps[-3:]
            ) and final_message.startswith("Reached the maximum")

        result.steps = steps
        result.extracted = extracted
        result.rewritten_task = working_task
        result.final_message = final_message or ("Task completed." if result.success else "Run ended.")

        await self._emit({"type": "report_generating", "message": "Writing result report…"})
        result.report_markdown = await self._write_report(
            task, result.success, result.final_message, steps, extracted, result.final_url,
            rewritten_task=working_task,
        )
        try:
            (run_dir / "report.md").write_text(result.report_markdown, encoding="utf-8")
            (run_dir / "result.json").write_text(json.dumps({
                "task": task,
                "rewritten_task": working_task,
                "success": result.success,
                "final_message": result.final_message,
                "final_url": result.final_url,
                "steps": [
                    {"index": s.index, "action": s.action, "status": s.status,
                     "message": s.message, "url": s.url, "screenshot": s.screenshot_path,
                     "duration_ms": s.duration_ms}
                    for s in steps
                ],
                "extracted": extracted,
            }, indent=2), encoding="utf-8")
        except Exception as exc:
            log(f"[AGENT] could not persist run artifacts: {exc}")

        await self._emit({
            "type": "execution_complete",
            "success": result.success,
            "steps_planned": len(outline_steps),
            "steps_executed": len(steps),
            "final_message": result.final_message,
            "report": result.report_markdown,
            "query": task,
            "rewritten_task": working_task,
        })

        await self.close()
        return result

    async def _run_step(
        self,
        action: Dict[str, Any],
        steps: List[AgentStep],
        extracted: List[Dict[str, str]],
        run_dir: Path,
        task: str,
    ) -> AgentStep:
        page = self.page
        assert page is not None
        index = len(steps)
        step = AgentStep(index=index, action=action)

        ui_step = {
            "type": action.get("action"),
            "description": action.get("step_title") or action.get("reason") or action.get("action"),
            "selector": None,
            "url": action.get("url"),
            "value": action.get("text") if "{{" not in str(action.get("text") or "") else "(credentials)",
            "reason": action.get("reason"),
        }
        await self._emit({"type": "step_start", "step_index": index, "step": ui_step,
                          "total_steps": max(self.max_steps, index + 1)})

        url_before = page.url
        t0 = time.time()
        try:
            step.message = await asyncio.wait_for(
                self._execute(action, extracted),
                timeout=settings.AGENT_STEP_TIMEOUT,
            )
            step.status = "success"
        except asyncio.TimeoutError:
            step.status = "error"
            step.message = f"Step timed out after {settings.AGENT_STEP_TIMEOUT}s"
            log(f"[AGENT] step {index} timed out")
        except Exception as exc:
            step.status = "error"
            step.message = str(exc)[:300]
            log(f"[AGENT] step {index} failed: {step.message}")
        step.duration_ms = int((time.time() - t0) * 1000)

        # Post-action observation for change detection + streaming screenshot
        screenshot_b64 = ""
        try:
            raw = await page.screenshot(timeout=8000)
            path = run_dir / f"step_{index}_after.png"
            path.write_bytes(raw)
            step.screenshot_path = str(path)
            screenshot_b64 = base64.b64encode(raw).decode()
        except Exception:
            pass
        step.url = page.url
        try:
            dom_len = await page.evaluate("() => document.body ? document.body.innerHTML.length : 0")
        except Exception:
            dom_len = -1
        prev_dom_len = getattr(self, "_last_dom_len", None)
        self._last_dom_len = dom_len
        step.page_changed = (page.url != url_before) or (
            prev_dom_len is not None and dom_len >= 0 and abs(dom_len - prev_dom_len) > 200
        ) or step.status == "success" and (action.get("action") in ("extract", "wait", "scroll", "type"))

        # A click that doesn't change anything is a FAILURE, even though
        # Playwright reported the click itself as executed. (Previously these
        # were logged as "success", so the model kept repeating them.)
        if step.status == "success" and (action.get("action") or "").lower() == "click" and not step.page_changed:
            step.status = "error"
            step.message = (
                "Click executed but the page did not change — the element is likely "
                "covered by a cookie banner/overlay or is not the right control."
            )
            log(f"[AGENT] step {index}: no-effect click demoted to failure")

        steps.append(step)
        await self._emit({
            "type": "step_complete",
            "step_index": index,
            "step": ui_step,
            "total_steps": max(self.max_steps, index + 1),
            "result": {
                "step_type": action.get("action"),
                "status": step.status,
                "message": step.message,
                "screenshot": screenshot_b64,
                "duration_ms": step.duration_ms,
                "url": step.url,
            },
        })
        return step

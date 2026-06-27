"""Live end-to-end smoke test for the AutomationAgent.

Runs a REAL browser automation with your configured LLM key — no server needed.
Costs a few cents of API usage and ~1-2 minutes.

Usage (from the backend/ directory, venv active):

    python scripts/live_e2e.py
    python scripts/live_e2e.py "Go to Wikipedia and summarize the article of the day"
    python scripts/live_e2e.py --show          # watch the browser window
    python scripts/live_e2e.py --provider anthropic

Exit code 0 = the agent completed the task and produced a report.
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Allow running from the backend/ directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_TASK = (
    "Go to https://news.ycombinator.com and summarize the top 5 stories "
    "currently on the front page, with one sentence per story."
)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Live agent smoke test")
    parser.add_argument("task", nargs="?", default=DEFAULT_TASK)
    parser.add_argument("--url", default=None, help="Optional start URL")
    parser.add_argument("--show", action="store_true", help="Show the browser window (headful)")
    parser.add_argument("--provider", default=None, choices=["openai", "anthropic"],
                        help="Override LLM provider for this run")
    parser.add_argument("--max-steps", type=int, default=15)
    args = parser.parse_args()

    from app.automation.agent.automation_agent import AutomationAgent
    from app.services.llm_client import LLMClient
    from app.core.config import settings

    llm = LLMClient(provider=args.provider) if args.provider else None

    print("=" * 70)
    print("LIVE E2E TEST — AutomationAgent")
    print(f"  Task     : {args.task}")
    print(f"  Provider : {args.provider or settings.active_llm_provider}")
    print(f"  Headless : {not args.show}")
    print("=" * 70)

    async def on_event(event):
        etype = event.get("type")
        if etype == "planning_complete":
            outline = [s["description"] for s in event.get("steps", [])]
            print(f"\n📋 Plan: {outline}")
        elif etype == "step_start":
            step = event.get("step", {})
            print(f"  ▶ step {event.get('step_index', 0) + 1}: [{step.get('type')}] {step.get('description')}")
        elif etype == "step_complete":
            result = event.get("result", {})
            mark = "✓" if result.get("status") == "success" else "✗"
            print(f"    {mark} {result.get('message', '')[:90]}")
        elif etype == "report_generating":
            print("\n📝 Generating result report…")
        elif etype == "error":
            print(f"  ⚠ {event.get('message')}")

    agent = AutomationAgent(
        headless=not args.show,
        llm=llm,
        on_event=on_event,
        max_steps=args.max_steps,
    )
    result = await agent.run(args.task, args.url)

    print("\n" + "=" * 70)
    print(f"SUCCESS: {result.success}")
    print(f"FINAL MESSAGE: {result.final_message}")
    print(f"STEPS EXECUTED: {result.steps_executed}")
    print(f"RUN ARTIFACTS: {result.run_dir}")
    print("=" * 70)
    print("\n----- RESULT REPORT -----\n")
    print(result.report_markdown)

    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

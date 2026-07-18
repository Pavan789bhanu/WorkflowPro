"""Workflow execution service — bridges the API/DB layer to the AutomationAgent.

Runs a saved workflow with the vision-driven agent, persists the outcome on the
Execution row, broadcasts real-time progress over the app WebSocket, and writes
an HTML report (with screenshots) served by /api/executions/{id}/report.
"""

import base64
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.automation.agent.automation_agent import AutomationAgent, AgentResult
from app.services.websocket_manager import manager
from app.models.models import Execution, Workflow, ExecutionStatus
from app.core.database import SessionLocal
from app.core.config import settings, APP_URL_MAPPINGS
from app.core.encryption import resolve_stored_password
from app.automation.utils.logger import get_logger

logger = get_logger("workflowpro.executor")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _markdown_to_html(md: str) -> str:
    """Tiny dependency-free markdown → HTML for the report page."""
    out = []
    in_list = False
    list_tag = "ul"  # "ul" for bullets, "ol" for numbered items
    for raw_line in md.splitlines():
        line = html.escape(raw_line.rstrip())
        # inline: bold / code
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        line = re.sub(r"`([^`]+)`", r"<code>\1</code>", line)
        if line.startswith("### "):
            line_html = f"<h3>{line[4:]}</h3>"
        elif line.startswith("## "):
            line_html = f"<h2>{line[3:]}</h2>"
        elif line.startswith("# "):
            line_html = f"<h1>{line[2:]}</h1>"
        elif re.match(r"^\s*\d+\.\s+", line):
            item = re.sub(r"^\s*\d+\.\s+", "", line)
            new_tag = "ol"
            if not in_list or list_tag != new_tag:
                if in_list:
                    out.append(f"</{list_tag}>")
                out.append(f"<{new_tag}>")
                in_list = True
                list_tag = new_tag
            out.append(f"<li>{item}</li>")
            continue
        elif re.match(r"^\s*[-*]\s+", line):
            item = re.sub(r"^\s*[-*]\s+", "", line)
            new_tag = "ul"
            if not in_list or list_tag != new_tag:
                if in_list:
                    out.append(f"</{list_tag}>")
                out.append(f"<{new_tag}>")
                in_list = True
                list_tag = new_tag
            out.append(f"<li>{item}</li>")
            continue
        elif line.strip() == "":
            line_html = ""
        else:
            line_html = f"<p>{line}</p>"
        if in_list:
            out.append(f"</{list_tag}>")
            in_list = False
        if line_html:
            out.append(line_html)
    if in_list:
        out.append(f"</{list_tag}>")
    return "\n".join(out)


def _write_html_report(result: AgentResult, workflow_name: str) -> Optional[str]:
    """Render the agent's markdown report + screenshots into a styled HTML file."""
    if not result.run_dir:
        return None
    run_dir = Path(result.run_dir)
    status_color = "#10b981" if result.success else "#ef4444"
    status_label = "SUCCESS" if result.success else "INCOMPLETE"

    # Inline screenshots as data URIs → the report is fully self-contained
    # (no extra authenticated requests needed when viewed in an iframe).
    shots = []
    for step in result.steps:
        if step.screenshot_path and Path(step.screenshot_path).exists():
            try:
                b64 = base64.b64encode(Path(step.screenshot_path).read_bytes()).decode()
            except Exception:
                continue
            title = html.escape(step.action.get("step_title") or step.action.get("action") or f"Step {step.index + 1}")
            shots.append(
                f'<figure><img src="data:image/png;base64,{b64}" loading="lazy" alt="{title}"/>'
                f"<figcaption>Step {step.index + 1}: {title}</figcaption></figure>"
            )

    steps_rows = "".join(
        f"<tr><td>{s.index + 1}</td><td>{html.escape(str(s.action.get('action') or ''))}</td>"
        f"<td>{html.escape(s.action.get('step_title') or s.action.get('reason') or '')}</td>"
        f"<td class='{ 'ok' if s.status == 'success' else 'err' }'>{s.status}</td>"
        f"<td>{html.escape((s.message or '')[:160])}</td></tr>"
        for s in result.steps
    )

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Automation Report — {html.escape(workflow_name)}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family: -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
         margin: 0; background: #f8fafc; color: #0f172a; line-height: 1.6; }}
  .wrap {{ max-width: 880px; margin: 0 auto; padding: 32px 20px 64px; }}
  .badge {{ display: inline-block; padding: 4px 14px; border-radius: 999px; color: #fff;
           background: {status_color}; font-weight: 700; font-size: 13px; letter-spacing: .04em; }}
  .meta {{ color: #64748b; font-size: 14px; margin: 6px 0 24px; }}
  .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 24px 28px; margin-bottom: 24px; }}
  h1 {{ font-size: 24px; margin: 8px 0 4px; }}
  h2 {{ font-size: 18px; margin-top: 22px; }}
  h3 {{ font-size: 15px; }}
  code {{ background: #f1f5f9; padding: 1px 6px; border-radius: 5px; font-size: 13px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #eef2f7; vertical-align: top; }}
  th {{ color: #64748b; font-weight: 600; }}
  td.ok {{ color: #059669; font-weight: 600; }}
  td.err {{ color: #dc2626; font-weight: 600; }}
  figure {{ margin: 0 0 22px; }}
  figure img {{ width: 100%; border-radius: 10px; border: 1px solid #e2e8f0; }}
  figcaption {{ font-size: 12px; color: #64748b; margin-top: 6px; }}
</style>
</head>
<body>
<div class="wrap">
  <span class="badge">{status_label}</span>
  <h1>{html.escape(workflow_name)}</h1>
  <p class="meta">Task: {html.escape(result.task)}<br/>
     Final URL: {html.escape(result.final_url or '—')} · Steps: {result.steps_executed} · Run: {result.run_id}</p>
  <div class="card">{_markdown_to_html(result.report_markdown or result.final_message)}</div>
  <div class="card"><h2>Action Log</h2>
    <table><thead><tr><th>#</th><th>Action</th><th>Description</th><th>Status</th><th>Detail</th></tr></thead>
    <tbody>{steps_rows or '<tr><td colspan=5>No steps executed</td></tr>'}</tbody></table>
  </div>
  <div class="card"><h2>Screenshots</h2>{''.join(shots) or '<p>No screenshots captured.</p>'}</div>
</div>
</body>
</html>"""
    report_path = run_dir / "execution_report.html"
    report_path.write_text(doc, encoding="utf-8")
    return str(report_path)


async def execute_workflow(execution_id: int, db: Session = None):
    """Execute a workflow using the AutomationAgent."""
    logger.info("Starting execution %s", execution_id)

    close_db = db is None
    db = db or SessionLocal()

    try:
        execution = db.query(Execution).filter(Execution.id == execution_id).first()
        if not execution:
            logger.error("Execution %s not found", execution_id)
            return

        workflow = db.query(Workflow).filter(Workflow.id == execution.workflow_id).first()
        if not workflow:
            execution.status = ExecutionStatus.FAILED
            execution.error_message = "Workflow not found"
            execution.completed_at = _utcnow()
            db.commit()
            return

        logger.info("Executing workflow: %s (ID: %s)", workflow.name, workflow.id)

        execution.status = ExecutionStatus.RUNNING
        execution.started_at = _utcnow()
        db.commit()

        await manager.send_execution_update(
            execution_id=execution_id,
            event="started",
            data={
                "workflow_id": workflow.id,
                "workflow_name": workflow.name,
                "status": "RUNNING",
                "started_at": execution.started_at.isoformat(),
            },
        )

        # Resolve task + URL
        app_name = workflow.app_name or ""
        url = workflow.start_url or ""
        if not url and app_name:
            url = APP_URL_MAPPINGS.get(app_name.lower(), "")
        task = workflow.description or f"Complete the workflow '{workflow.name}'" + (f" in {app_name}" if app_name else "")

        # Credentials: workflow-specific > .env defaults
        auth_email = workflow.login_email or settings.LOGIN_EMAIL
        auth_password = resolve_stored_password(workflow.login_password) or settings.LOGIN_PASSWORD
        credentials = {"email": auth_email, "password": auth_password} if auth_email and auth_password else {}

        # Stream agent events to all websocket clients (without heavy screenshots)
        async def forward_event(event: dict):
            payload = dict(event)
            result = payload.get("result")
            if isinstance(result, dict) and result.get("screenshot"):
                result = dict(result)
                screenshot = result.pop("screenshot", "")
                # Forward a thumbnail-size signal only (full image stays on disk)
                result["has_screenshot"] = bool(screenshot)
                payload["result"] = result
            await manager.send_execution_update(
                execution_id=execution_id,
                event="progress",
                data=payload,
            )

        agent = AutomationAgent(
            headless=settings.DEFAULT_HEADLESS,
            credentials=credentials,
            on_event=forward_event,
        )

        try:
            result = await agent.run(task=task, start_url=url or None)
        except Exception as exec_error:
            execution.status = ExecutionStatus.FAILED
            execution.completed_at = _utcnow()
            execution.error_message = str(exec_error)[:1000]
            execution.result = json.dumps({
                "success": False,
                "error": str(exec_error),
                "message": "Workflow execution crashed",
            })
            db.commit()
            await manager.send_execution_update(
                execution_id=execution_id,
                event="failed",
                data={"status": "FAILED", "error": str(exec_error), "success": False},
            )
            raise

        html_report = None
        try:
            html_report = _write_html_report(result, workflow.name)
        except Exception as report_err:
            logger.warning("HTML report generation failed: %s", report_err)

        execution.status = ExecutionStatus.SUCCESS if result.success else ExecutionStatus.FAILED
        execution.completed_at = _utcnow()
        duration = int((execution.completed_at - execution.started_at).total_seconds()) if execution.started_at else None
        if not result.success:
            execution.error_message = (result.error or result.final_message or "")[:1000]

        execution.result = json.dumps({
            "success": result.success,
            "message": result.final_message,
            "task": task,
            "app_name": app_name,
            "url": url,
            "final_url": result.final_url,
            "steps_executed": result.steps_executed,
            "run_id": result.run_id,
            "report_markdown": result.report_markdown,
            "html_report": html_report,
            "duration": duration,
        })
        db.commit()

        await manager.send_execution_update(
            execution_id=execution_id,
            event="completed" if result.success else "failed",
            data={
                "status": execution.status.value,
                "completed_at": execution.completed_at.isoformat(),
                "duration": duration,
                "success": result.success,
                "message": result.final_message,
            },
        )
        logger.info(
            "Execution %s %s in %ss",
            execution_id,
            "succeeded" if result.success else "failed",
            duration,
        )

    except Exception as e:
        logger.exception("Error executing workflow %s: %s", execution_id, e)
        try:
            execution = db.query(Execution).filter(Execution.id == execution_id).first()
            if execution and execution.status not in (ExecutionStatus.SUCCESS, ExecutionStatus.FAILED):
                execution.status = ExecutionStatus.FAILED
                execution.completed_at = _utcnow()
                execution.error_message = str(e)[:1000]
                execution.result = execution.result or json.dumps({"success": False, "error": str(e)})
                db.commit()
        except Exception as db_error:
            logger.error("Error updating execution status: %s", db_error)
        raise

    finally:
        if close_db and db:
            db.close()

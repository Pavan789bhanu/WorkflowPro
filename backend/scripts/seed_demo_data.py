#!/usr/bin/env python3
"""Seed polished sample workflows + executions for a stakeholder demo.

Makes the dashboard, workflows, executions, and analytics pages look alive
with realistic success/failure mix — without running a live browser.

Usage (from backend/):
  python scripts/seed_demo_data.py
  python scripts/seed_demo_data.py --reset   # replace previous demo seed
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow `python scripts/seed_demo_data.py` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import Base, SessionLocal, engine
from app.core.security import get_password_hash
from app.models.models import (
    Execution,
    ExecutionStatus,
    User,
    Workflow,
    WorkflowStatus,
)

DEMO_TAG = "[Demo]"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ensure_admin(db) -> User:
    admin = db.query(User).filter(User.username == "admin").first()
    if admin:
        return admin
    admin = User(
        email="admin@example.com",
        username="admin",
        hashed_password=get_password_hash("admin123"),
        is_active=True,
        is_superuser=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def _clear_demo(db, owner_id: int) -> int:
    demo_workflows = (
        db.query(Workflow)
        .filter(Workflow.owner_id == owner_id, Workflow.name.startswith(DEMO_TAG))
        .all()
    )
    count = 0
    for wf in demo_workflows:
        db.query(Execution).filter(Execution.workflow_id == wf.id).delete()
        db.delete(wf)
        count += 1
    db.commit()
    return count


def seed(reset: bool = False) -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = _ensure_admin(db)
        if reset:
            removed = _clear_demo(db, admin.id)
            print(f"Removed {removed} previous demo workflow(s).")

        existing = (
            db.query(Workflow)
            .filter(Workflow.owner_id == admin.id, Workflow.name.startswith(DEMO_TAG))
            .count()
        )
        if existing and not reset:
            print(f"Demo data already present ({existing} workflows). Use --reset to recreate.")
            return

        catalog = [
            {
                "name": f"{DEMO_TAG} Research Hacker News headlines",
                "description": "Open Hacker News and list the top 5 story titles with links.",
                "app_name": "hacker news",
                "start_url": "https://news.ycombinator.com",
                "runs": [
                    (ExecutionStatus.SUCCESS, 42, True),
                    (ExecutionStatus.SUCCESS, 38, True),
                    (ExecutionStatus.FAILED, 19, False),
                ],
            },
            {
                "name": f"{DEMO_TAG} GitHub FastAPI search",
                "description": 'Go to GitHub and search for "fastapi" repositories, capture the top results.',
                "app_name": "github",
                "start_url": "https://github.com",
                "runs": [
                    (ExecutionStatus.SUCCESS, 55, True),
                    (ExecutionStatus.SUCCESS, 61, True),
                    (ExecutionStatus.SUCCESS, 48, True),
                ],
            },
            {
                "name": f"{DEMO_TAG} Wikipedia Playwright lookup",
                "description": 'Open Wikipedia and look up "Playwright browser automation", summarize the intro.',
                "app_name": "wikipedia",
                "start_url": "https://en.wikipedia.org",
                "runs": [
                    (ExecutionStatus.SUCCESS, 33, True),
                    (ExecutionStatus.FAILED, 12, False),
                ],
            },
            {
                "name": f"{DEMO_TAG} Product Hunt daily scan",
                "description": "Visit Product Hunt and list today's featured products with one-line descriptions.",
                "app_name": "product hunt",
                "start_url": "https://www.producthunt.com",
                "runs": [
                    (ExecutionStatus.SUCCESS, 70, True),
                ],
            },
        ]

        now = _utcnow()
        hours_ago = 2
        created_wfs = 0
        created_ex = 0

        for item in catalog:
            wf = Workflow(
                name=item["name"],
                description=item["description"],
                app_name=item["app_name"],
                start_url=item["start_url"],
                status=WorkflowStatus.ACTIVE,
                owner_id=admin.id,
                steps=json.dumps([]),
            )
            db.add(wf)
            db.flush()
            created_wfs += 1

            for status, duration_s, ok in item["runs"]:
                started = now - timedelta(hours=hours_ago)
                completed = started + timedelta(seconds=duration_s)
                hours_ago += 5
                result = {
                    "success": ok,
                    "message": (
                        "Task completed — extracted content ready in the report."
                        if ok
                        else "Stopped early after repeated extraction failures."
                    ),
                    "task": item["description"],
                    "app_name": item["app_name"],
                    "url": item["start_url"],
                    "final_url": item["start_url"],
                    "steps_executed": 6 if ok else 3,
                    "duration": duration_s,
                    "report_markdown": (
                        f"## Result\n\nDemo run against **{item['app_name']}** completed successfully.\n"
                        if ok
                        else f"## Result\n\nDemo run against **{item['app_name']}** failed (intentional sample).\n"
                    ),
                }
                ex = Execution(
                    workflow_id=wf.id,
                    status=status,
                    started_at=started,
                    completed_at=completed,
                    error_message=None if ok else "Sample failure for analytics demo",
                    result=json.dumps(result),
                    created_at=started,
                )
                db.add(ex)
                created_ex += 1

        db.commit()
        print(f"✅ Seeded {created_wfs} demo workflows and {created_ex} executions for admin.")
        print("   Login: admin@example.com / admin123")
        print("   Then open Dashboard → Workflows → Executions → Analytics → Playground.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo workflows and executions")
    parser.add_argument("--reset", action="store_true", help="Replace existing [Demo] seed data")
    args = parser.parse_args()
    seed(reset=args.reset)

<h1 align="center">WorkflowPro</h1>

<p align="center">
  <strong>AI-Powered Browser Automation Platform</strong><br/>
  Build, execute, and monitor browser workflows using natural language
</p>

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#%EF%B8%8F-architecture">Architecture</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-documentation">Docs</a> •
  <a href="#-contributing">Contributing</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/node-20+-green.svg" alt="Node 20+" />
  <img src="https://img.shields.io/badge/react-19-61DAFB.svg" alt="React 19" />
  <img src="https://img.shields.io/badge/fastapi-0.100+-009688.svg" alt="FastAPI" />
  <img src="https://img.shields.io/badge/playwright-latest-2EAD33.svg" alt="Playwright" />
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License" />
</p>

---

## 🎯 Overview

WorkflowPro is an intelligent browser automation platform that transforms natural language descriptions into executable browser workflows. Powered by a vision-capable LLM (**OpenAI GPT-4o or Anthropic Claude — your choice via .env**), it understands web interfaces visually—just like a human would—and executes complex multi-step tasks autonomously.

At its core is the **AutomationAgent**: an observe → decide → act loop. Before every single action the agent takes a screenshot, scans the live DOM for interactive elements, and lets the LLM choose the next move. No brittle pre-scripted selectors. When the run finishes you get a **result report containing the actual output** of your task (summaries, findings, confirmations) — not just a list of clicks.

```
"Go to Medium, find articles about RAG from the past week, and summarize what's new in AI"
                                  │
                                  ▼
      ┌────────────── AutomationAgent loop ──────────────┐
      │  📸 Observe: screenshot + DOM element digest      │
      │  🧠 Decide:  LLM picks ONE action (click #14, …)  │
      │  🖱️ Act:     Playwright executes it               │
      │  ✅ Verify:  page-change + loop detection         │
      └───────────── repeat until done ──────────────────┘
                                  │
                                  ▼
        📄 Result report: the summaries you asked for,
           + step log + screenshots, streamed live to the UI
```

### The Problem

Modern web applications are increasingly complex. Teams struggle with:

- **Manual Documentation**: Creating step-by-step guides is time-consuming and error-prone
- **Regression Testing**: Recording and maintaining test flows requires significant effort
- **Onboarding**: Training new team members on complex workflows is inefficient
- **Process Automation**: Building browser automations requires deep technical knowledge

### Our Solution

WorkflowPro provides a complete platform where you can:

1. **Describe tasks in plain English** → "Log into Notion and create a new project"
2. **Watch AI execute in real-time** → Visual step-by-step execution with screenshots
3. **Review detailed reports** → AI-explained workflows with comprehensive documentation
4. **Manage & rerun workflows** → Save, edit, and schedule automation tasks

---

## ✨ Features

### 🤖 AI-Powered Workflow Generation

```
Input:  "Go to GitHub, create a new repository called 'my-project', 
         add a README, and make it private"

Output: Structured workflow with 8 executable steps
```

- **Natural Language Processing**: Describe tasks conversationally
- **GPT-4 Vision Integration**: Understands UI elements visually
- **Intelligent Step Planning**: Breaks complex tasks into atomic actions
- **Self-Healing Selectors**: Adapts to UI changes automatically

### 🎮 Interactive Playground

- **Real-time Preview**: See generated steps before execution
- **Drag & Drop Editing**: Reorder steps with intuitive controls
- **Step-by-Step Execution**: Run individual steps or full workflows
- **Live Screenshots**: Visual feedback at every step
- **AI Suggestions**: Get contextual recommendations

### 📊 Workflow Management Dashboard

- **Multiple View Modes**: Grid, List, and Compact table views
- **Smart Filtering**: Filter by status, search by name
- **Execution History**: Track all runs with detailed metrics
- **Success Rate Analytics**: Monitor automation reliability
- **One-Click Execution**: Run any saved workflow instantly

### 📈 Execution Monitoring

- **Real-time Status Updates**: WebSocket-powered live updates
- **Grouped by Date**: Organized execution history
- **Interactive Reports**: Embedded report viewer with fullscreen mode
- **Duration Tracking**: Performance metrics for each run
- **Error Diagnostics**: Detailed failure analysis

### 🔐 Enterprise-Ready Security

- **JWT Authentication**: Secure token-based auth
- **Session Persistence**: Saved browser authentication state
- **Credential Management**: Encrypted storage for sensitive data
- **Role-Based Access**: (Coming soon)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              WorkflowPro Platform                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         Frontend (React 19)                         │    │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────────────────┐│    │
│  │  │ Dashboard │ │ Workflows │ │Executions │ │      Playground       ││    │
│  │  │           │ │           │ │           │ │  (AI Workflow Builder)││    │
│  │  └───────────┘ └───────────┘ └───────────┘ └───────────────────────┘│    │
│  │  ┌─────────────────────────────────────────────────────────────────┐│    │
│  │  │  React Query │ React Router │ WebSocket │ Context Providers     ││    │
│  │  └─────────────────────────────────────────────────────────────────┘│    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        Backend (FastAPI)                            │    │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────────────────┐│    │
│  │  │  REST API │ │ WebSocket │ │   Auth    │ │   Report Generator    ││    │
│  │  │ Endpoints │ │  Server   │ │  (JWT)    │ │      (HTML/PDF)       ││    │
│  │  └───────────┘ └───────────┘ └───────────┘ └───────────────────────┘│    │
│  │  ┌─────────────────────────────────────────────────────────────────┐│    │
│  │  │           SQLite Database │ Async Task Queue                    ││    │
│  │  └─────────────────────────────────────────────────────────────────┘│    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                AutomationAgent (vision-driven loop)                 │    │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────────────────┐│    │
│  │  │  Observe  │ │  Decide   │ │    Act    │ │   Report Generator    ││    │
│  │  │(screenshot│ │ LLM Client│ │(Playwright)│ │ (result + screenshots)││    │
│  │  │+DOM digest│ │ GPT-4o /  │ │ element-id│ │                       ││    │
│  │  │ )         │ │  Claude   │ │  actions  │ │                       ││    │
│  │  └───────────┘ └───────────┘ └───────────┘ └───────────────────────┘│    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Frontend** | React 19, TypeScript, Vite | Modern SPA with type safety |
| **Styling** | Tailwind CSS | Utility-first responsive design |
| **State** | TanStack Query, Zustand | Server state & client state management |
| **Routing** | React Router v7 | Nested routes with code splitting |
| **Backend** | FastAPI, Python 3.11+ | High-performance async API |
| **Database** | SQLite + SQLAlchemy | Lightweight persistent storage |
| **Real-time** | WebSocket (Socket.IO) | Live execution updates |
| **Browser** | Playwright | Cross-browser automation |
| **AI** | OpenAI GPT-4o / Anthropic Claude (configurable) | Visual UI understanding |
| **Deployment** | Docker Compose (backend + nginx frontend) | One-command deploy |
| **CI/CD** | GitHub Actions | Automated testing & deployment |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+** with pip *(local dev)* or **Docker** *(deployment)*
- **Node.js 20+** with npm *(local dev)*
- An LLM API key: **OpenAI** (GPT-4o) *or* **Anthropic** (Claude) — set either one

### Option 1 — Docker (recommended for deployment)

```bash
git clone https://github.com/pavan-kumar-malasani/ui_capture_system.git
cd ui_capture_system
# create .env (./start.sh generates a template on first run, or write one
# with: SECRET_KEY + OPENAI_API_KEY or ANTHROPIC_API_KEY)
docker compose up --build -d
```

Open **http://localhost:8080** — login `admin@example.com` / `admin123` (configurable via `ADMIN_EMAIL` / `ADMIN_PASSWORD`).

### Option 2 — Local development (lets you watch the browser work)

```bash
git clone https://github.com/pavan-kumar-malasani/ui_capture_system.git
cd ui_capture_system
./start.sh                 # first run creates a .env template — fill in
                           # SECRET_KEY + an LLM API key, then re-run
```

Open **http://localhost:5173**. Set `DEFAULT_HEADLESS=false` in `.env` to watch the Chromium window live. Stop with `./stop.sh`.

### Choosing your LLM provider

```bash
# .env
LLM_PROVIDER=auto            # auto | openai | anthropic
OPENAI_API_KEY=sk-...        # for GPT-4o
ANTHROPIC_API_KEY=sk-ant-... # for Claude
OPENAI_MODEL=gpt-4o
ANTHROPIC_MODEL=claude-sonnet-4-5
```

`auto` uses whichever key is present (OpenAI wins if both are set). Switch providers any time — no code changes needed.

### Manual startup (alternative)

```bash
# Terminal 1 — backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt && playwright install chromium
python init_db.py
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm install && cp .env.example .env
npm run dev
```

---

### 🧪 Testing

```bash
# Backend tests
cd backend
pytest -v

# Frontend tests
cd frontend
npm test

# E2E tests (coming soon)
npm run test:e2e
```

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [OpenAI](https://openai.com) for GPT-4 Vision
- [Playwright](https://playwright.dev) for browser automation
- [FastAPI](https://fastapi.tiangolo.com) for the backend framework
- [React](https://react.dev) for the frontend framework
- [Tailwind CSS](https://tailwindcss.com) for styling

---

<p align="center">
  <a href="https://github.com/Pavan789bhanu/UI_State_Capture_System/issues">Report Bug</a> •
  <a href="https://github.com/Pavan789bhanu/UI_State_Capture_System/issues">Request Feature</a> •
  <a href="https://github.com/Pavan789bhanu/UI_State_Capture_System/discussions">Discussions</a>
</p>

<p align="center">
  Made by Pavan Kumar Malasani
</p>

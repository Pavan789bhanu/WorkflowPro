/**
 * Playground API Client
 * Handles all playground-related API calls
 */

import { API_BASE, getWsBase } from './baseUrls';

const API_BASE_URL = `${API_BASE}/api`;

export interface WorkflowStep {
  type: 'navigate' | 'click' | 'type' | 'wait' | 'select' | 'extract' | 'screenshot';
  selector?: string;
  value?: string;
  url?: string;
  timeout?: number;
  description: string;
}

export interface StepResult {
  step_type: string;
  status: 'success' | 'error';
  message: string;
  screenshot?: string;
  duration_ms: number;
  timestamp: string;
  data?: any;
}

export interface ExecutionResult {
  success: boolean;
  result: StepResult;
}

export interface WorkflowExecutionResult {
  success: boolean;
  total_steps: number;
  executed_steps: number;
  results: Array<{
    step_index: number;
    step: WorkflowStep;
    result: StepResult;
  }>;
}

export interface ParsedWorkflow {
  steps: WorkflowStep[];
  confidence: number;
  estimated_duration: number;
  requires_auth: boolean;
  warnings: string[];
}

export interface SelectorValidation {
  valid: boolean;
  count?: number;
  previews?: Array<{
    tag: string;
    text: string;
  }>;
  message: string;
}

// ── Automation run-live event types ──────────────────────────────────────────

export type AutomationEventType =
  | 'planning_start'
  | 'planning_complete'
  | 'browser_starting'
  | 'browser_ready'
  | 'step_start'
  | 'step_complete'
  | 'report_generating'
  | 'execution_stopped'
  | 'execution_complete'
  | 'error'
  | 'ws_closed';

export interface AgentPlan {
  start_url?: string;
  app_name?: string;
  outline?: string[];
  success_criteria?: string;
  requires_auth?: boolean;
  warnings?: string[];
  /** Query-rewriting output: precise, self-contained version of the user's query */
  rewritten_task?: string;
  search_terms?: string[];
  sub_goals?: string[];
}

export interface AgentUIStep {
  type: string;
  description: string;
  selector?: string | null;
  url?: string | null;
  value?: string | null;
  reason?: string;
}

export interface AutomationEvent {
  type: AutomationEventType;
  message?: string;
  steps?: AgentUIStep[];
  plan?: AgentPlan;
  mode?: 'agent' | 'script';
  confidence?: number;
  requires_auth?: boolean;
  warnings?: string[];
  estimated_duration?: number;
  step_index?: number;
  step?: AgentUIStep;
  result?: StepResult;
  total_steps?: number;
  reason?: string;
  success?: boolean;
  steps_planned?: number;
  steps_executed?: number;
  final_message?: string;
  report?: string;
  query?: string;
}

class PlaygroundAPI {
  private baseUrl: string;

  constructor() {
    this.baseUrl = API_BASE_URL;
  }

  /**
   * Parse natural language task into workflow
   */
  async parseTask(description: string, targetUrl?: string): Promise<ParsedWorkflow> {
    const response = await fetch(`${this.baseUrl}/ai/parse-task`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        description,
        target_url: targetUrl,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to parse task: ${response.statusText}`);
    }

    const data = await response.json();
    return data.workflow;
  }

  /**
   * Execute a single step
   */
  async executeStep(step: WorkflowStep): Promise<ExecutionResult> {
    const response = await fetch(`${this.baseUrl}/playground/execute-step`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        step,
        continue_from_current: true,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to execute step: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Execute entire workflow
   */
  async executeWorkflow(steps: WorkflowStep[], headless: boolean = false): Promise<WorkflowExecutionResult> {
    const response = await fetch(`${this.baseUrl}/playground/execute-workflow`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        steps,
        headless,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to execute workflow: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Validate a selector on current page
   */
  async validateSelector(selector: string): Promise<SelectorValidation> {
    const response = await fetch(`${this.baseUrl}/playground/validate-selector`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ selector }),
    });

    if (!response.ok) {
      throw new Error(`Failed to validate selector: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Get current page state
   */
  async getPageState(): Promise<{ url: string; title: string; viewport: any }> {
    const response = await fetch(`${this.baseUrl}/playground/page-state`);

    if (!response.ok) {
      throw new Error(`Failed to get page state: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Initialize browser
   */
  async initializeBrowser(headless: boolean = false): Promise<void> {
    const response = await fetch(`${this.baseUrl}/playground/initialize?headless=${headless}`, {
      method: 'POST',
    });

    if (!response.ok) {
      throw new Error(`Failed to initialize browser: ${response.statusText}`);
    }
  }

  /**
   * Cleanup browser
   */
  async cleanupBrowser(): Promise<void> {
    const response = await fetch(`${this.baseUrl}/playground/cleanup`, {
      method: 'POST',
    });

    if (!response.ok) {
      throw new Error(`Failed to cleanup browser: ${response.statusText}`);
    }
  }

  /**
   * Validate workflow steps
   */
  async validateWorkflow(steps: any[]): Promise<any> {
    const response = await fetch(`${this.baseUrl}/ai/validate-workflow`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ steps }),
    });

    if (!response.ok) {
      throw new Error(`Failed to validate workflow: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Get workflow templates
   */
  async getTemplates(category?: string, search?: string): Promise<any> {
    const params = new URLSearchParams();
    if (category) params.append('category', category);
    if (search) params.append('search', search);

    const response = await fetch(`${this.baseUrl}/ai/workflow-templates?${params}`);

    if (!response.ok) {
      throw new Error(`Failed to get templates: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Save workflow to database.
   * Note: requires auth — use apiClient.createWorkflow() instead, which
   * attaches the JWT and matches the backend schema. Kept for compatibility.
   */
  async saveWorkflow(name: string, description: string, steps: WorkflowStep[], appName = 'web'): Promise<unknown> {
    const token = localStorage.getItem('auth_token');
    const response = await fetch(`${this.baseUrl}/workflows/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        name,
        description,
        app_name: appName,
        start_url: steps.find((s) => s.type === 'navigate')?.url ?? null,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to save workflow: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Submit workflow feedback for learning
   */
  async submitFeedback(
    originalTask: string,
    generatedSteps: Array<WorkflowStep | AgentUIStep>,
    correctedSteps: Array<WorkflowStep | AgentUIStep>,
    feedbackType: 'correction' | 'success' | 'failure',
    url: string,
    notes?: string
  ): Promise<unknown> {
    const response = await fetch(`${this.baseUrl}/playground/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        original_task: originalTask,
        generated_steps: generatedSteps,
        corrected_steps: correctedSteps,
        feedback_type: feedbackType,
        url,
        notes,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to submit feedback: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Get workflow suggestions based on learning
   */
  async getSuggestions(taskDescription: string, url?: string): Promise<any> {
    const response = await fetch(`${this.baseUrl}/playground/suggestions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_description: taskDescription,
        url,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to get suggestions: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Get learning statistics
   */
  async getLearningStats(): Promise<any> {
    const response = await fetch(`${this.baseUrl}/playground/learning-stats`);

    if (!response.ok) {
      throw new Error(`Failed to get learning stats: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Open a WebSocket to /api/automation/run-live and stream automation events.
   *
   * @param query    Plain English task description
   * @param url      Optional target URL
   * @param headless Whether to run the browser headlessly
   * @param onEvent  Callback for every JSON message from the server
   * @returns        A cancel function — call it to close the WebSocket
   */
  runAutomationLive(
    query: string,
    url: string | undefined,
    headless: boolean,
    onEvent: (event: AutomationEvent) => void
  ): () => void {
    const wsUrl = `${getWsBase()}/api/automation/run-live`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      ws.send(JSON.stringify({ query, url: url ?? null, headless }));
    };

    ws.onmessage = (e) => {
      try {
        const event: AutomationEvent = JSON.parse(e.data as string);
        onEvent(event);
      } catch {
        // ignore malformed messages
      }
    };

    ws.onerror = () => {
      onEvent({ type: 'error', message: 'WebSocket connection error' });
    };

    ws.onclose = () => {
      onEvent({ type: 'ws_closed' });
    };

    // Cancel: politely ask the server to stop the run, then close.
    return () => {
      try {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'cancel' }));
        }
      } catch {
        // ignore
      }
      ws.close();
    };
  }
}

export const playgroundAPI = new PlaygroundAPI();

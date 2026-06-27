/**
 * Home — bento-grid mission control (Aurora Glass design system).
 * Same data sources as before: workflows + executions queries with
 * real-time WebSocket refresh.
 */
import {
  Workflow, Activity, ArrowRight, Plus, Zap, BarChart3, Sparkles, Clock,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../services/api';
import { useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { GlassCard, Stat, StatusBadge, EmptyState, Button, timeAgo } from '../components/ui/kit';

export default function Dashboard() {
  const navigate = useNavigate();
  const { isAuthenticated, isLoading: authLoading, user } = useAuth();

  const { data: executionsData, refetch: refetchExecutions } = useQuery({
    queryKey: ['recent-executions'],
    queryFn: async () => (await apiClient.getExecutions()).executions,
    enabled: isAuthenticated && !authLoading,
    refetchInterval: 3000,
    staleTime: 0,
  });

  const { data: workflowsData, refetch: refetchWorkflows } = useQuery({
    queryKey: ['recent-workflows'],
    queryFn: async () => (await apiClient.getWorkflows()).workflows,
    enabled: isAuthenticated && !authLoading,
    refetchInterval: 5000,
  });

  useEffect(() => {
    const handleUpdate = () => {
      refetchExecutions();
      refetchWorkflows();
    };
    apiClient.on('execution_created', handleUpdate);
    apiClient.on('execution_completed', handleUpdate);
    apiClient.on('workflow_created', handleUpdate);
    return () => {
      apiClient.off('execution_created', handleUpdate);
      apiClient.off('execution_completed', handleUpdate);
      apiClient.off('workflow_created', handleUpdate);
    };
  }, [refetchExecutions, refetchWorkflows]);

  const executions = executionsData ?? [];
  const workflows = workflowsData ?? [];
  const running = executions.filter((e) => e.status === 'RUNNING').length;
  const succeeded = executions.filter((e) => e.status === 'SUCCESS' || e.status === 'COMPLETED').length;
  const successRate = executions.length ? Math.round((succeeded / executions.length) * 100) : null;

  return (
    <div className="max-w-7xl mx-auto animate-fade-in">
      {/* ── Hero strip ─────────────────────────────────────────────── */}
      <GlassCard className="p-7 mb-5 relative overflow-hidden">
        <div
          className="absolute -right-20 -top-24 w-72 h-72 rounded-full opacity-30 blur-3xl pointer-events-none"
          style={{ background: 'linear-gradient(135deg, rgb(var(--brand)), rgb(var(--cta)))' }}
        />
        <div className="relative flex flex-col lg:flex-row lg:items-center gap-6">
          <div className="mr-auto">
            <p className="text-sm text-secondary mb-1">Welcome back,</p>
            <h2 className="font-display text-2xl font-bold text-primary capitalize">
              {user?.username || 'there'} <span aria-hidden>✦</span>
            </h2>
            <p className="text-sm text-secondary mt-2 max-w-md">
              Describe any task in plain English and watch the agent do it in a real browser.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button variant="cta" onClick={() => navigate('/playground')}>
              <Zap size={17} /> Run a task now
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                navigate('/workflows');
                window.dispatchEvent(new CustomEvent('create-workflow'));
              }}
            >
              <Plus size={17} /> New workflow
            </Button>
          </div>
        </div>
      </GlassCard>

      {/* ── Stats row ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5 stagger">
        <Stat label="Workflows" value={workflows.length} icon={<Workflow size={19} />} tone="brand" />
        <Stat
          label="Running now"
          value={running}
          icon={<Activity size={19} />}
          tone={running > 0 ? 'success' : 'neutral'}
          hint={running > 0 ? 'agents working live' : 'all quiet'}
        />
        <Stat label="Total runs" value={executions.length} icon={<BarChart3 size={19} />} tone="brand" />
        <Stat
          label="Success rate"
          value={successRate === null ? '—' : `${successRate}%`}
          icon={<Sparkles size={19} />}
          tone={successRate !== null && successRate >= 70 ? 'success' : 'warn'}
        />
      </div>

      {/* ── Bento: workflows + activity ────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
        <GlassCard className="lg:col-span-3 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display font-bold text-primary">Recent workflows</h3>
            <Link to="/workflows" className="text-sm font-medium text-brand inline-flex items-center gap-1 hover:gap-2 transition-all">
              View all <ArrowRight size={15} />
            </Link>
          </div>
          {workflows.length === 0 ? (
            <EmptyState
              icon={<Workflow size={26} />}
              title="No workflows yet"
              description="Save your first automation and re-run it any time."
              action={
                <Button onClick={() => { navigate('/workflows'); window.dispatchEvent(new CustomEvent('create-workflow')); }}>
                  <Plus size={16} /> Create workflow
                </Button>
              }
            />
          ) : (
            <div className="space-y-1">
              {workflows.slice(0, 6).map((wf) => (
                <button
                  key={wf.id}
                  onClick={() => navigate('/workflows')}
                  className="w-full flex items-center gap-3 p-3 rounded-xl text-left hover:bg-[rgba(var(--brand),0.06)] transition-colors group"
                >
                  <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
                    style={{ background: 'rgba(var(--brand), 0.12)', color: 'rgb(var(--brand))' }}>
                    <Workflow size={16} />
                  </div>
                  <div className="min-w-0 mr-auto">
                    <p className="text-sm font-semibold text-primary truncate">{wf.name}</p>
                    <p className="text-xs text-tertiary flex items-center gap-1">
                      <Clock size={11} /> {timeAgo(wf.updated_at || wf.created_at)}
                    </p>
                  </div>
                  <span className="stat-number text-xs text-secondary hidden sm:block">
                    {wf.execution_count ?? 0} runs
                  </span>
                  <ArrowRight size={15} className="text-tertiary opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all" />
                </button>
              ))}
            </div>
          )}
        </GlassCard>

        <GlassCard className="lg:col-span-2 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display font-bold text-primary flex items-center gap-2">
              Activity {running > 0 && <span className="live-dot" />}
            </h3>
            <Link to="/executions" className="text-sm font-medium text-brand inline-flex items-center gap-1 hover:gap-2 transition-all">
              View all <ArrowRight size={15} />
            </Link>
          </div>
          {executions.length === 0 ? (
            <EmptyState icon={<Activity size={26} />} title="No activity yet" description="Run a workflow or try the Playground." />
          ) : (
            <div className="space-y-1">
              {executions.slice(0, 7).map((ex) => (
                <button
                  key={ex.id}
                  onClick={() => navigate('/executions')}
                  className="w-full flex items-center gap-3 p-2.5 rounded-xl text-left hover:bg-[rgba(var(--brand),0.06)] transition-colors"
                >
                  <div className="min-w-0 mr-auto">
                    <p className="text-sm font-medium text-primary truncate">{ex.workflow_name || 'Run'}</p>
                    <p className="text-[11px] text-tertiary">{timeAgo(ex.started_at)}</p>
                  </div>
                  <StatusBadge status={ex.status} />
                </button>
              ))}
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  );
}

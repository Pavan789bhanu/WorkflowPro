/**
 * Executions — live run monitor (Aurora Glass + Real-Time Monitoring style).
 * Functionality preserved: list + live updates, search/status filter,
 * report float-window viewer, thumbs feedback → learning system, delete,
 * cancel running runs.
 */
import {
  Activity, Search, Trash2, Eye, ExternalLink, X, RefreshCw,
  ThumbsUp, ThumbsDown, CheckCircle2, StopCircle, Maximize2, Minimize2,
} from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient, type Execution } from '../services/api';
import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNotifications } from '../contexts/NotificationContext';
import {
  GlassCard, PageHeader, Button, StatusBadge, EmptyState, Modal,
  TextInput, Stat, timeAgo, formatDuration,
} from '../components/ui/kit';

type StatusFilter = 'all' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'PENDING';

export default function ExecutionsPage() {
  const queryClient = useQueryClient();
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const { addNotification } = useNotifications();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [reportFor, setReportFor] = useState<Execution | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Execution | null>(null);

  const { data, refetch, isFetching } = useQuery({
    queryKey: ['executions'],
    queryFn: async () => (await apiClient.getExecutions()).executions,
    enabled: isAuthenticated && !authLoading,
    refetchInterval: 3000,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiClient.deleteExecution(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['executions'] });
      addNotification({ type: 'success', title: 'Execution deleted', message: 'The run record was removed.' });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (id: string) => apiClient.stopExecution(id),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['executions'] });
      addNotification({
        type: res.cancelled ? 'success' : 'info',
        title: res.cancelled ? 'Run cancelled' : 'Could not cancel',
        message: res.message,
      });
    },
  });

  // Real-time refresh via app WebSocket
  useEffect(() => {
    const handleUpdate = () => refetch();
    const events = ['execution_created', 'execution_updated', 'execution_completed',
      'execution_started', 'execution_progress', 'execution_failed'];
    events.forEach((e) => apiClient.on(e, handleUpdate));
    return () => events.forEach((e) => apiClient.off(e, handleUpdate));
  }, [refetch]);

  const executions = useMemo(() => data ?? [], [data]);
  const filtered = executions.filter((ex) => {
    if (statusFilter !== 'all') {
      const ok = statusFilter === 'SUCCESS'
        ? ex.status === 'SUCCESS' || ex.status === 'COMPLETED'
        : ex.status === statusFilter;
      if (!ok) return false;
    }
    if (search && !(ex.workflow_name || '').toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const running = executions.filter((e) => e.status === 'RUNNING').length;
  const succeeded = executions.filter((e) => e.status === 'SUCCESS' || e.status === 'COMPLETED').length;
  const failed = executions.filter((e) => e.status === 'FAILED').length;

  return (
    <div className="max-w-7xl mx-auto">
      <PageHeader
        icon={<Activity size={22} />}
        title="Executions"
        subtitle="Every agent run, live"
        actions={
          <button onClick={() => refetch()} className="icon-btn" title="Refresh">
            <RefreshCw size={17} className={isFetching ? 'animate-spin' : ''} />
          </button>
        }
      />

      {/* Live stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5 stagger">
        <Stat label="Total runs" value={executions.length} tone="brand" icon={<Activity size={18} />} />
        <Stat label="Running" value={running} tone={running ? 'success' : 'neutral'}
          icon={running ? <span className="live-dot" /> : <Activity size={18} />} />
        <Stat label="Succeeded" value={succeeded} tone="success" icon={<CheckCircle2 size={18} />} />
        <Stat label="Failed" value={failed} tone={failed ? 'danger' : 'neutral'} icon={<X size={18} />} />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="relative max-w-xs flex-1 min-w-[200px]">
          <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-tertiary pointer-events-none" />
          <TextInput
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by workflow…"
            className="!pl-9 !py-2"
            aria-label="Search executions"
          />
        </div>
        <div className="glass rounded-xl p-1 flex gap-0.5">
          {(['all', 'RUNNING', 'SUCCESS', 'FAILED', 'PENDING'] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold capitalize transition-colors"
              style={{
                background: statusFilter === s ? 'rgba(var(--brand), 0.15)' : 'transparent',
                color: statusFilter === s ? 'rgb(var(--brand))' : 'rgb(var(--text-tertiary))',
              }}
            >
              {s === 'all' ? 'All' : s.toLowerCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <GlassCard className="overflow-hidden">
        {filtered.length === 0 ? (
          <EmptyState
            icon={<Activity size={26} />}
            title={search || statusFilter !== 'all' ? 'No runs match the filters' : 'No runs yet'}
            description="Start a workflow or use the Playground — runs appear here in real time."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(var(--border-color), 0.8)' }}>
                  <th className="table-head">Workflow</th>
                  <th className="table-head">Status</th>
                  <th className="table-head hidden md:table-cell">Started</th>
                  <th className="table-head hidden lg:table-cell">Duration</th>
                  <th className="table-head text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((ex) => (
                  <ExecutionRow
                    key={ex.id}
                    execution={ex}
                    onViewReport={() => setReportFor(ex)}
                    onDelete={() => setDeleteTarget(ex)}
                    onCancel={() => cancelMutation.mutate(String(ex.id))}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>

      {reportFor && <ReportFloat execution={reportFor} onClose={() => setReportFor(null)} />}

      {deleteTarget && (
        <Modal title="Delete execution?" onClose={() => setDeleteTarget(null)}>
          <p className="text-sm text-secondary mb-5">
            This permanently removes the run record for “{deleteTarget.workflow_name}”.
          </p>
          <div className="flex gap-3">
            <Button variant="ghost" className="flex-1" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button
              variant="danger"
              className="flex-1"
              loading={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate(String(deleteTarget.id), { onSettled: () => setDeleteTarget(null) })}
            >
              <Trash2 size={15} /> Delete
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}

/* ── Row ──────────────────────────────────────────────────────────── */

function ExecutionRow({
  execution, onViewReport, onDelete, onCancel,
}: {
  execution: Execution;
  onViewReport: () => void;
  onDelete: () => void;
  onCancel: () => void;
}) {
  const isRunning = execution.status === 'RUNNING';
  const [liveSeconds, setLiveSeconds] = useState(0);

  useEffect(() => {
    if (!isRunning || !execution.started_at) return;
    const tick = () =>
      setLiveSeconds(Math.max(0, Math.floor((Date.now() - new Date(execution.started_at!).getTime()) / 1000)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [isRunning, execution.started_at]);

  const canViewReport = execution.status !== 'PENDING' && !isRunning;

  return (
    <tr className="table-row">
      <td className="px-4 py-3">
        <p className="text-sm font-semibold text-primary truncate max-w-[260px]">
          {execution.workflow_name || 'Run'}
        </p>
        <p className="text-[11px] text-tertiary stat-number">#{execution.id}</p>
      </td>
      <td className="px-4 py-3"><StatusBadge status={execution.status} /></td>
      <td className="px-4 py-3 hidden md:table-cell text-xs text-secondary">
        {timeAgo(execution.started_at)}
      </td>
      <td className="px-4 py-3 hidden lg:table-cell stat-number text-sm text-secondary">
        {isRunning ? formatDuration(liveSeconds) : formatDuration(execution.duration)}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center justify-end gap-0.5">
          {canViewReport && <FeedbackButtons execution={execution} />}
          {isRunning && (
            <button className="icon-btn !p-1.5 hover:!text-red-500 hover:!bg-red-500/10" title="Cancel run" onClick={onCancel}>
              <StopCircle size={16} />
            </button>
          )}
          <button
            className="icon-btn !p-1.5"
            title="View report"
            disabled={!canViewReport}
            style={!canViewReport ? { opacity: 0.35, cursor: 'not-allowed' } : undefined}
            onClick={onViewReport}
          >
            <Eye size={16} />
          </button>
          <button className="icon-btn !p-1.5 hover:!text-red-500 hover:!bg-red-500/10" title="Delete" onClick={onDelete}>
            <Trash2 size={16} />
          </button>
        </div>
      </td>
    </tr>
  );
}

/* ── Feedback (→ learning system) ─────────────────────────────────── */

export function FeedbackButtons({ execution }: { execution: Execution }) {
  const existing = (() => {
    try {
      const parsed = typeof execution.result === 'string' ? JSON.parse(execution.result) : execution.result;
      return parsed?.user_feedback?.rating as 'positive' | 'negative' | undefined;
    } catch {
      return undefined;
    }
  })();
  const [given, setGiven] = useState<'positive' | 'negative' | null>(existing ?? null);
  const [showNotes, setShowNotes] = useState(false);
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (rating: 'positive' | 'negative', text?: string) => {
    setBusy(true);
    try {
      await apiClient.submitExecutionFeedback(execution.id, rating, text);
      setGiven(rating);
      setShowNotes(false);
    } catch {
      /* non-fatal */
    } finally {
      setBusy(false);
    }
  };

  if (given) {
    return (
      <span className="p-1.5" style={{ color: 'rgb(var(--cta))' }} title={`Feedback recorded (${given})`}>
        <CheckCircle2 size={15} />
      </span>
    );
  }

  return (
    <div className="relative flex items-center">
      <button
        onClick={() => submit('positive')}
        disabled={busy}
        className="icon-btn !p-1.5 hover:!text-emerald-600 hover:!bg-emerald-500/10"
        title="Worked well — teach the model this run was good"
      >
        <ThumbsUp size={15} />
      </button>
      <button
        onClick={() => setShowNotes((v) => !v)}
        disabled={busy}
        className="icon-btn !p-1.5 hover:!text-red-500 hover:!bg-red-500/10"
        title="Didn't work — tell the model what went wrong"
      >
        <ThumbsDown size={15} />
      </button>
      {showNotes && (
        <div className="absolute top-full right-0 mt-2 w-72 z-50 animate-scale-in">
          <div className="glass-card p-3" style={{ background: 'rgba(var(--bg-secondary), 0.97)' }}>
            <p className="text-xs font-semibold text-primary mb-2">What went wrong? (optional)</p>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="e.g. It opened the wrong article / missed the cookie banner…"
              className="field !text-xs resize-none"
            />
            <div className="flex gap-2 mt-2">
              <Button variant="ghost" className="flex-1 !py-1.5 !text-xs" onClick={() => setShowNotes(false)}>
                Cancel
              </Button>
              <Button variant="danger" className="flex-1 !py-1.5 !text-xs" loading={busy}
                onClick={() => submit('negative', notes.trim() || undefined)}>
                Send feedback
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Floating report window ───────────────────────────────────────── */

function ReportFloat({ execution, onClose }: { execution: Execution; onClose: () => void }) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const reportUrl = apiClient.getReportUrl(execution.id);
  const ok = execution.status === 'SUCCESS' || execution.status === 'COMPLETED';

  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [onClose]);

  return (
    /* Float: bottom-right, no blocking backdrop — page stays interactive. */
    <div
      className={
        isFullscreen
          ? 'fixed inset-0 z-[95] flex items-center justify-center p-4 animate-fade-in'
          : 'fixed bottom-5 right-5 z-[95] pointer-events-none animate-scale-in'
      }
      style={isFullscreen ? { background: 'rgba(20,16,60,0.45)', backdropFilter: 'blur(6px)' } : undefined}
      onClick={isFullscreen ? onClose : undefined}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`pointer-events-auto glass-card flex flex-col overflow-hidden transition-all duration-300 ${
          isFullscreen
            ? 'w-[calc(100vw-32px)] h-[calc(100vh-32px)]'
            : 'w-[min(620px,calc(100vw-40px))] h-[min(560px,calc(100vh-80px))]'
        }`}
        style={{ background: 'rgba(var(--bg-secondary), 0.95)' }}
      >
        {/* Slim header — report starts immediately below */}
        <div className="flex items-center gap-2.5 px-4 py-2.5 shrink-0"
          style={{ borderBottom: '1px solid rgba(var(--border-color), 0.8)' }}>
          <span
            className="w-2.5 h-2.5 rounded-full shrink-0"
            style={{ background: ok ? 'rgb(var(--cta))' : 'rgb(var(--danger))' }}
            title={execution.status}
          />
          <div className="min-w-0 mr-auto">
            <p className="text-sm font-semibold text-primary truncate leading-tight">
              {execution.workflow_name || 'Execution Report'}
            </p>
            <p className="text-[10px] text-tertiary truncate stat-number">
              #{execution.id}
              {execution.duration ? ` · ${formatDuration(execution.duration)}` : ''}
              {execution.started_at ? ` · ${new Date(execution.started_at).toLocaleString()}` : ''}
            </p>
          </div>
          <FeedbackButtons execution={execution} />
          <button onClick={() => setIsFullscreen((v) => !v)} className="icon-btn !p-1.5"
            title={isFullscreen ? 'Float window' : 'Fullscreen'}>
            {isFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>
          <button onClick={() => window.open(reportUrl, '_blank', 'width=1400,height=900')}
            className="icon-btn !p-1.5" title="Open in new tab">
            <ExternalLink size={15} />
          </button>
          <button onClick={onClose} className="icon-btn !p-1.5" title="Close (Esc)">
            <X size={16} />
          </button>
        </div>

        <iframe
          src={reportUrl}
          className="flex-1 w-full border-0 bg-white"
          title="Execution Report"
          sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
        />
      </div>
    </div>
  );
}

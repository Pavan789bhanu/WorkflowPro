/**
 * Workflows — saved automations (Aurora Glass design system).
 * Functionality preserved: list, search, grid/list view, create, edit,
 * delete (with confirm), run, real-time refresh.
 */
import {
  Play, Edit3, Trash2, Clock, Plus, Search, LayoutGrid, List, RefreshCw,
  Workflow as WorkflowIcon, Globe, KeyRound, ChevronDown, ChevronUp,
} from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient, type Workflow } from '../services/api';
import { useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useSearchParams } from 'react-router-dom';
import { useNotifications } from '../contexts/NotificationContext';
import {
  GlassCard, PageHeader, Button, StatusBadge, EmptyState, Modal, Field,
  TextInput, TextArea, timeAgo,
} from '../components/ui/kit';

type ViewMode = 'grid' | 'list';

export default function WorkflowsPage() {
  const queryClient = useQueryClient();
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [searchParams] = useSearchParams();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editWorkflow, setEditWorkflow] = useState<Workflow | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Workflow | null>(null);
  const [searchQuery, setSearchQuery] = useState(searchParams.get('q') || '');
  const [viewMode, setViewMode] = useState<ViewMode>(
    () => (localStorage.getItem('workflowViewMode') as ViewMode) || 'grid'
  );
  const { addNotification } = useNotifications();

  const { data: workflowsData, refetch, isFetching } = useQuery({
    queryKey: ['workflows'],
    queryFn: async () => apiClient.getWorkflows(),
    enabled: isAuthenticated && !authLoading,
  });

  const handleViewModeChange = (mode: ViewMode) => {
    setViewMode(mode);
    localStorage.setItem('workflowViewMode', mode);
  };

  const runWorkflowMutation = useMutation({
    mutationFn: async (workflowId: string) =>
      apiClient.createExecution({ workflow_id: workflowId, headless: false }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      queryClient.invalidateQueries({ queryKey: ['executions'] });
      addNotification({ type: 'success', title: 'Run started', message: 'The agent is on it — watch progress in Executions.' });
    },
    onError: () =>
      addNotification({ type: 'error', title: 'Run failed to start', message: 'Please try again.' }),
  });

  const deleteWorkflowMutation = useMutation({
    mutationFn: async (workflowId: string) => apiClient.deleteWorkflow(workflowId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      addNotification({ type: 'success', title: 'Workflow deleted', message: 'The workflow has been removed.' });
    },
    onError: () =>
      addNotification({ type: 'error', title: 'Delete failed', message: 'Failed to delete the workflow. Please try again.' }),
  });

  // Real-time refresh
  useEffect(() => {
    const handleUpdate = () => refetch();
    apiClient.on('workflow_created', handleUpdate);
    apiClient.on('workflow_updated', handleUpdate);
    apiClient.on('workflow_deleted', handleUpdate);
    apiClient.on('execution_completed', handleUpdate);
    return () => {
      apiClient.off('workflow_created', handleUpdate);
      apiClient.off('workflow_updated', handleUpdate);
      apiClient.off('workflow_deleted', handleUpdate);
      apiClient.off('execution_completed', handleUpdate);
    };
  }, [refetch]);

  // "New Workflow" from header/dashboard
  useEffect(() => {
    const open = () => setShowCreateModal(true);
    window.addEventListener('create-workflow', open);
    return () => window.removeEventListener('create-workflow', open);
  }, []);

  const workflows = workflowsData?.workflows || [];
  const filtered = workflows.filter((wf: Workflow) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return wf.name?.toLowerCase().includes(q) || wf.description?.toLowerCase().includes(q);
  });

  return (
    <div className="max-w-7xl mx-auto">
      <PageHeader
        icon={<WorkflowIcon size={22} />}
        title="Workflows"
        subtitle={`${workflows.length} saved automation${workflows.length === 1 ? '' : 's'}`}
        actions={
          <>
            <button onClick={() => refetch()} className="icon-btn" title="Refresh">
              <RefreshCw size={17} className={isFetching ? 'animate-spin' : ''} />
            </button>
            <div className="glass rounded-xl p-1 flex">
              {(['grid', 'list'] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => handleViewModeChange(mode)}
                  className="p-1.5 rounded-lg transition-colors"
                  style={{
                    background: viewMode === mode ? 'rgba(var(--brand), 0.15)' : 'transparent',
                    color: viewMode === mode ? 'rgb(var(--brand))' : 'rgb(var(--text-tertiary))',
                  }}
                  title={`${mode} view`}
                >
                  {mode === 'grid' ? <LayoutGrid size={16} /> : <List size={16} />}
                </button>
              ))}
            </div>
            <Button onClick={() => setShowCreateModal(true)}>
              <Plus size={16} /> New Workflow
            </Button>
          </>
        }
      />

      {/* Search */}
      <div className="relative mb-5 max-w-md">
        <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-tertiary pointer-events-none" />
        <TextInput
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search workflows…"
          className="!pl-10"
          aria-label="Search workflows"
        />
      </div>

      {filtered.length === 0 ? (
        <GlassCard className="p-6">
          <EmptyState
            icon={<WorkflowIcon size={26} />}
            title={searchQuery ? 'No workflows match your search' : 'No workflows yet'}
            description={searchQuery ? 'Try a different keyword.' : 'Save an automation once, run it forever.'}
            action={
              !searchQuery && (
                <Button onClick={() => setShowCreateModal(true)}>
                  <Plus size={16} /> Create your first workflow
                </Button>
              )
            }
          />
        </GlassCard>
      ) : viewMode === 'grid' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 stagger">
          {filtered.map((wf: Workflow, i: number) => (
            <WorkflowCard
              key={wf.id}
              workflow={wf}
              index={i}
              running={runWorkflowMutation.isPending}
              onRun={() => runWorkflowMutation.mutate(wf.id)}
              onEdit={() => setEditWorkflow(wf)}
              onDelete={() => setDeleteTarget(wf)}
            />
          ))}
        </div>
      ) : (
        <GlassCard className="overflow-hidden">
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(var(--border-color), 0.8)' }}>
                <th className="table-head">Workflow</th>
                <th className="table-head hidden md:table-cell">App</th>
                <th className="table-head hidden lg:table-cell">Runs</th>
                <th className="table-head hidden sm:table-cell">Updated</th>
                <th className="table-head text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((wf: Workflow) => (
                <tr key={wf.id} className="table-row">
                  <td className="px-4 py-3">
                    <p className="text-sm font-semibold text-primary">{wf.name}</p>
                    <p className="text-xs text-tertiary truncate max-w-[320px]">{wf.description}</p>
                  </td>
                  <td className="px-4 py-3 hidden md:table-cell text-sm text-secondary">{wf.app_name}</td>
                  <td className="px-4 py-3 hidden lg:table-cell stat-number text-sm text-secondary">
                    {wf.execution_count ?? 0}
                  </td>
                  <td className="px-4 py-3 hidden sm:table-cell text-xs text-tertiary">
                    {timeAgo(wf.updated_at || wf.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <button className="icon-btn !p-1.5" title="Run now" onClick={() => runWorkflowMutation.mutate(wf.id)}>
                        <Play size={15} />
                      </button>
                      <button className="icon-btn !p-1.5" title="Edit" onClick={() => setEditWorkflow(wf)}>
                        <Edit3 size={15} />
                      </button>
                      <button
                        className="icon-btn !p-1.5 hover:!text-red-500 hover:!bg-red-500/10"
                        title="Delete"
                        onClick={() => setDeleteTarget(wf)}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </GlassCard>
      )}

      {showCreateModal && <CreateWorkflowModal onClose={() => setShowCreateModal(false)} />}
      {editWorkflow && <EditWorkflowModal workflow={editWorkflow} onClose={() => setEditWorkflow(null)} />}
      {deleteTarget && (
        <Modal title="Delete workflow?" onClose={() => setDeleteTarget(null)}>
          <p className="text-sm text-secondary mb-5">
            “{deleteTarget.name}” and its execution history will be permanently removed.
          </p>
          <div className="flex gap-3">
            <Button variant="ghost" className="flex-1" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              className="flex-1"
              loading={deleteWorkflowMutation.isPending}
              onClick={() => {
                deleteWorkflowMutation.mutate(deleteTarget.id, { onSettled: () => setDeleteTarget(null) });
              }}
            >
              <Trash2 size={15} /> Delete
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}

/* ── Card ─────────────────────────────────────────────────────────── */

function WorkflowCard({
  workflow, index, running, onRun, onEdit, onDelete,
}: {
  workflow: Workflow; index: number; running: boolean;
  onRun: () => void; onEdit: () => void; onDelete: () => void;
}) {
  return (
    <GlassCard hover className="p-5 flex flex-col animate-fade-in-up" >
      <div className="flex items-start gap-3 mb-3" style={{ animationDelay: `${index * 40}ms` }}>
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: 'rgba(var(--brand), 0.12)', color: 'rgb(var(--brand))' }}
        >
          <WorkflowIcon size={18} />
        </div>
        <div className="min-w-0 mr-auto">
          <h3 className="font-semibold text-primary truncate">{workflow.name}</h3>
          <p className="text-xs text-tertiary flex items-center gap-1 mt-0.5">
            <Globe size={11} /> {workflow.app_name}
          </p>
        </div>
        <StatusBadge status={workflow.status} />
      </div>

      <p className="text-sm text-secondary line-clamp-2 mb-4 flex-1">{workflow.description}</p>

      <div className="flex items-center justify-between text-xs text-tertiary mb-4">
        <span className="flex items-center gap-1">
          <Clock size={11} /> {timeAgo(workflow.updated_at || workflow.created_at)}
        </span>
        <span className="stat-number">
          {workflow.execution_count ?? 0} runs
          {typeof workflow.success_count === 'number' && (workflow.execution_count ?? 0) > 0 &&
            ` · ${Math.round((workflow.success_count / (workflow.execution_count || 1)) * 100)}% ok`}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <Button variant="cta" className="flex-1 !py-2" onClick={onRun} loading={running}>
          <Play size={15} /> Run
        </Button>
        <button className="icon-btn" title="Edit" onClick={onEdit}>
          <Edit3 size={16} />
        </button>
        <button className="icon-btn hover:!text-red-500 hover:!bg-red-500/10" title="Delete" onClick={onDelete}>
          <Trash2 size={16} />
        </button>
      </div>
    </GlassCard>
  );
}

/* ── Create ───────────────────────────────────────────────────────── */

function CreateWorkflowModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const { addNotification } = useNotifications();
  const [showCreds, setShowCreds] = useState(false);
  const [formData, setFormData] = useState({
    name: '', description: '', app_name: '', start_url: '',
    login_email: '', login_password: '',
  });

  const createMutation = useMutation({
    mutationFn: async (data: typeof formData) => apiClient.createWorkflow(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      addNotification({ type: 'success', title: 'Workflow created', message: `“${formData.name}” is ready to run.` });
      onClose();
    },
    onError: (err: Error) =>
      addNotification({ type: 'error', title: 'Create failed', message: err.message }),
  });

  return (
    <Modal title="Create workflow" onClose={onClose}>
      <form
        onSubmit={(e) => { e.preventDefault(); createMutation.mutate(formData); }}
        className="space-y-4"
      >
        <Field label="Name">
          <TextInput
            required autoFocus value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            placeholder="e.g. Weekly Medium digest"
          />
        </Field>
        <Field label="Task (plain English)">
          <TextArea
            required rows={3} value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            placeholder="Search Medium for RAG articles from this week and summarize each one"
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="App / site">
            <TextInput
              required value={formData.app_name}
              onChange={(e) => setFormData({ ...formData, app_name: e.target.value })}
              placeholder="Medium, Jira…"
            />
          </Field>
          <Field label="Start URL" optional>
            <TextInput
              type="url" value={formData.start_url}
              onChange={(e) => setFormData({ ...formData, start_url: e.target.value })}
              placeholder="https://…"
            />
          </Field>
        </div>

        <button
          type="button"
          onClick={() => setShowCreds((v) => !v)}
          className="flex items-center gap-1.5 text-xs font-medium text-brand"
        >
          <KeyRound size={13} />
          Site credentials {showCreds ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
        {showCreds && (
          <div className="grid grid-cols-2 gap-3 animate-fade-in">
            <Field label="Login email" optional>
              <TextInput
                type="email" value={formData.login_email}
                onChange={(e) => setFormData({ ...formData, login_email: e.target.value })}
                placeholder="bot@company.com"
              />
            </Field>
            <Field label="Login password" optional>
              <TextInput
                type="password" value={formData.login_password}
                onChange={(e) => setFormData({ ...formData, login_password: e.target.value })}
                placeholder="Stored encrypted"
              />
            </Field>
          </div>
        )}

        <div className="flex gap-3 pt-1">
          <Button type="button" variant="ghost" className="flex-1" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" className="flex-1" loading={createMutation.isPending}>
            Create workflow
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/* ── Edit ─────────────────────────────────────────────────────────── */

function EditWorkflowModal({ workflow, onClose }: { workflow: Workflow; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { addNotification } = useNotifications();
  const [formData, setFormData] = useState({
    name: workflow.name,
    description: workflow.description,
    status: workflow.status,
  });

  const updateMutation = useMutation({
    mutationFn: async (data: typeof formData) => apiClient.updateWorkflow(workflow.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      addNotification({ type: 'success', title: 'Workflow updated', message: `“${formData.name}” saved.` });
      onClose();
    },
    onError: (err: Error) =>
      addNotification({ type: 'error', title: 'Update failed', message: err.message }),
  });

  return (
    <Modal title="Edit workflow" onClose={onClose}>
      <form
        onSubmit={(e) => { e.preventDefault(); updateMutation.mutate(formData); }}
        className="space-y-4"
      >
        <Field label="Name">
          <TextInput
            required value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          />
        </Field>
        <Field label="Task (plain English)">
          <TextArea
            required rows={3} value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          />
        </Field>
        <Field label="Status">
          <div className="flex gap-2">
            {(['active', 'paused'] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setFormData({ ...formData, status: s })}
                className="badge capitalize px-3 py-1.5"
                style={{
                  background: formData.status === s ? 'rgba(var(--brand), 0.15)' : 'rgba(var(--border-color), 0.5)',
                  color: formData.status === s ? 'rgb(var(--brand))' : 'rgb(var(--text-secondary))',
                  border: formData.status === s ? '1px solid rgba(var(--brand), 0.4)' : '1px solid transparent',
                }}
              >
                {s}
              </button>
            ))}
          </div>
        </Field>
        <div className="flex gap-3 pt-1">
          <Button type="button" variant="ghost" className="flex-1" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" className="flex-1" loading={updateMutation.isPending}>
            Save changes
          </Button>
        </div>
      </form>
    </Modal>
  );
}

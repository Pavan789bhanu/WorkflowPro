/**
 * Profile — account overview (Aurora Glass).
 */
import { User, Mail, Shield, Activity, Workflow as WorkflowIcon, LogOut } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import { apiClient } from '../services/api';
import { GlassCard, PageHeader, Stat, Button } from '../components/ui/kit';

export default function ProfilePage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const { data: workflows } = useQuery({
    queryKey: ['workflows'],
    queryFn: async () => (await apiClient.getWorkflows()).workflows,
  });
  const { data: executions } = useQuery({
    queryKey: ['executions'],
    queryFn: async () => (await apiClient.getExecutions()).executions,
  });

  const succeeded = (executions ?? []).filter((e) => e.status === 'SUCCESS' || e.status === 'COMPLETED').length;

  return (
    <div className="max-w-4xl mx-auto">
      <PageHeader icon={<User size={22} />} title="Profile" subtitle="Your account at a glance" />

      <GlassCard className="p-7 mb-5 flex flex-col sm:flex-row items-start sm:items-center gap-5">
        <div
          className="w-20 h-20 rounded-3xl flex items-center justify-center text-white text-3xl font-bold font-display shrink-0 animate-float"
          style={{ background: 'linear-gradient(135deg, rgb(var(--brand)), rgb(var(--cta)))' }}
        >
          {(user?.username?.[0] || 'U').toUpperCase()}
        </div>
        <div className="mr-auto">
          <h2 className="font-display text-xl font-bold text-primary capitalize">{user?.username || 'User'}</h2>
          <p className="text-sm text-secondary flex items-center gap-1.5 mt-1">
            <Mail size={13} /> {user?.email || '—'}
          </p>
          <p className="text-xs text-tertiary flex items-center gap-1.5 mt-1">
            <Shield size={12} /> Authenticated session
          </p>
        </div>
        <Button variant="ghost" onClick={() => { logout(); navigate('/'); }}>
          <LogOut size={15} /> Sign out
        </Button>
      </GlassCard>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Stat label="Workflows" value={workflows?.length ?? '—'} icon={<WorkflowIcon size={18} />} tone="brand" />
        <Stat label="Total runs" value={executions?.length ?? '—'} icon={<Activity size={18} />} tone="brand" />
        <Stat label="Successful runs" value={succeeded} icon={<Activity size={18} />} tone="success" />
      </div>
    </div>
  );
}

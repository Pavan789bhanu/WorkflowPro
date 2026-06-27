/**
 * Analytics — performance insight (Aurora Glass + Executive Dashboard style).
 * Data: /analytics/overview + /analytics/top-workflows with live refresh.
 */
import { TrendingUp, Activity, CheckCircle2, XCircle, Trophy, Timer } from 'lucide-react';
import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { GlassCard, PageHeader, Stat, EmptyState, formatDuration } from '../components/ui/kit';

export default function AnalyticsPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  const { data: overview, refetch: refetchOverview } = useQuery({
    queryKey: ['analytics-overview'],
    queryFn: async () => apiClient.getAnalyticsOverview(),
    enabled: isAuthenticated && !authLoading,
    refetchInterval: 10000,
  });

  const { data: topWorkflows, refetch: refetchTop } = useQuery({
    queryKey: ['top-workflows'],
    queryFn: async () => (await apiClient.getTopWorkflows()).workflows,
    enabled: isAuthenticated && !authLoading,
    refetchInterval: 15000,
  });

  useEffect(() => {
    const handleUpdate = () => {
      refetchOverview();
      refetchTop();
    };
    apiClient.on('execution_completed', handleUpdate);
    apiClient.on('workflow_created', handleUpdate);
    return () => {
      apiClient.off('execution_completed', handleUpdate);
      apiClient.off('workflow_created', handleUpdate);
    };
  }, [refetchOverview, refetchTop]);

  const successRate = overview?.success_rate ?? 0;
  const ringStyle = {
    background: `conic-gradient(rgb(var(--cta)) ${successRate * 3.6}deg, rgba(var(--border-color), 0.6) 0deg)`,
  };

  return (
    <div className="max-w-7xl mx-auto">
      <PageHeader
        icon={<TrendingUp size={22} />}
        title="Analytics"
        subtitle="How your automations are performing"
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5 stagger">
        <Stat label="Workflows" value={overview?.total_workflows ?? '—'} icon={<Activity size={18} />} tone="brand"
          hint={`${overview?.active_workflows ?? 0} active`} />
        <Stat label="Total runs" value={overview?.total_executions ?? '—'} icon={<Activity size={18} />} tone="brand"
          hint={`${overview?.running_executions ?? 0} running now`} />
        <Stat label="Succeeded" value={overview?.success_executions ?? '—'} icon={<CheckCircle2 size={18} />} tone="success" />
        <Stat label="Failed" value={overview?.failed_executions ?? '—'} icon={<XCircle size={18} />}
          tone={(overview?.failed_executions ?? 0) > 0 ? 'danger' : 'neutral'} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Success ring */}
        <GlassCard className="p-6 flex flex-col items-center justify-center text-center">
          <h3 className="font-display font-bold text-primary mb-5 self-start">Success rate</h3>
          <div className="relative w-44 h-44 rounded-full animate-fade-in" style={ringStyle}>
            <div
              className="absolute inset-3 rounded-full flex flex-col items-center justify-center"
              style={{ background: 'rgb(var(--bg-secondary))' }}
            >
              <span className="stat-number text-4xl font-bold text-primary">{Math.round(successRate)}%</span>
              <span className="text-xs text-tertiary mt-1">of all runs</span>
            </div>
          </div>
          <p className="text-xs text-secondary mt-5 flex items-center gap-1.5">
            <Timer size={13} /> avg duration {formatDuration(Math.round(overview?.average_duration ?? 0))}
          </p>
        </GlassCard>

        {/* Top workflows */}
        <GlassCard className="lg:col-span-2 p-6">
          <h3 className="font-display font-bold text-primary mb-5 flex items-center gap-2">
            <Trophy size={16} style={{ color: 'rgb(var(--warn))' }} /> Top workflows
          </h3>
          {!topWorkflows || topWorkflows.length === 0 ? (
            <EmptyState
              icon={<Trophy size={26} />}
              title="No data yet"
              description="Run some workflows and the leaderboard fills in."
            />
          ) : (
            <div className="space-y-4">
              {topWorkflows.slice(0, 6).map((wf, i) => (
                <div key={wf.id} className="animate-fade-in-up" style={{ animationDelay: `${i * 50}ms` }}>
                  <div className="flex items-center justify-between mb-1.5">
                    <p className="text-sm font-semibold text-primary truncate mr-3">
                      <span className="stat-number text-tertiary mr-2">#{i + 1}</span>
                      {wf.name}
                    </p>
                    <p className="stat-number text-xs text-secondary shrink-0">
                      {wf.execution_count} runs · {Math.round(wf.success_rate)}% ok
                    </p>
                  </div>
                  <div className="h-2 rounded-full overflow-hidden" style={{ background: 'rgba(var(--border-color), 0.6)' }}>
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{
                        width: `${Math.max(4, wf.success_rate)}%`,
                        background: 'linear-gradient(90deg, rgb(var(--brand)), rgb(var(--cta)))',
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  );
}

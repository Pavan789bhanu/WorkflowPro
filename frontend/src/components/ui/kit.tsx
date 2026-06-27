/**
 * WorkflowPro UI kit — Aurora Glass design system primitives.
 * Built per design-system/workflowpro/MASTER.md (ui-ux-pro-max).
 */
import type { ReactNode, ButtonHTMLAttributes, InputHTMLAttributes, TextareaHTMLAttributes } from 'react';
import { useEffect } from 'react';
import { X, Loader2, CheckCircle2, XCircle, Clock } from 'lucide-react';

/* ── Surfaces ─────────────────────────────────────────────────────── */

export function GlassCard({
  children,
  className = '',
  hover = false,
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}) {
  return (
    <div className={`glass-card ${hover ? 'glass-hover' : ''} ${className}`}>
      {children}
    </div>
  );
}

export function PageHeader({
  icon,
  title,
  subtitle,
  actions,
}: {
  icon?: ReactNode;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 animate-fade-in-up">
      <div className="flex items-center gap-3.5">
        {icon && (
          <div
            className="w-12 h-12 rounded-2xl flex items-center justify-center text-white shadow-lg animate-float"
            style={{ background: 'linear-gradient(135deg, rgb(var(--brand)), rgb(var(--cta)))' }}
          >
            {icon}
          </div>
        )}
        <div>
          <h1 className="text-xl font-bold text-primary leading-tight">{title}</h1>
          {subtitle && <p className="text-sm text-secondary mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
    </div>
  );
}

/* ── Buttons ──────────────────────────────────────────────────────── */

type ButtonVariant = 'brand' | 'cta' | 'ghost' | 'danger';

export function Button({
  variant = 'brand',
  loading = false,
  children,
  className = '',
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; loading?: boolean }) {
  return (
    <button className={`btn-${variant} ${className}`} disabled={loading || rest.disabled} {...rest}>
      {loading && <Loader2 size={15} className="animate-spin" />}
      {children}
    </button>
  );
}

/* ── Status ───────────────────────────────────────────────────────── */

const STATUS_STYLES: Record<string, { bg: string; fg: string; label: string; spin?: boolean; live?: boolean }> = {
  SUCCESS: { bg: 'rgba(16,185,129,0.14)', fg: '#059669', label: 'Success' },
  COMPLETED: { bg: 'rgba(16,185,129,0.14)', fg: '#059669', label: 'Success' },
  RUNNING: { bg: 'rgba(59,130,246,0.14)', fg: '#2563eb', label: 'Running', spin: true, live: true },
  PENDING: { bg: 'rgba(245,158,11,0.14)', fg: '#d97706', label: 'Pending' },
  FAILED: { bg: 'rgba(239,68,68,0.14)', fg: '#dc2626', label: 'Failed' },
  STOPPED: { bg: 'rgba(148,163,184,0.18)', fg: '#64748b', label: 'Stopped' },
  CANCELLED: { bg: 'rgba(148,163,184,0.18)', fg: '#64748b', label: 'Cancelled' },
  active: { bg: 'rgba(16,185,129,0.14)', fg: '#059669', label: 'Active' },
  paused: { bg: 'rgba(245,158,11,0.14)', fg: '#d97706', label: 'Paused' },
  archived: { bg: 'rgba(148,163,184,0.18)', fg: '#64748b', label: 'Archived' },
};

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.PENDING;
  const Icon = status === 'RUNNING' ? Loader2
    : (status === 'SUCCESS' || status === 'COMPLETED' || status === 'active') ? CheckCircle2
    : (status === 'FAILED') ? XCircle
    : Clock;
  return (
    <span className="badge" style={{ backgroundColor: s.bg, color: s.fg }}>
      {s.live ? <span className="live-dot" /> : <Icon size={12} className={s.spin ? 'animate-spin' : ''} />}
      {s.label}
    </span>
  );
}

/* ── Stats ────────────────────────────────────────────────────────── */

export function Stat({
  label,
  value,
  icon,
  tone = 'brand',
  hint,
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  tone?: 'brand' | 'success' | 'danger' | 'warn' | 'neutral';
  hint?: string;
}) {
  const tones: Record<string, string> = {
    brand: 'rgba(var(--brand), 0.14)',
    success: 'rgba(16,185,129,0.14)',
    danger: 'rgba(239,68,68,0.12)',
    warn: 'rgba(245,158,11,0.14)',
    neutral: 'rgba(148,163,184,0.16)',
  };
  const fg: Record<string, string> = {
    brand: 'rgb(var(--brand))',
    success: '#059669',
    danger: '#dc2626',
    warn: '#d97706',
    neutral: 'rgb(var(--text-secondary))',
  };
  return (
    <GlassCard hover className="p-5 animate-fade-in-up">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-tertiary mb-2">{label}</p>
          <p className="stat-number text-3xl font-bold text-primary leading-none">{value}</p>
          {hint && <p className="text-xs text-tertiary mt-2">{hint}</p>}
        </div>
        {icon && (
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: tones[tone], color: fg[tone] }}>
            {icon}
          </div>
        )}
      </div>
    </GlassCard>
  );
}

/* ── Empty state ──────────────────────────────────────────────────── */

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="text-center py-14 animate-fade-in">
      <div className="w-16 h-16 rounded-2xl glass flex items-center justify-center mx-auto mb-4 text-tertiary">
        {icon}
      </div>
      <h3 className="font-semibold text-primary mb-1">{title}</h3>
      {description && <p className="text-sm text-secondary max-w-xs mx-auto mb-5">{description}</p>}
      {action}
    </div>
  );
}

/* ── Modal ────────────────────────────────────────────────────────── */

export function Modal({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center p-4 animate-fade-in"
      style={{ background: 'rgba(20, 16, 60, 0.45)', backdropFilter: 'blur(6px)' }}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        className={`glass-card w-full ${wide ? 'max-w-2xl' : 'max-w-md'} max-h-[88vh] overflow-y-auto animate-scale-in`}
        style={{ background: 'rgba(var(--bg-secondary), 0.92)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 pt-5 pb-3">
          <h2 className="text-lg font-bold text-primary">{title}</h2>
          <button onClick={onClose} className="icon-btn" aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="px-6 pb-6">{children}</div>
      </div>
    </div>
  );
}

/* ── Form primitives ──────────────────────────────────────────────── */

export function Field({
  label,
  children,
  optional = false,
}: {
  label: string;
  children: ReactNode;
  optional?: boolean;
}) {
  return (
    <div>
      <label className="label">
        {label}
        {optional && <span className="normal-case font-normal text-tertiary"> · optional</span>}
      </label>
      {children}
    </div>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`field ${props.className ?? ''}`} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`field resize-none ${props.className ?? ''}`} />;
}

/* ── Misc ─────────────────────────────────────────────────────────── */

export function timeAgo(date?: string | null): string {
  if (!date) return '—';
  const s = Math.floor((Date.now() - new Date(date).getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 604800) return `${Math.floor(s / 86400)}d ago`;
  return new Date(date).toLocaleDateString();
}

export function formatDuration(seconds?: number | null): string {
  if (!seconds && seconds !== 0) return '—';
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

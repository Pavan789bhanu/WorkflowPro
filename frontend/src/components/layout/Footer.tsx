/**
 * Footer — professional glass footer used on app pages and the landing page.
 */
import { Link } from 'react-router-dom';
import { Sparkles, Github, BookOpen, Heart } from 'lucide-react';

const PRODUCT_LINKS = [
  { label: 'Playground', to: '/playground' },
  { label: 'Workflows', to: '/workflows' },
  { label: 'Executions', to: '/executions' },
  { label: 'Analytics', to: '/analytics' },
];

const ACCOUNT_LINKS = [
  { label: 'Sign in', to: '/login' },
  { label: 'Profile', to: '/profile' },
  { label: 'Settings', to: '/settings' },
];

export default function Footer({ compact = false }: { compact?: boolean }) {
  const year = new Date().getFullYear();

  if (compact) {
    return (
      <footer className="glass-card px-5 py-3.5 mt-8 mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-tertiary animate-fade-in">
        <span className="flex items-center gap-1.5 font-semibold text-secondary">
          <Sparkles size={13} className="text-brand" /> WorkflowPro
        </span>
        <span className="hidden sm:inline">·</span>
        <span>© {year}</span>
        <span className="hidden sm:inline">·</span>
        <span className="flex items-center gap-1.5">
          <span className="live-dot" style={{ width: 7, height: 7 }} /> agent online
        </span>
        <span className="ml-auto flex items-center gap-1">
          built with <Heart size={11} className="text-rose-500" /> and the ui-ux-pro-max skill
        </span>
      </footer>
    );
  }

  return (
    <footer className="max-w-6xl mx-auto px-5 pb-8 pt-4 w-full">
      <div className="glass-card p-8">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
          <div className="col-span-2 md:col-span-1">
            <div className="flex items-center gap-2.5 mb-3">
              <div
                className="w-9 h-9 rounded-xl flex items-center justify-center text-white shadow"
                style={{ background: 'linear-gradient(135deg, rgb(var(--brand)), rgb(var(--cta)))' }}
              >
                <Sparkles size={17} />
              </div>
              <span className="font-display font-bold text-primary">WorkflowPro</span>
            </div>
            <p className="text-xs text-secondary leading-relaxed max-w-[220px]">
              Agentic browser automation — describe the task in plain English, get the result.
            </p>
          </div>

          <div>
            <p className="label mb-3">Product</p>
            <ul className="space-y-2">
              {PRODUCT_LINKS.map((l) => (
                <li key={l.to}>
                  <Link to={l.to} className="text-sm text-secondary hover:text-brand transition-colors">{l.label}</Link>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <p className="label mb-3">Account</p>
            <ul className="space-y-2">
              {ACCOUNT_LINKS.map((l) => (
                <li key={l.to}>
                  <Link to={l.to} className="text-sm text-secondary hover:text-brand transition-colors">{l.label}</Link>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <p className="label mb-3">Resources</p>
            <ul className="space-y-2">
              <li>
                <a href="https://github.com/pavan-kumar-malasani/ui_capture_system" target="_blank" rel="noreferrer"
                  className="text-sm text-secondary hover:text-brand transition-colors inline-flex items-center gap-1.5">
                  <Github size={13} /> GitHub
                </a>
              </li>
              <li>
                <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer"
                  className="text-sm text-secondary hover:text-brand transition-colors inline-flex items-center gap-1.5">
                  <BookOpen size={13} /> API docs
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div
          className="flex flex-wrap items-center gap-3 mt-8 pt-5 text-xs text-tertiary"
          style={{ borderTop: '1px solid rgba(var(--border-color), 0.7)' }}
        >
          <span>© {year} WorkflowPro · MIT License</span>
          <span className="ml-auto flex items-center gap-1.5">
            <span className="live-dot" style={{ width: 7, height: 7 }} /> all systems operational
          </span>
        </div>
      </div>
    </footer>
  );
}

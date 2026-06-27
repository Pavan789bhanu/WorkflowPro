/**
 * Dock — floating glass navigation rail (Aurora Glass design system).
 * Replaces the old full-height solid sidebar.
 */
import { Home, Workflow, Activity, TrendingUp, Settings, FlaskConical, LogOut, Sparkles } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';

const NAV_ITEMS = [
  { icon: Home, label: 'Home', path: '/dashboard' },
  { icon: FlaskConical, label: 'Playground', path: '/playground' },
  { icon: Workflow, label: 'Workflows', path: '/workflows' },
  { icon: Activity, label: 'Executions', path: '/executions' },
  { icon: TrendingUp, label: 'Analytics', path: '/analytics' },
  { icon: Settings, label: 'Settings', path: '/settings' },
];

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { logout, user } = useAuth();

  return (
    <aside
      className="glass-card fixed left-4 top-4 bottom-4 z-40 w-[72px] xl:w-56 flex flex-col py-4 transition-all duration-300"
      role="navigation"
      aria-label="Main navigation"
    >
      {/* Brand */}
      <Link to="/dashboard" className="flex items-center gap-3 px-4 mb-6 group" aria-label="WorkflowPro home">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center text-white shadow-lg shrink-0 group-hover:scale-105 transition-transform"
          style={{ background: 'linear-gradient(135deg, rgb(var(--brand)), rgb(var(--cta)))' }}
        >
          <Sparkles size={20} />
        </div>
        <div className="hidden xl:block min-w-0">
          <p className="font-display font-bold text-sm text-primary leading-none">WorkflowPro</p>
          <p className="text-[10px] text-tertiary mt-1">Aurora</p>
        </div>
      </Link>

      {/* Nav */}
      <nav className="flex-1 px-2.5 space-y-1.5" aria-label="Main menu">
        {NAV_ITEMS.map(({ icon: Icon, label, path }) => {
          const active = location.pathname === path;
          return (
            <Link
              key={path}
              to={path}
              title={label}
              className="relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all group"
              style={{
                background: active ? 'rgba(var(--brand), 0.12)' : 'transparent',
                color: active ? 'rgb(var(--brand))' : 'rgb(var(--text-secondary))',
              }}
            >
              {active && (
                <span
                  className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 rounded-full"
                  style={{ background: 'rgb(var(--brand))' }}
                />
              )}
              <Icon size={19} className="shrink-0 mx-auto xl:mx-0 group-hover:scale-110 transition-transform" />
              <span className="hidden xl:inline truncate">{label}</span>
            </Link>
          );
        })}
      </nav>

      {/* User chip */}
      <div className="px-2.5 pt-3 mt-2 space-y-1.5" style={{ borderTop: '1px solid rgba(var(--border-color), 0.7)' }}>
        <Link
          to="/profile"
          title="Profile"
          className="flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors hover:bg-[rgba(var(--brand),0.08)]"
        >
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0 mx-auto xl:mx-0"
            style={{ background: 'linear-gradient(135deg, rgb(var(--brand)), rgb(var(--brand-hover)))' }}
          >
            {(user?.username?.[0] || 'U').toUpperCase()}
          </div>
          <div className="hidden xl:block min-w-0">
            <p className="text-xs font-semibold text-primary truncate">{user?.username || 'Account'}</p>
            <p className="text-[10px] text-tertiary truncate">{user?.email || ''}</p>
          </div>
        </Link>
        <button
          onClick={() => { logout(); navigate('/'); }}
          title="Sign out"
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-secondary hover:text-red-500 hover:bg-red-500/10 transition-colors"
        >
          <LogOut size={18} className="shrink-0 mx-auto xl:mx-0" />
          <span className="hidden xl:inline">Sign out</span>
        </button>
      </div>
    </aside>
  );
}

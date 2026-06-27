/**
 * Top bar — slim glass strip with page context, live status, quick actions.
 */
import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Bell, Plus, Sun, Moon, Zap } from 'lucide-react';
import { useNotifications } from '../../contexts/NotificationContext';
import { useTheme } from '../../contexts/ThemeContext';
import NotificationPanel from '../NotificationPanel';

const PAGE_TITLES: Record<string, string> = {
  '/dashboard': 'Home',
  '/playground': 'Playground',
  '/workflows': 'Workflows',
  '/executions': 'Executions',
  '/analytics': 'Analytics',
  '/settings': 'Settings',
  '/profile': 'Profile',
};

export default function Header() {
  const location = useLocation();
  const navigate = useNavigate();
  const { unreadCount } = useNotifications();
  const { theme, setTheme } = useTheme();
  const [showNotifications, setShowNotifications] = useState(false);

  const title = PAGE_TITLES[location.pathname] ?? 'WorkflowPro';
  const isDark = theme !== 'light';

  return (
    <header className="sticky top-4 z-30 mb-6">
      <div className="glass-card flex items-center gap-3 px-5 py-3">
        <div className="mr-auto flex items-center gap-3">
          <h1 className="font-display font-bold text-base text-primary">{title}</h1>
          <span className="hidden sm:flex items-center gap-1.5 text-[11px] text-tertiary">
            <span className="live-dot" aria-hidden="true" />
            live
          </span>
        </div>

        <button
          onClick={() => {
            navigate('/workflows');
            window.dispatchEvent(new CustomEvent('create-workflow'));
          }}
          className="btn-brand !py-2 hidden sm:inline-flex"
        >
          <Plus size={16} />
          New Workflow
        </button>
        <button
          onClick={() => navigate('/playground')}
          className="btn-ghost !py-2 hidden md:inline-flex"
          title="Open Playground"
        >
          <Zap size={16} />
          Run a task
        </button>

        <button
          onClick={() => setTheme(isDark ? 'light' : 'midnight')}
          className="icon-btn"
          title={isDark ? 'Switch to light (aurora)' : 'Switch to midnight'}
          aria-label="Toggle theme"
        >
          {isDark ? <Sun size={18} /> : <Moon size={18} />}
        </button>

        <button
          onClick={() => setShowNotifications((v) => !v)}
          className="icon-btn relative"
          title="Notifications"
          aria-label={`Notifications${unreadCount ? ` (${unreadCount} unread)` : ''}`}
        >
          <Bell size={18} />
          {unreadCount > 0 && (
            <span
              className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full text-[10px] font-bold text-white flex items-center justify-center"
              style={{ background: 'rgb(var(--danger))' }}
            >
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </button>
      </div>

      {showNotifications && <NotificationPanel onClose={() => setShowNotifications(false)} />}
    </header>
  );
}

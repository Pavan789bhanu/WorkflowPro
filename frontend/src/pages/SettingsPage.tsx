/**
 * Settings — appearance & preferences (Aurora Glass).
 * All controls wired to ThemeContext, which now actually applies
 * the choices to the DOM.
 */
import { Settings as SettingsIcon, Sun, Moon, MoonStar, Sparkles, Type, Gauge } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';
import { GlassCard, PageHeader } from '../components/ui/kit';

const THEMES = [
  { id: 'light', label: 'Aurora Light', icon: Sun, desc: 'Lavender glass, bright & airy' },
  { id: 'dark', label: 'Dark', icon: Moon, desc: 'Soft dark surfaces' },
  { id: 'midnight', label: 'Midnight', icon: MoonStar, desc: 'Deep OLED black' },
] as const;

const ACCENTS = [
  { id: 'indigo', color: '#6366F1' },
  { id: 'purple', color: '#A855F7' },
  { id: 'blue', color: '#3B82F6' },
  { id: 'emerald', color: '#10B981' },
  { id: 'rose', color: '#F43F5E' },
  { id: 'amber', color: '#F59E0B' },
] as const;

const FONT_SIZES = [
  { id: 'small', label: 'Small' },
  { id: 'medium', label: 'Medium' },
  { id: 'large', label: 'Large' },
] as const;

export default function SettingsPage() {
  const {
    theme, setTheme,
    accentColor, setAccentColor,
    fontSize, setFontSize,
    effectsEnabled, setEffectsEnabled,
    reducedMotion, setReducedMotion,
    compactMode, setCompactMode,
  } = useTheme();

  return (
    <div className="max-w-4xl mx-auto">
      <PageHeader
        icon={<SettingsIcon size={22} />}
        title="Settings"
        subtitle="Make WorkflowPro feel like yours"
      />

      {/* Theme */}
      <GlassCard className="p-6 mb-5">
        <h3 className="font-display font-bold text-primary mb-4 flex items-center gap-2">
          <Sparkles size={16} className="text-brand" /> Theme
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {THEMES.map(({ id, label, icon: Icon, desc }) => (
            <button
              key={id}
              onClick={() => setTheme(id)}
              className="glass rounded-2xl p-4 text-left transition-all"
              style={{
                borderColor: theme === id ? 'rgb(var(--brand))' : undefined,
                boxShadow: theme === id ? '0 0 0 2px rgba(var(--brand), 0.35)' : undefined,
              }}
              aria-pressed={theme === id}
            >
              <Icon size={18} className={theme === id ? 'text-brand' : 'text-tertiary'} />
              <p className="font-semibold text-sm text-primary mt-2">{label}</p>
              <p className="text-xs text-tertiary mt-0.5">{desc}</p>
            </button>
          ))}
        </div>
      </GlassCard>

      {/* Accent */}
      <GlassCard className="p-6 mb-5">
        <h3 className="font-display font-bold text-primary mb-4">Accent color</h3>
        <div className="flex flex-wrap gap-3">
          {ACCENTS.map(({ id, color }) => (
            <button
              key={id}
              onClick={() => setAccentColor(id)}
              className="w-10 h-10 rounded-full transition-transform hover:scale-110 capitalize"
              style={{
                background: color,
                boxShadow: accentColor === id ? `0 0 0 3px rgb(var(--bg-primary)), 0 0 0 5px ${color}` : 'none',
              }}
              title={id}
              aria-pressed={accentColor === id}
              aria-label={`Accent ${id}`}
            />
          ))}
        </div>
      </GlassCard>

      {/* Typography & comfort */}
      <GlassCard className="p-6 mb-5">
        <h3 className="font-display font-bold text-primary mb-4 flex items-center gap-2">
          <Type size={16} className="text-brand" /> Text size
        </h3>
        <div className="glass rounded-xl p-1 inline-flex gap-0.5">
          {FONT_SIZES.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setFontSize(id)}
              className="px-4 py-2 rounded-lg text-sm font-semibold transition-colors"
              style={{
                background: fontSize === id ? 'rgba(var(--brand), 0.15)' : 'transparent',
                color: fontSize === id ? 'rgb(var(--brand))' : 'rgb(var(--text-tertiary))',
              }}
              aria-pressed={fontSize === id}
            >
              {label}
            </button>
          ))}
        </div>
      </GlassCard>

      {/* Motion & effects */}
      <GlassCard className="p-6">
        <h3 className="font-display font-bold text-primary mb-4 flex items-center gap-2">
          <Gauge size={16} className="text-brand" /> Motion & effects
        </h3>
        <div className="space-y-1">
          <ToggleRow
            label="Aurora effects"
            description="Animated gradient backdrop and glass shimmer"
            checked={effectsEnabled}
            onChange={setEffectsEnabled}
          />
          <ToggleRow
            label="Reduce motion"
            description="Minimize animations across the app"
            checked={reducedMotion}
            onChange={setReducedMotion}
          />
          <ToggleRow
            label="Compact mode"
            description="Tighter spacing for dense screens"
            checked={compactMode}
            onChange={setCompactMode}
          />
        </div>
      </GlassCard>
    </div>
  );
}

function ToggleRow({
  label, description, checked, onChange,
}: {
  label: string; description: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className="w-full flex items-center justify-between gap-4 p-3 rounded-xl hover:bg-[rgba(var(--brand),0.05)] transition-colors text-left"
      role="switch"
      aria-checked={checked}
    >
      <div>
        <p className="text-sm font-semibold text-primary">{label}</p>
        <p className="text-xs text-tertiary">{description}</p>
      </div>
      <span
        className="relative w-11 h-6 rounded-full transition-colors shrink-0"
        style={{ background: checked ? 'rgb(var(--cta))' : 'rgba(var(--border-color), 1)' }}
      >
        <span
          className="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-all"
          style={{ left: checked ? '22px' : '2px' }}
        />
      </span>
    </button>
  );
}

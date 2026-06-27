import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';

type Theme = 'light' | 'dark' | 'midnight';
type AccentColor = 'indigo' | 'purple' | 'blue' | 'emerald' | 'rose' | 'amber';
type FontSize = 'small' | 'medium' | 'large';

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  effectsEnabled: boolean;
  setEffectsEnabled: (enabled: boolean) => void;
  accentColor: AccentColor;
  setAccentColor: (color: AccentColor) => void;
  fontSize: FontSize;
  setFontSize: (size: FontSize) => void;
  reducedMotion: boolean;
  setReducedMotion: (enabled: boolean) => void;
  compactMode: boolean;
  setCompactMode: (enabled: boolean) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

function usePersisted<T extends string | boolean>(key: string, initial: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => {
    const saved = localStorage.getItem(key);
    if (saved === null) return initial;
    if (typeof initial === 'boolean') return (saved === 'true') as T;
    return saved as T;
  });
  const set = (v: T) => {
    setValue(v);
    localStorage.setItem(key, String(v));
  };
  return [value, set];
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Aurora light is the new default look; dark/midnight remain available.
  const [theme, setTheme] = usePersisted<Theme>('theme', 'light');
  const [effectsEnabled, setEffectsEnabled] = usePersisted<boolean>('effectsEnabled', true);
  const [accentColor, setAccentColor] = usePersisted<AccentColor>('accentColor', 'indigo');
  const [fontSize, setFontSize] = usePersisted<FontSize>('fontSize', 'medium');
  const [reducedMotion, setReducedMotion] = usePersisted<boolean>('reducedMotion', false);
  const [compactMode, setCompactMode] = usePersisted<boolean>('compactMode', false);

  // Actually apply the choices to the DOM (previously the settings were
  // stored but never wired to anything — themes silently did nothing).
  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute('data-theme', theme);
    root.setAttribute('data-accent', accentColor);
    root.setAttribute('data-font-size', fontSize);
    root.toggleAttribute('data-no-effects', !effectsEnabled);
    root.toggleAttribute('data-reduced-motion', reducedMotion);
    root.toggleAttribute('data-compact', compactMode);
  }, [theme, accentColor, fontSize, effectsEnabled, reducedMotion, compactMode]);

  return (
    <ThemeContext.Provider
      value={{
        theme, setTheme,
        effectsEnabled, setEffectsEnabled,
        accentColor, setAccentColor,
        fontSize, setFontSize,
        reducedMotion, setReducedMotion,
        compactMode, setCompactMode,
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return context;
}

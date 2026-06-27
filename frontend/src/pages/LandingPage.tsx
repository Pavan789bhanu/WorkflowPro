/**
 * Landing — public marketing page (Aurora Glass).
 * Compact hero + how-it-works + CTA. Replaces the old 700-line page.
 */
import { Link } from 'react-router-dom';
import {
  Sparkles, ArrowRight, Eye, Brain, MousePointerClick, FileText,
  Zap, ShieldCheck, Repeat,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { GlassCard } from '../components/ui/kit';
import Footer from '../components/layout/Footer';

const LOOP = [
  { icon: Eye, title: 'Observe', desc: 'Screenshot + live DOM scan of the real page' },
  { icon: Brain, title: 'Decide', desc: 'A vision LLM picks the single best next action' },
  { icon: MousePointerClick, title: 'Act', desc: 'Clicks, types and navigates like a human' },
  { icon: FileText, title: 'Report', desc: 'Delivers the actual answer, not just step logs' },
];

const FEATURES = [
  { icon: Zap, title: 'Plain English in, results out', desc: '“Find this week’s RAG articles on Medium and summarize each” — that’s the whole program.' },
  { icon: Repeat, title: 'Save & re-run', desc: 'Turn any task into a workflow. Watch every run live with streaming screenshots.' },
  { icon: ShieldCheck, title: 'Resilient by design', desc: 'Cookie banners, sign-up walls and anti-bot pages are handled — with cost guards on every run.' },
];

export default function LandingPage() {
  const { isAuthenticated, logout } = useAuth();
  const appHref = isAuthenticated ? '/dashboard' : '/login';

  return (
    <div className="min-h-screen">
      <div className="aurora-bg" aria-hidden="true" />

      {/* Nav */}
      <nav className="max-w-6xl mx-auto flex items-center gap-3 px-5 py-5">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center text-white shadow-lg"
          style={{ background: 'linear-gradient(135deg, rgb(var(--brand)), rgb(var(--cta)))' }}
        >
          <Sparkles size={20} />
        </div>
        <span className="font-display text-lg font-bold text-primary mr-auto">WorkflowPro</span>
        {isAuthenticated ? (
          <>
            <button onClick={() => { logout(); }} className="btn-ghost !py-2 hidden sm:inline-flex">
              Sign out
            </button>
            <Link to="/dashboard" className="btn-brand !py-2">
              Open Dashboard <ArrowRight size={15} />
            </Link>
          </>
        ) : (
          <>
            <Link to="/login" className="btn-ghost !py-2">
              Sign in
            </Link>
            <Link to="/login" className="btn-brand !py-2">
              Get started <ArrowRight size={15} />
            </Link>
          </>
        )}
      </nav>

      {/* Hero */}
      <header className="max-w-4xl mx-auto text-center px-5 pt-16 pb-14">
        <p
          className="inline-flex items-center gap-2 badge mb-6"
          style={{ background: 'rgba(var(--brand), 0.12)', color: 'rgb(var(--brand))' }}
        >
          <span className="live-dot" /> Agentic browser automation
        </p>
        <h1 className="font-display text-4xl sm:text-5xl font-bold text-primary leading-tight mb-5">
          Describe the task.<br />
          <span className="gradient-text">Watch it get done.</span>
        </h1>
        <p className="text-secondary max-w-xl mx-auto mb-9">
          WorkflowPro drives a real browser with a vision AI agent — it reads pages like a human,
          adapts to any site, and hands you a result report with the answers you asked for.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Link to={appHref} className="btn-cta !px-7 !py-3.5 !text-base">
            <Zap size={18} /> Run your first task
          </Link>
          <Link to={appHref} className="btn-ghost !px-7 !py-3.5 !text-base">
            See the dashboard
          </Link>
        </div>
      </header>

      {/* Agent loop */}
      <section className="max-w-5xl mx-auto px-5 pb-14">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 stagger">
          {LOOP.map(({ icon: Icon, title, desc }, i) => (
            <GlassCard key={title} hover className="p-5 animate-fade-in-up" >
              <div className="flex items-center gap-2 mb-2" style={{ animationDelay: `${i * 80}ms` }}>
                <span className="stat-number text-xs text-tertiary">0{i + 1}</span>
                <Icon size={18} className="text-brand" />
              </div>
              <p className="font-display font-bold text-sm text-primary mb-1">{title}</p>
              <p className="text-xs text-secondary leading-relaxed">{desc}</p>
            </GlassCard>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="max-w-5xl mx-auto px-5 pb-16 grid grid-cols-1 md:grid-cols-3 gap-4 stagger">
        {FEATURES.map(({ icon: Icon, title, desc }) => (
          <GlassCard key={title} hover className="p-6">
            <div
              className="w-11 h-11 rounded-xl flex items-center justify-center text-white mb-4 shadow-lg"
              style={{ background: 'linear-gradient(135deg, rgb(var(--brand)), rgb(var(--cta)))' }}
            >
              <Icon size={20} />
            </div>
            <h3 className="font-display font-bold text-primary mb-1.5">{title}</h3>
            <p className="text-sm text-secondary leading-relaxed">{desc}</p>
          </GlassCard>
        ))}
      </section>

      {/* CTA */}
      <section className="max-w-3xl mx-auto px-5 pb-20">
        <GlassCard className="p-10 text-center relative overflow-hidden">
          <div
            className="absolute -right-16 -top-20 w-64 h-64 rounded-full opacity-25 blur-3xl pointer-events-none"
            style={{ background: 'linear-gradient(135deg, rgb(var(--brand)), rgb(var(--cta)))' }}
          />
          <h2 className="font-display text-2xl font-bold text-primary mb-3">
            Your browser has a copilot now
          </h2>
          <p className="text-sm text-secondary mb-7">
            Demo login: admin@example.com / admin123
          </p>
          <Link to={appHref} className="btn-brand !px-8 !py-3.5 !text-base">
            Get started <ArrowRight size={17} />
          </Link>
        </GlassCard>
      </section>

      <Footer />
    </div>
  );
}

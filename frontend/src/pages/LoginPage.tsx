/**
 * Login / Register — Aurora Glass.
 * Same auth flow as before (demo credentials prefill preserved).
 */
import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Sparkles, Loader2, ArrowLeft } from 'lucide-react';
import { GlassCard, Field, TextInput } from '../components/ui/kit';

const DEMO_EMAIL = 'admin@example.com';
const DEMO_PASSWORD = 'admin123';

export function LoginPage() {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const navigate = useNavigate();
  const { login, register } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const loginEmail = email.trim() || DEMO_EMAIL;
    const loginPassword = password || DEMO_PASSWORD;

    if (!isLogin && (!email.trim() || !password)) {
      setError('Please enter both email and password to create an account.');
      return;
    }

    setIsLoading(true);
    try {
      if (isLogin) {
        await login(loginEmail, loginPassword);
      } else {
        await register(email.trim(), password);
      }
      navigate('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4 py-10">
      <div className="aurora-bg" aria-hidden="true" />

      <Link to="/" className="flex items-center gap-1.5 text-sm text-secondary hover:text-brand mb-8 self-start sm:self-auto">
        <ArrowLeft size={15} /> Back to home
      </Link>

      <div className="flex items-center gap-3 mb-8">
        <div
          className="w-12 h-12 rounded-2xl flex items-center justify-center text-white shadow-lg animate-float"
          style={{ background: 'linear-gradient(135deg, rgb(var(--brand)), rgb(var(--cta)))' }}
        >
          <Sparkles size={24} />
        </div>
        <span className="font-display text-2xl font-bold text-primary">WorkflowPro</span>
      </div>

      <GlassCard className="w-full max-w-sm p-7 animate-scale-in">
        <h1 className="font-display text-xl font-bold text-primary mb-1">
          {isLogin ? 'Welcome back' : 'Create account'}
        </h1>
        <p className="text-sm text-secondary mb-6">
          {isLogin
            ? 'Leave blank to use the demo account.'
            : 'Set up a new WorkflowPro account.'}
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Email">
            <TextInput
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={isLogin ? DEMO_EMAIL : 'you@company.com'}
              autoComplete="email"
            />
          </Field>
          <Field label="Password">
            <TextInput
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={isLogin ? '••••••••  (demo)' : 'Choose a strong password'}
              autoComplete={isLogin ? 'current-password' : 'new-password'}
            />
          </Field>

          {error && (
            <p className="text-xs font-medium px-3 py-2.5 rounded-xl"
              style={{ color: 'rgb(var(--danger))', background: 'rgba(239,68,68,0.10)' }}>
              {error}
            </p>
          )}

          <button type="submit" disabled={isLoading} className="btn-brand w-full !py-3">
            {isLoading && <Loader2 size={16} className="animate-spin" />}
            {isLogin ? 'Sign in' : 'Create account'}
          </button>
        </form>

        <p className="text-center text-sm text-secondary mt-5">
          {isLogin ? "Don't have an account?" : 'Already registered?'}{' '}
          <button onClick={() => { setIsLogin(!isLogin); setError(''); }} className="font-semibold text-brand">
            {isLogin ? 'Sign up' : 'Sign in'}
          </button>
        </p>
      </GlassCard>
    </div>
  );
}

export default LoginPage;

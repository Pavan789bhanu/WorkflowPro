import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * App-wide error boundary. Catches render-time exceptions so a single broken
 * component can't blank the whole screen — instead the user sees a friendly
 * recovery card. Prevents the classic "white screen of death" during a demo.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // In production this is where you'd forward to Sentry / a logging service.
    if (import.meta.env.DEV) {
      console.error('Unhandled UI error:', error, info);
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
        <div className="max-w-md">
          <h1 className="mb-2 text-xl font-bold text-primary">Something went wrong</h1>
          <p className="mb-6 text-sm text-secondary">
            An unexpected error occurred while rendering this page. You can try again, or
            reload the app.
          </p>
          <div className="flex justify-center gap-3">
            <button
              onClick={this.handleReset}
              className="rounded-lg px-4 py-2 text-sm font-medium text-white"
              style={{ background: 'linear-gradient(135deg, rgb(var(--brand)), rgb(var(--cta)))' }}
            >
              Try again
            </button>
            <button
              onClick={() => window.location.assign('/dashboard')}
              className="rounded-lg border border-[rgb(var(--border-color))] px-4 py-2 text-sm font-medium text-secondary"
            >
              Go to dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }
}

export default ErrorBoundary;

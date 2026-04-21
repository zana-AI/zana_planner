import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary] Uncaught error:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: '24px',
          fontFamily: 'system-ui, sans-serif',
          color: '#edf3ff',
          background: '#090f1f',
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
        }}>
          <h2 style={{ margin: 0, fontSize: '18px' }}>Something went wrong</h2>
          <pre style={{
            fontSize: '12px',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            background: '#0f1832',
            padding: '12px',
            borderRadius: '8px',
            color: '#ef4444',
          }}>
            {this.state.error?.message}
            {'\n\n'}
            {this.state.error?.stack}
          </pre>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '10px 20px',
              background: '#63a7f7',
              color: '#090f1f',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Reload
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

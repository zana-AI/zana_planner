import { useNavigate, useLocation } from 'react-router-dom';
import { useTelegramWebApp, getDevInitData } from '../hooks/useTelegramWebApp';

export function Navigation() {
  const navigate = useNavigate();
  const location = useLocation();
  const { initData } = useTelegramWebApp();
  const authData = initData || getDevInitData();
  const isAuthenticated = !!authData;

  // Don't show nav on home, admin, or unauthenticated pages
  if (location.pathname === '/' || location.pathname === '/admin' || !isAuthenticated) {
    return null;
  }

  const isActive = (path: string) => {
    if (path === '/weekly') {
      return location.pathname === '/weekly';
    }
    if (path === '/tasks') {
      return location.pathname === '/tasks';
    }
    if (path === '/community') {
      return location.pathname === '/community';
    }
    return false;
  };

  return (
    <nav className="tab-bar">
      <button
        onClick={() => navigate('/weekly')}
        className={`tab-button ${isActive('/weekly') ? 'active' : ''}`}
      >
        <span className="tab-icon">📊</span>
        <span className="tab-label">Promises</span>
      </button>
      <button
        onClick={() => navigate('/tasks')}
        className={`tab-button ${isActive('/tasks') ? 'active' : ''}`}
      >
        <span className="tab-icon">✅</span>
        <span className="tab-label">Tasks</span>
      </button>
      <button
        onClick={() => navigate('/community')}
        className={`tab-button ${isActive('/community') ? 'active' : ''}`}
      >
        <span className="tab-icon">👥</span>
        <span className="tab-label">Community</span>
      </button>
    </nav>
  );
}


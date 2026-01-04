import { useNavigate, useLocation } from 'react-router-dom';

export function Navigation() {
  const navigate = useNavigate();
  const location = useLocation();

  if (location.pathname === '/' || location.pathname === '/admin') {
    return null; // Don't show nav on home or admin pages
  }

  return (
    <nav style={{
      display: 'flex',
      justifyContent: 'space-around',
      padding: '0.75rem 1rem',
      backgroundColor: '#1a1a2e',
      borderBottom: '1px solid #2a2a3a',
      position: 'sticky',
      top: 0,
      zIndex: 100
    }}>
      <button
        onClick={() => navigate('/weekly')}
        style={{
          background: 'transparent',
          border: 'none',
          color: location.pathname === '/weekly' ? '#4CAF50' : '#ccc',
          cursor: 'pointer',
          fontSize: '0.9rem',
          padding: '0.5rem 1rem',
          fontWeight: location.pathname === '/weekly' ? '600' : '400'
        }}
      >
        📊 Weekly
      </button>
      <button
        onClick={() => navigate('/templates')}
        style={{
          background: 'transparent',
          border: 'none',
          color: location.pathname.startsWith('/templates') ? '#4CAF50' : '#ccc',
          cursor: 'pointer',
          fontSize: '0.9rem',
          padding: '0.5rem 1rem',
          fontWeight: location.pathname.startsWith('/templates') ? '600' : '400'
        }}
      >
        📋 Templates
      </button>
      <button
        onClick={() => navigate('/community')}
        style={{
          background: 'transparent',
          border: 'none',
          color: location.pathname === '/community' ? '#4CAF50' : '#ccc',
          cursor: 'pointer',
          fontSize: '0.9rem',
          padding: '0.5rem 1rem',
          fontWeight: location.pathname === '/community' ? '600' : '400'
        }}
      >
        👥 Community
      </button>
    </nav>
  );
}


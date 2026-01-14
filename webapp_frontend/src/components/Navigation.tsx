import { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTelegramWebApp, getDevInitData } from '../hooks/useTelegramWebApp';
import { apiClient } from '../api/client';
import type { UserInfo } from '../types';

export function Navigation() {
  const navigate = useNavigate();
  const location = useLocation();
  const { initData, user: telegramUser, webApp } = useTelegramWebApp();
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [botUsername, setBotUsername] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  
  const authData = initData || getDevInitData();
  const hasToken = !!localStorage.getItem('telegram_auth_token');
  const isAuthenticated = !!authData || hasToken;

  // Fetch user info for browser login users
  useEffect(() => {
    if (hasToken && !authData) {
      // Browser login - fetch user info
      apiClient.getUserInfo()
        .then(setUserInfo)
        .catch(() => {
          // If fetch fails, user might not be authenticated
          console.error('Failed to fetch user info');
        });
    }
  }, [hasToken, authData]);

  // Fetch bot username for Telegram links
  useEffect(() => {
    const fetchBotUsername = async () => {
      try {
        const response = await fetch('/api/auth/bot-username');
        if (response.ok) {
          const data = await response.json();
          if (data.bot_username) {
            setBotUsername(data.bot_username.trim());
          }
        }
      } catch (error) {
        console.error('Failed to fetch bot username:', error);
      }
    };
    
    if (isAuthenticated) {
      fetchBotUsername();
    }
  }, [isAuthenticated]);

  // Check admin status
  useEffect(() => {
    const checkAdmin = async () => {
      if (!isAuthenticated) {
        setIsAdmin(false);
        return;
      }
      
      try {
        // Set auth data for API client
        if (authData) {
          apiClient.setInitData(authData);
        }
        const result = await apiClient.checkAdminStatus();
        setIsAdmin(result.is_admin);
      } catch (error) {
        console.error('Failed to check admin status:', error);
        setIsAdmin(false);
      }
    };
    
    checkAdmin();
  }, [isAuthenticated, authData]);

  // Detect mobile mode
  useEffect(() => {
    const checkMobile = () => {
      // Check if Telegram WebApp is available and platform is mobile
      const isTelegramMobile = webApp?.platform && 
        (webApp.platform === 'ios' || webApp.platform === 'android');
      
      // Also check viewport width as fallback
      const isSmallViewport = window.innerWidth < 768;
      
      setIsMobile(isTelegramMobile || isSmallViewport);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, [webApp]);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowProfileMenu(false);
      }
    };

    if (showProfileMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showProfileMenu]);

  // Don't show nav on home, admin, or unauthenticated pages
  if (location.pathname === '/' || location.pathname === '/admin' || !isAuthenticated) {
    return null;
  }

  const handleLogout = () => {
    apiClient.clearAuth();
    // Dispatch custom event to update App.tsx state
    window.dispatchEvent(new Event('logout'));
    setShowProfileMenu(false);
    navigate('/', { replace: true });
  };

  // Get display name with proper fallback: first_name → username → user_id
  const displayName = userInfo?.first_name || telegramUser?.first_name || telegramUser?.username || userInfo?.user_id?.toString() || 'User';
  const displayInitial = (userInfo?.first_name || telegramUser?.first_name || telegramUser?.username || 'U').charAt(0).toUpperCase();

  const isActive = (path: string) => {
    if (path === '/dashboard') {
      return location.pathname === '/dashboard';
    }
    if (path === '/community') {
      return location.pathname === '/community';
    }
    if (path === '/templates') {
      return location.pathname.startsWith('/templates');
    }
    return false;
  };

  return (
    <>
      {/* Top Header with Profile Menu (Desktop) */}
      <header style={{
        position: 'sticky',
        top: 0,
        zIndex: 100,
        background: 'rgba(11, 16, 32, 0.95)',
        backdropFilter: 'blur(10px)',
        borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
        padding: '0.75rem 1rem',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button
            onClick={() => navigate('/dashboard')}
            style={{
              background: 'none',
              border: 'none',
              color: '#fff',
              fontSize: '1.2rem',
              fontWeight: 'bold',
              cursor: 'pointer',
              padding: '0.5rem'
            }}
          >
            Xaana
          </button>
        </div>

        {/* Profile Menu */}
        <div style={{ position: 'relative' }} ref={menuRef}>
          <button
            onClick={() => setShowProfileMenu(!showProfileMenu)}
            style={{
              background: 'rgba(255, 255, 255, 0.1)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              borderRadius: '50%',
              width: '40px',
              height: '40px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
              fontSize: '1rem',
              fontWeight: 'bold',
              cursor: 'pointer',
              transition: 'all 0.2s'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.2)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
            }}
          >
            {telegramUser?.photo_url ? (
              <img
                src={telegramUser.photo_url}
                alt={displayName}
                style={{
                  width: '100%',
                  height: '100%',
                  borderRadius: '50%',
                  objectFit: 'cover'
                }}
              />
            ) : (
              displayInitial
            )}
          </button>

          {/* Dropdown Menu */}
          {showProfileMenu && (
            <div style={{
              position: 'absolute',
              top: 'calc(100% + 0.5rem)',
              right: 0,
              background: 'rgba(11, 16, 32, 0.98)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              borderRadius: '8px',
              padding: '0.5rem',
              minWidth: '180px',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)'
            }}>
              <div style={{
                padding: '0.75rem 1rem',
                borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
                color: '#fff',
                fontSize: '0.9rem',
                fontWeight: '500'
              }}>
                {displayName}
              </div>
              <button
                onClick={() => {
                  navigate('/dashboard');
                  setShowProfileMenu(false);
                }}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'none',
                  border: 'none',
                  color: '#fff',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '0.9rem',
                  borderRadius: '4px',
                  transition: 'background 0.2s'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'none';
                }}
              >
                👤 Profile / Weekly
              </button>
              <a
                href={botUsername ? `https://t.me/${botUsername}` : 'https://t.me/zana_planner_bot'}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => setShowProfileMenu(false)}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'none',
                  border: 'none',
                  color: '#fff',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '0.9rem',
                  borderRadius: '4px',
                  transition: 'background 0.2s',
                  textDecoration: 'none',
                  display: 'block',
                  marginTop: '0.25rem'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'none';
                }}
              >
                🤖 Open Bot
              </a>
              <button
                onClick={() => {
                  navigate('/community');
                  setShowProfileMenu(false);
                }}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'none',
                  border: 'none',
                  color: '#fff',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '0.9rem',
                  borderRadius: '4px',
                  transition: 'background 0.2s',
                  marginTop: '0.25rem'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'none';
                }}
              >
                👥 Community
              </button>
              <button
                onClick={() => {
                  navigate('/templates');
                  setShowProfileMenu(false);
                }}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'none',
                  border: 'none',
                  color: '#fff',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '0.9rem',
                  borderRadius: '4px',
                  transition: 'background 0.2s',
                  marginTop: '0.25rem'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'none';
                }}
              >
                📋 Explore
              </button>
              {isAdmin && (
                <button
                  onClick={() => {
                    navigate('/admin');
                    setShowProfileMenu(false);
                  }}
                  style={{
                    width: '100%',
                    padding: '0.75rem 1rem',
                    background: 'none',
                    border: 'none',
                    color: '#5ba3f5',
                    textAlign: 'left',
                    cursor: 'pointer',
                    fontSize: '0.9rem',
                    borderRadius: '4px',
                    transition: 'background 0.2s',
                    marginTop: '0.25rem'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'rgba(91, 163, 245, 0.1)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'none';
                  }}
                >
                  🔐 Admin Panel
                </button>
              )}
              <div style={{
                marginTop: '0.5rem',
                paddingTop: '0.5rem',
                borderTop: '1px solid rgba(255, 255, 255, 0.1)'
              }}>
                <button
                  onClick={handleLogout}
                  style={{
                    width: '100%',
                    padding: '0.75rem 1rem',
                    background: 'none',
                    border: 'none',
                    color: '#ff6b6b',
                    textAlign: 'left',
                    cursor: 'pointer',
                    fontSize: '0.9rem',
                    borderRadius: '4px',
                    transition: 'background 0.2s'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'rgba(255, 107, 107, 0.1)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'none';
                  }}
                >
                  🚪 Logout
                </button>
              </div>
            </div>
          )}
        </div>
      </header>

      {/* Bottom Tab Bar (Desktop Navigation) - Hidden on Mobile */}
      {!isMobile && (
        <nav className="tab-bar">
          <button
            onClick={() => navigate('/dashboard')}
            className={`tab-button ${isActive('/dashboard') ? 'active' : ''}`}
          >
            <span className="tab-icon">🏠</span>
            <span className="tab-label">Weekly</span>
          </button>
          <button
            onClick={() => navigate('/community')}
            className={`tab-button ${isActive('/community') ? 'active' : ''}`}
          >
            <span className="tab-icon">👥</span>
            <span className="tab-label">Community</span>
          </button>
          <button
            onClick={() => navigate('/templates')}
            className={`tab-button ${isActive('/templates') ? 'active' : ''}`}
          >
            <span className="tab-icon">📋</span>
            <span className="tab-label">Explore</span>
          </button>
        </nav>
      )}

      {/* Telegram Keyboard (Mobile Navigation) */}
      {isMobile && (
        <div className="telegram-keyboard">
          <div className="telegram-keyboard-row">
            <button
              onClick={() => navigate('/dashboard')}
              className={`telegram-keyboard-button ${isActive('/dashboard') ? 'active' : ''}`}
            >
              Weekly
            </button>
            <button
              onClick={() => navigate('/community')}
              className={`telegram-keyboard-button ${isActive('/community') ? 'active' : ''}`}
            >
              Community
            </button>
            <button
              onClick={() => navigate('/templates')}
              className={`telegram-keyboard-button ${isActive('/templates') ? 'active' : ''}`}
            >
              Explore
            </button>
          </div>
        </div>
      )}
    </>
  );
}


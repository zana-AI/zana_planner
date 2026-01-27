import { useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../../api/client';
import type { UserInfo } from '../../types';

interface AdminHeaderProps {
  telegramUser: any;
  userInfo: UserInfo | null;
  botUsername: string | null;
  showProfileMenu: boolean;
  setShowProfileMenu: (show: boolean) => void;
}

export function AdminHeader({
  telegramUser,
  userInfo,
  botUsername,
  showProfileMenu,
  setShowProfileMenu,
}: AdminHeaderProps) {
  const navigate = useNavigate();
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowProfileMenu(false);
      }
    };

    if (showProfileMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showProfileMenu, setShowProfileMenu]);

  const handleLogout = () => {
    apiClient.clearAuth();
    window.dispatchEvent(new Event('logout'));
    setShowProfileMenu(false);
    navigate('/', { replace: true });
  };

  const displayName = userInfo?.first_name || telegramUser?.first_name || telegramUser?.username || userInfo?.user_id?.toString() || 'User';
  const displayInitial = (userInfo?.first_name || telegramUser?.first_name || telegramUser?.username || 'U').charAt(0).toUpperCase();

  return (
    <div className="admin-panel-header" style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: '1rem'
    }}>
      <h1 className="admin-panel-title" style={{ margin: 0 }}>Admin Panel</h1>
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
            transition: 'all 0.2s',
            padding: 0
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
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
            zIndex: 1000
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
              👤 Profile / Dashboard
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
              📋 Promise Marketplace
            </button>
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
    </div>
  );
}

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTelegramWebApp, getDevInitData } from '../hooks/useTelegramWebApp';
import { apiClient } from '../api/client';
import type { WeeklyReportData, UserInfo } from '../types';

export function DashboardPage() {
  const navigate = useNavigate();
  const { user, initData, isReady } = useTelegramWebApp();
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [reportData, setReportData] = useState<WeeklyReportData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isReady) return;

    const loadDashboardData = async () => {
      try {
        // Check for auth
        const authData = initData || getDevInitData();
        const token = localStorage.getItem('telegram_auth_token');
        
        if (!authData && !token) {
          navigate('/', { replace: true });
          return;
        }

        // Set auth for API client
        if (authData) {
          apiClient.setInitData(authData);
        }

        // Fetch user info and weekly report in parallel
        const [info, report] = await Promise.all([
          apiClient.getUserInfo().catch(() => null),
          apiClient.getWeeklyReport().catch(() => null)
        ]);

        setUserInfo(info);
        setReportData(report);
      } catch (error) {
        console.error('Failed to load dashboard data:', error);
      } finally {
        setLoading(false);
      }
    };

    loadDashboardData();
  }, [isReady, initData, navigate]);

  if (!isReady || loading) {
    return (
      <div className="app">
        <div className="loading">
          <div className="loading-spinner" />
          <div className="loading-text">Loading your workspace...</div>
        </div>
      </div>
    );
  }

  const displayName = user?.first_name || userInfo?.user_id?.toString() || 'User';
  const totalPromises = reportData ? Object.keys(reportData.promises).length : 0;
  const totalSpent = reportData?.total_spent || 0;
  const totalPromised = reportData?.total_promised || 0;

  return (
    <div className="app" style={{ padding: '1rem', maxWidth: '1200px', margin: '0 auto' }}>
      {/* Welcome Header */}
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '2rem', marginBottom: '0.5rem', color: '#fff' }}>
          Welcome back, {displayName}! 👋
        </h1>
        <p style={{ color: '#aaa', fontSize: '1rem' }}>
          Here's your workspace overview
        </p>
      </div>

      {/* Quick Stats */}
      {reportData && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '1rem',
          marginBottom: '2rem'
        }}>
          <div style={{
            background: 'rgba(11, 16, 32, 0.95)',
            padding: '1.5rem',
            borderRadius: '12px',
            border: '1px solid rgba(255, 255, 255, 0.1)'
          }}>
            <div style={{ color: '#aaa', fontSize: '0.9rem', marginBottom: '0.5rem' }}>Active Promises</div>
            <div style={{ color: '#fff', fontSize: '2rem', fontWeight: 'bold' }}>{totalPromises}</div>
          </div>
          <div style={{
            background: 'rgba(11, 16, 32, 0.95)',
            padding: '1.5rem',
            borderRadius: '12px',
            border: '1px solid rgba(255, 255, 255, 0.1)'
          }}>
            <div style={{ color: '#aaa', fontSize: '0.9rem', marginBottom: '0.5rem' }}>Hours This Week</div>
            <div style={{ color: '#fff', fontSize: '2rem', fontWeight: 'bold' }}>
              {totalSpent.toFixed(1)}h
            </div>
            <div style={{ color: '#666', fontSize: '0.8rem', marginTop: '0.25rem' }}>
              of {totalPromised.toFixed(1)}h promised
            </div>
          </div>
        </div>
      )}

      {/* Quick Actions / Navigation Cards */}
      <div style={{ marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1.5rem', marginBottom: '1rem', color: '#fff' }}>Navigate</h2>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
          gap: '1rem'
        }}>
          {/* Promises Card */}
          <div
            onClick={() => navigate('/weekly')}
            style={{
              background: 'rgba(11, 16, 32, 0.95)',
              padding: '1.5rem',
              borderRadius: '12px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              cursor: 'pointer',
              transition: 'all 0.2s'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.3)';
              e.currentTarget.style.transform = 'translateY(-2px)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.1)';
              e.currentTarget.style.transform = 'translateY(0)';
            }}
          >
            <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>📊</div>
            <h3 style={{ color: '#fff', fontSize: '1.2rem', marginBottom: '0.5rem' }}>Promises</h3>
            <p style={{ color: '#aaa', fontSize: '0.9rem' }}>
              View and manage your weekly promises and track your progress
            </p>
          </div>

          {/* Tasks Card */}
          <div
            onClick={() => navigate('/tasks')}
            style={{
              background: 'rgba(11, 16, 32, 0.95)',
              padding: '1.5rem',
              borderRadius: '12px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              cursor: 'pointer',
              transition: 'all 0.2s'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.3)';
              e.currentTarget.style.transform = 'translateY(-2px)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.1)';
              e.currentTarget.style.transform = 'translateY(0)';
            }}
          >
            <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>✅</div>
            <h3 style={{ color: '#fff', fontSize: '1.2rem', marginBottom: '0.5rem' }}>Tasks</h3>
            <p style={{ color: '#aaa', fontSize: '0.9rem' }}>
              Manage one-time tasks and track their completion
            </p>
          </div>

          {/* Community Card */}
          <div
            onClick={() => navigate('/community')}
            style={{
              background: 'rgba(11, 16, 32, 0.95)',
              padding: '1.5rem',
              borderRadius: '12px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              cursor: 'pointer',
              transition: 'all 0.2s'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.3)';
              e.currentTarget.style.transform = 'translateY(-2px)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.1)';
              e.currentTarget.style.transform = 'translateY(0)';
            }}
          >
            <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>👥</div>
            <h3 style={{ color: '#fff', fontSize: '1.2rem', marginBottom: '0.5rem' }}>Community</h3>
            <p style={{ color: '#aaa', fontSize: '0.9rem' }}>
              Connect with other users, follow progress, and stay motivated
            </p>
          </div>

          {/* Templates Card */}
          <div
            onClick={() => navigate('/templates')}
            style={{
              background: 'rgba(11, 16, 32, 0.95)',
              padding: '1.5rem',
              borderRadius: '12px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              cursor: 'pointer',
              transition: 'all 0.2s'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.3)';
              e.currentTarget.style.transform = 'translateY(-2px)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.1)';
              e.currentTarget.style.transform = 'translateY(0)';
            }}
          >
            <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>📋</div>
            <h3 style={{ color: '#fff', fontSize: '1.2rem', marginBottom: '0.5rem' }}>Templates</h3>
            <p style={{ color: '#aaa', fontSize: '0.9rem' }}>
              Browse and subscribe to promise templates to get started quickly
            </p>
          </div>
        </div>
      </div>

      {/* Recent Activity / Resume Section */}
      {reportData && totalPromises > 0 && (
        <div style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.5rem', marginBottom: '1rem', color: '#fff' }}>Resume Where You Left Off</h2>
          <div
            onClick={() => navigate('/weekly')}
            style={{
              background: 'rgba(11, 16, 32, 0.95)',
              padding: '1.5rem',
              borderRadius: '12px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              cursor: 'pointer',
              transition: 'all 0.2s'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.3)';
              e.currentTarget.style.transform = 'translateY(-2px)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.1)';
              e.currentTarget.style.transform = 'translateY(0)';
            }}
          >
            <p style={{ color: '#aaa', marginBottom: '0.5rem' }}>
              You have {totalPromises} active {totalPromises === 1 ? 'promise' : 'promises'} this week
            </p>
            <p style={{ color: '#fff', fontSize: '1.1rem', fontWeight: '500' }}>
              Continue tracking your progress →
            </p>
          </div>
        </div>
      )}
    </div>
  );
}


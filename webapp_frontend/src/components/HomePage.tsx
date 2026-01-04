import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { NewYearBanner } from './NewYearBanner';
import { TelegramLogin } from './TelegramLogin';
import { apiClient } from '../api/client';

// Helper to detect mobile device
function isMobileDevice(): boolean {
  if (typeof window === 'undefined') return false;
  
  // Check user agent
  const userAgent = navigator.userAgent || navigator.vendor || (window as any).opera;
  const mobileRegex = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini/i;
  
  // Check for touch support
  const hasTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  
  // Check viewport width (mobile typically < 768px)
  const isSmallViewport = window.innerWidth < 768;
  
  return mobileRegex.test(userAgent) || (hasTouch && isSmallViewport);
}

export function HomePage() {
  const navigate = useNavigate();
  const [showLogin, setShowLogin] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [botUsername, setBotUsername] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  
  // Check if user is already authenticated
  useEffect(() => {
    const token = localStorage.getItem('telegram_auth_token');
    const hasInitData = window.Telegram?.WebApp?.initData;
    
    if (token || hasInitData) {
      // User is authenticated, redirect to dashboard
      setIsAuthenticated(true);
      navigate('/dashboard', { replace: true });
    } else {
      // Show login option
      setIsAuthenticated(false);
      setShowLogin(true);
    }
  }, [navigate]);

  // Detect mobile on mount and resize
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(isMobileDevice());
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

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
    
    if (isMobile) {
      fetchBotUsername();
    }
  }, [isMobile]);

  const handleAuthSuccess = (token: string) => {
    apiClient.setAuthToken(token);
    navigate('/dashboard', { replace: true });
  };

  // Build Telegram deep links
  const telegramBotLink = botUsername ? `https://t.me/${botUsername}` : 'https://t.me/zana_planner_bot';
  const telegramWebAppLink = botUsername ? `https://t.me/${botUsername}?startapp=webapp` : 'https://t.me/zana_planner_bot?startapp=webapp';

  // Don't show hero section if authenticated
  if (isAuthenticated) {
    return null; // Will redirect to dashboard anyway
  }

  return (
    <div className="home-page">
      <NewYearBanner />
      
      {/* Mobile: Show Telegram CTAs instead of login widget */}
      {showLogin && isMobile && (
        <section className="home-login-section" style={{
          background: 'rgba(11, 16, 32, 0.95)',
          padding: '2rem',
          margin: '2rem auto',
          maxWidth: '500px',
          borderRadius: '12px',
          textAlign: 'center'
        }}>
          <h2 style={{ color: '#fff', marginBottom: '1rem' }}>Continue in Telegram</h2>
          <p style={{ color: '#aaa', marginBottom: '2rem' }}>
            Open Zana AI in Telegram to access your workspace and continue your productivity journey.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <a
              href={telegramWebAppLink}
              className="home-cta-button"
              style={{ 
                display: 'inline-block',
                textDecoration: 'none',
                padding: '0.75rem 1.5rem'
              }}
            >
              Open in Telegram
            </a>
            <a
              href={telegramBotLink}
              className="home-cta-button"
              style={{ 
                display: 'inline-block',
                textDecoration: 'none',
                padding: '0.75rem 1.5rem',
                backgroundColor: 'rgba(255, 255, 255, 0.1)',
                border: '1px solid rgba(255, 255, 255, 0.2)'
              }}
            >
              Open Bot Chat
            </a>
          </div>
        </section>
      )}
      
      {/* Desktop: Show Telegram Login Widget */}
      {showLogin && !isMobile && (
        <section className="home-login-section" style={{
          background: 'rgba(11, 16, 32, 0.95)',
          padding: '2rem',
          margin: '2rem auto',
          maxWidth: '500px',
          borderRadius: '12px',
          textAlign: 'center'
        }}>
          <TelegramLogin onAuthSuccess={handleAuthSuccess} />
        </section>
      )}
      
      {/* Hero Section - only show when not authenticated */}
      {!isAuthenticated && (
        <section className="home-hero">
          <div className="home-hero-content">
            <h1 className="home-hero-title">
              Zana AI
            </h1>
            <p className="home-hero-subtitle">
              Your AI-powered assistant for productivity and goal achievement
            </p>
            <p className="home-hero-description">
              Take control of your time, track your promises, and achieve your goals with intelligent insights and personalized recommendations.
            </p>
            <a 
              href={telegramBotLink}
              className="home-cta-button"
              target="_blank"
              rel="noopener noreferrer"
            >
              Start with Zana AI
            </a>
          </div>
        </section>
      )}

      {/* Three Key Features Section */}
      <section className="home-features">
        <h2 className="home-section-title">Why Choose Zana AI?</h2>
        <div className="home-features-grid">
          <div className="home-feature-card">
            <div className="home-feature-icon">🎯</div>
            <h3 className="home-feature-title">Goal Tracking</h3>
            <p className="home-feature-description">
              Track your promises (goals) and log time spent on them. Stay organized and focused on what matters most.
            </p>
          </div>
          
          <div className="home-feature-card">
            <div className="home-feature-icon">🧠</div>
            <h3 className="home-feature-title">AI Insights</h3>
            <p className="home-feature-description">
              Get personalized recommendations and daily focus areas powered by advanced AI. Know exactly what to work on today.
            </p>
          </div>
          
          <div className="home-feature-card">
            <div className="home-feature-icon">📊</div>
            <h3 className="home-feature-title">Progress Visualization</h3>
            <p className="home-feature-description">
              Visualize your progress with weekly reports and detailed analytics. See how you're advancing toward your goals.
            </p>
          </div>
        </div>
      </section>

      {/* Templates Section */}
      <section className="home-features">
        <h2 className="home-section-title">Promise Templates</h2>
        <div className="home-features-grid">
          <div className="home-feature-card">
            <div className="home-feature-icon">🎯</div>
            <h3 className="home-feature-title">Curated Templates</h3>
            <p className="home-feature-description">
              Start with proven promise templates. From fitness goals to language learning, choose templates designed for success.
            </p>
          </div>
          
          <div className="home-feature-card">
            <div className="home-feature-icon">🔓</div>
            <h3 className="home-feature-title">Progressive Unlocks</h3>
            <p className="home-feature-description">
              Unlock advanced templates as you complete easier ones. Build momentum with a structured progression system.
            </p>
          </div>
          
          <div className="home-feature-card">
            <div className="home-feature-icon">📉</div>
            <h3 className="home-feature-title">Distraction Budgets</h3>
            <p className="home-feature-description">
              Set limits on distractions like social media. Track and stay within your weekly time budgets.
            </p>
          </div>
        </div>
      </section>

      {/* Additional Features Section */}
      <section className="home-additional-features">
        <h2 className="home-section-title">More Features</h2>
        <div className="home-additional-grid">
          <div className="home-additional-item">
            <span className="home-additional-icon">🎤</span>
            <span className="home-additional-text">Voice & Image Input</span>
          </div>
          <div className="home-additional-item">
            <span className="home-additional-icon">🌍</span>
            <span className="home-additional-text">Multi-language Support</span>
          </div>
          <div className="home-additional-item">
            <span className="home-additional-icon">⏱️</span>
            <span className="home-additional-text">Pomodoro Sessions</span>
          </div>
          <div className="home-additional-item">
            <span className="home-additional-icon">🔔</span>
            <span className="home-additional-text">Smart Reminders</span>
          </div>
        </div>
      </section>

      {/* Community Preview Section */}
      <section className="home-community">
        <div className="home-community-card">
          <div className="home-community-icon">👥</div>
          <h3 className="home-community-title">Join the Community</h3>
          <p className="home-community-description">
            Connect with other goal-achievers, share your progress, and stay motivated together.
          </p>
          <Link 
            to="/community" 
            className="home-cta-button"
            style={{ marginTop: '1rem', display: 'inline-block' }}
          >
            View Community
          </Link>
        </div>
      </section>

      {/* Final CTA Section - only show when not authenticated */}
      {!isAuthenticated && (
        <section className="home-final-cta">
          <h2 className="home-cta-title">Ready to Achieve Your Goals?</h2>
          <p className="home-cta-subtitle">
            Start your productivity journey with Zana AI today
          </p>
          <a 
            href={telegramBotLink}
            className="home-cta-button home-cta-button-large"
            target="_blank"
            rel="noopener noreferrer"
          >
            Get Started on Telegram
          </a>
        </section>
      )}
    </div>
  );
}


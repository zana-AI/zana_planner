import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, BarChart3, BrainCircuit, CalendarClock, CheckCircle2, MessageCircle, Sparkles, Users } from 'lucide-react';
import { apiClient } from '../api/client';
import { AppLogo } from './ui/AppLogo';
import { TelegramLogin } from './TelegramLogin';
import { HomeMockupGallery, HomeMockupPreviewStack } from './home/HomeMockups';

function isMobileDevice(): boolean {
  if (typeof window === 'undefined') return false;

  const userAgent = navigator.userAgent || navigator.vendor || (window as any).opera;
  const mobileRegex = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini/i;
  const hasTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  const isSmallViewport = window.innerWidth < 768;

  return mobileRegex.test(userAgent) || (hasTouch && isSmallViewport);
}

const valueCards = [
  {
    icon: Users,
    title: 'Stay close to your people',
    body: 'Create clubs for routines you want to keep with friends: running, study, deep work, language practice, anything that benefits from being visible.',
  },
  {
    icon: CalendarClock,
    title: 'Turn intent into a next session',
    body: 'Promises become scheduled actions, reminders, and check-ins, so the week has a shape before motivation disappears.',
  },
  {
    icon: BrainCircuit,
    title: 'Let agentic AI keep the thread',
    body: 'Xaana watches progress, spots drift, suggests the next move, and nudges the right people at the right moment.',
  },
  {
    icon: BarChart3,
    title: 'See what is actually working',
    body: 'Weekly progress, club momentum, and simple visualizations show whether your routines are becoming real.',
  },
];

export function HomePage() {
  const navigate = useNavigate();
  const [isMobile, setIsMobile] = useState(false);
  const [botUsername, setBotUsername] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('telegram_auth_token');
    const hasInitData = window.Telegram?.WebApp?.initData;

    if (token || hasInitData) {
      setIsAuthenticated(true);
      navigate('/dashboard', { replace: true });
      return;
    }

    setIsAuthenticated(false);
  }, [navigate]);

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(isMobileDevice());
    };

    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  useEffect(() => {
    const fetchBotUsername = async () => {
      try {
        const response = await fetch('/api/auth/bot-username');
        if (!response.ok) return;
        const data = await response.json();
        if (data.bot_username) setBotUsername(data.bot_username.trim());
      } catch (error) {
        console.error('Failed to fetch bot username:', error);
      }
    };

    fetchBotUsername();
  }, []);

  const handleAuthSuccess = (token: string) => {
    apiClient.setAuthToken(token);
    navigate('/dashboard', { replace: true });
  };

  const telegramBotLink = botUsername ? `https://t.me/${botUsername}` : 'https://t.me/zana_planner_bot';
  const telegramWebAppLink = botUsername ? `https://t.me/${botUsername}?startapp=webapp` : 'https://t.me/zana_planner_bot?startapp=webapp';

  if (isAuthenticated) return null;

  return (
    <main className="home-page home-page-v2">
      <section className="home-v2-hero" aria-labelledby="home-title">
        <div className="home-v2-hero-copy">
          <div className="home-v2-brand-row">
            <AppLogo size={34} />
            <span>Xaana</span>
          </div>
          <p className="home-v2-eyebrow">Resolutions, kept together</p>
          <h1 id="home-title">Build routines with friends and an AI that keeps the week moving.</h1>
          <p className="home-v2-lede">
            Make a promise, plan the next session, check in with your club, and see progress before motivation fades.
          </p>
          <div className="home-v2-actions">
            <a href={telegramBotLink} className="home-v2-button home-v2-button-primary" target="_blank" rel="noopener noreferrer">
              Start with Xaana
              <ArrowRight size={18} />
            </a>
            <a href="#how-it-works" className="home-v2-button home-v2-button-secondary">
              See how it works
            </a>
          </div>
          <div className="home-v2-proof" aria-label="Core Xaana workflow">
            <span><CheckCircle2 size={16} /> Promise</span>
            <span><CalendarClock size={16} /> Plan</span>
            <span><MessageCircle size={16} /> Check in</span>
            <span><Sparkles size={16} /> Adjust</span>
          </div>
        </div>

        <div className="home-v2-hero-visual">
          <HomeMockupPreviewStack />
        </div>
      </section>

      <section className="home-v2-login" aria-label="Sign in">
        <div>
          <h2>Sign in to Xaana</h2>
          <p>Use Telegram to continue into your routines, clubs, and weekly progress.</p>
        </div>
        <TelegramLogin onAuthSuccess={handleAuthSuccess} />
        {isMobile && (
          <a href={telegramWebAppLink} className="home-v2-telegram-link">
            Open directly in Telegram
            <ArrowRight size={16} />
          </a>
        )}
      </section>

      <section id="how-it-works" className="home-v2-values" aria-labelledby="home-values-title">
        <div className="home-v2-section-heading">
          <p className="home-v2-eyebrow">How Xaana helps</p>
          <h2 id="home-values-title">Less dashboard, more follow-through.</h2>
          <p>
            Xaana is built for the gap between deciding something matters and actually repeating it next week.
          </p>
        </div>
        <div className="home-v2-value-grid">
          {valueCards.map((item) => {
            const Icon = item.icon;
            return (
              <article key={item.title} className="home-v2-value-card">
                <Icon size={24} />
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section className="home-v2-showcase" aria-labelledby="home-showcase-title">
        <div className="home-v2-section-heading">
          <p className="home-v2-eyebrow">Product moments</p>
          <h2 id="home-showcase-title">A week you can act on.</h2>
          <p>
            The home page uses synthetic app states, not user data, to show the surfaces that matter most now.
          </p>
        </div>
        <HomeMockupGallery />
      </section>

      <section className="home-v2-final">
        <h2>Start with one promise and one person.</h2>
        <p>Xaana helps the routine become visible, social, and easier to keep.</p>
        <a href={telegramBotLink} className="home-v2-button home-v2-button-primary" target="_blank" rel="noopener noreferrer">
          Get started on Telegram
          <ArrowRight size={18} />
        </a>
      </section>
    </main>
  );
}

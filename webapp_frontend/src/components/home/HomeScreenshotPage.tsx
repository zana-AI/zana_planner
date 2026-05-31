import { Navigate, useParams } from 'react-router-dom';
import { useEffect } from 'react';
import { HomeMockupScreen, type HomeMockupId } from './HomeMockups';

const VALID_SCREENS = new Set<HomeMockupId>([
  'my-week',
  'community-clubs',
  'planned-sessions',
  'telegram-chat',
]);

export function HomeScreenshotPage() {
  const { screen } = useParams<{ screen: string }>();

  useEffect(() => {
    document.body.classList.add('home-shot-mode');
    return () => document.body.classList.remove('home-shot-mode');
  }, []);

  if (!import.meta.env.DEV) {
    return <Navigate to="/" replace />;
  }

  if (!screen || !VALID_SCREENS.has(screen as HomeMockupId)) {
    return <Navigate to="/__home-screenshots/my-week" replace />;
  }

  return (
    <div className="home-shot-page">
      <HomeMockupScreen id={screen as HomeMockupId} />
    </div>
  );
}

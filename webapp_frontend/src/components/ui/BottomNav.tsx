import { useLocation, useNavigate } from 'react-router-dom';
import { Compass, Home, Users } from 'lucide-react';
import type { AppNavItem } from '../../types';

interface BottomNavProps {
  items: AppNavItem[];
}

export function BottomNav({ items }: BottomNavProps) {
  const navigate = useNavigate();
  const location = useLocation();

  const getIcon = (key: AppNavItem['key']) => {
    if (key === 'today') return <Home size={18} />;
    if (key === 'community') return <Users size={18} />;
    return <Compass size={18} />;
  };

  return (
    <nav className="ui-bottom-nav" aria-label="Primary navigation">
      {items.map((item) => {
        const isActive = location.pathname === item.to || (item.to !== '/dashboard' && location.pathname.startsWith(item.to));
        return (
          <button
            key={item.key}
            className={['ui-bottom-nav-item', isActive ? 'active' : ''].join(' ')}
            onClick={() => navigate(item.to)}
            aria-current={isActive ? 'page' : undefined}
          >
            <span className="ui-bottom-nav-icon">{getIcon(item.key)}</span>
            <span className="ui-bottom-nav-label">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

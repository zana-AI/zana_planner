import { ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useCallback } from 'react';
import type { ReactNode } from 'react';
import { useTelegramBackButton } from '../../hooks/useTelegramBackButton';
import { Button } from './Button';
import { AppLogo } from './AppLogo';

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  showBack?: boolean;
  backLabel?: string;
  fallbackRoute?: string;
  onBack?: () => void;
  rightSlot?: ReactNode;
}

export function PageHeader({
  title,
  subtitle,
  showBack = false,
  backLabel = 'Back',
  fallbackRoute = '/dashboard',
  onBack,
  rightSlot,
}: PageHeaderProps) {
  const navigate = useNavigate();

  const handleBack = useCallback(() => {
    if (onBack) {
      onBack();
      return;
    }
    if (window.history.length > 1) {
      navigate(-1);
    } else {
      navigate(fallbackRoute, { replace: true });
    }
  }, [navigate, onBack, fallbackRoute]);

  useTelegramBackButton({ enabled: showBack, onClick: handleBack });

  return (
    <header className="ui-page-header">
      <div className="ui-page-header-left">
        {showBack ? (
          <Button variant="ghost" size="sm" onClick={handleBack} leftIcon={<ArrowLeft size={16} />}>
            {backLabel}
          </Button>
        ) : (
          <AppLogo size={26} />
        )}
        <div className="ui-page-title-wrap">
          <h1 className="ui-page-title">{title}</h1>
          {subtitle ? <p className="ui-page-subtitle">{subtitle}</p> : null}
        </div>
      </div>
      {rightSlot ? <div className="ui-page-header-right">{rightSlot}</div> : null}
    </header>
  );
}

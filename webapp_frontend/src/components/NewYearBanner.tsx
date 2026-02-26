import { useState, useEffect } from 'react';
import { Emoji } from './ui/Emoji';

export function NewYearBanner() {
  const [isDismissed, setIsDismissed] = useState(false);

  useEffect(() => {
    // Check if banner was already dismissed
    const dismissed = localStorage.getItem('newYearBanner2026_dismissed');
    if (dismissed === 'true') {
      setIsDismissed(true);
    }
  }, []);

  const handleDismiss = () => {
    localStorage.setItem('newYearBanner2026_dismissed', 'true');
    setIsDismissed(true);
  };

  if (isDismissed) {
    return null;
  }

  return (
    <div className="new-year-banner">
      <div className="new-year-banner-content">
        <span className="new-year-banner-emoji"><Emoji emoji="🎉" size={18} /></span>
        <span className="new-year-banner-text">
          Happy New Year 2026! Start achieving your goals with Xaana
        </span>
      </div>
      <button 
        className="new-year-banner-close"
        onClick={handleDismiss}
        aria-label="Dismiss banner"
      >
        ×
      </button>
    </div>
  );
}


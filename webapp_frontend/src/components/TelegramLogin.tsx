import { useEffect, useRef, useState } from 'react';
import { apiClient } from '../api/client';

interface TelegramLoginProps {
  onAuthSuccess: (token: string) => void;
  botName?: string; // Optional bot name, will be fetched if not provided
  buttonSize?: 'large' | 'medium' | 'small';
  cornerRadius?: number;
  requestAccess?: boolean;
}

export function TelegramLogin({ 
  onAuthSuccess, 
  botName,
  buttonSize = 'large',
  cornerRadius = 8,
  requestAccess = true
}: TelegramLoginProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [botUsername, setBotUsername] = useState<string | null>(botName || null);
  const [loading, setLoading] = useState(!botName);

  useEffect(() => {
    // Fetch bot username if not provided
    const fetchBotUsername = async () => {
      if (botName) {
        setBotUsername(botName);
        setLoading(false);
        return;
      }

      try {
        const response = await fetch('/api/auth/bot-username');
        if (response.ok) {
          const data = await response.json();
          setBotUsername(data.bot_username);
        } else {
          console.error('Failed to fetch bot username');
        }
      } catch (error) {
        console.error('Error fetching bot username:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchBotUsername();
  }, [botName]);

  useEffect(() => {
    if (loading || !botUsername || !containerRef.current) {
      return;
    }

    // Clean up any existing script
    const existingScript = containerRef.current.querySelector('script[data-telegram-login]');
    if (existingScript) {
      existingScript.remove();
    }

    // Define global callback function
    (window as any).onTelegramAuth = async (user: any) => {
      try {
        // Send auth data to backend
        const response = await fetch('/api/auth/telegram-login', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ auth_data: user }),
        });
        
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || 'Authentication failed');
        }
        
        const data = await response.json();
        
        // Store token
        localStorage.setItem('telegram_auth_token', data.session_token);
        
        // Update API client
        apiClient.setAuthToken(data.session_token);
        
        // Call success callback
        onAuthSuccess(data.session_token);
      } catch (error) {
        console.error('Telegram login error:', error);
        alert(`Login failed: ${error instanceof Error ? error.message : 'Unknown error'}. Please try again.`);
      }
    };
    
    // Load Telegram Login Widget script
    const script = document.createElement('script');
    script.src = 'https://telegram.org/js/telegram-widget.js?22';
    script.setAttribute('data-telegram-login', botUsername);
    script.setAttribute('data-size', buttonSize);
    script.setAttribute('data-radius', cornerRadius.toString());
    script.setAttribute('data-request-access', requestAccess ? 'write' : '');
    script.setAttribute('data-userpic', 'true');
    script.setAttribute('data-onauth', 'onTelegramAuth(user)');
    script.async = true;
    
    containerRef.current.appendChild(script);
    
    return () => {
      // Cleanup
      if (containerRef.current && script.parentNode) {
        script.parentNode.removeChild(script);
      }
      delete (window as any).onTelegramAuth;
    };
  }, [botUsername, loading, buttonSize, cornerRadius, requestAccess, onAuthSuccess]);

  if (loading) {
    return (
      <div className="telegram-login-loading">
        <div className="loading-spinner" />
        <div>Loading login...</div>
      </div>
    );
  }

  if (!botUsername) {
    return (
      <div className="telegram-login-error">
        <p>Unable to load Telegram login. Please try again later.</p>
      </div>
    );
  }

  return <div ref={containerRef} className="telegram-login-container" />;
}


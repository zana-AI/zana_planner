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
        const responseText = await response.text();
        console.log('Bot username API response:', response.status, responseText);
        
        if (response.ok) {
          try {
            const data = JSON.parse(responseText);
            const username = data.bot_username;
            console.log('Parsed bot username:', username);
            if (username && typeof username === 'string' && username.trim()) {
              setBotUsername(username.trim());
            } else {
              console.error('Bot username is empty or invalid:', username, typeof username);
              setBotUsername(null);
            }
          } catch (parseError) {
            console.error('Failed to parse bot username response:', parseError, responseText);
            setBotUsername(null);
          }
        } else {
          console.error('Failed to fetch bot username:', response.status, responseText);
          setBotUsername(null);
        }
      } catch (error) {
        console.error('Error fetching bot username:', error);
        setBotUsername(null);
      } finally {
        setLoading(false);
      }
    };

    fetchBotUsername();
  }, [botName]);

  useEffect(() => {
    if (loading || !botUsername || !botUsername.trim() || !containerRef.current) {
      return;
    }

    console.log('Loading Telegram Login Widget for bot:', botUsername);

    // Clean up any existing script
    const existingScript = containerRef.current.querySelector('script[data-telegram-login]');
    if (existingScript) {
      existingScript.remove();
    }

    // Set a timeout to check if widget rendered
    const timeoutId = setTimeout(() => {
      const widgetIframe = containerRef.current?.querySelector('iframe');
      if (!widgetIframe) {
        console.warn('Telegram widget did not render after 3 seconds. Bot username:', botUsername);
        // Widget might not render if domain isn't whitelisted in Telegram Bot settings
      }
    }, 3000);

    // Define global callback function
    (window as any).onTelegramAuth = async (user: any) => {
      console.log('Telegram auth callback received:', user);
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
    script.setAttribute('data-telegram-login', botUsername.trim());
    script.setAttribute('data-size', buttonSize);
    script.setAttribute('data-radius', cornerRadius.toString());
    if (requestAccess) {
      script.setAttribute('data-request-access', 'write');
    }
    script.setAttribute('data-userpic', 'true');
    script.setAttribute('data-onauth', 'onTelegramAuth(user)');
    script.async = true;
    
    // Handle script load errors
    script.onerror = () => {
      console.error('Failed to load Telegram widget script');
    };
    
    script.onload = () => {
      console.log('Telegram widget script loaded');
    };
    
    containerRef.current.appendChild(script);
    
    return () => {
      // Cleanup
      clearTimeout(timeoutId);
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
        <p>Unable to load Telegram login. Bot username not available.</p>
        <p style={{ fontSize: '0.9em', marginTop: '0.5rem', opacity: 0.8 }}>
          Please check server configuration or try again later.
        </p>
      </div>
    );
  }

  return (
    <div 
      ref={containerRef} 
      className="telegram-login-container" 
      style={{ 
        minHeight: '60px',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center'
      }} 
    />
  );
}



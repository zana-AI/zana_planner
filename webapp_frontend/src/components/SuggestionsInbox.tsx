import { useState, useEffect } from 'react';
import { apiClient, ApiError } from '../api/client';
import type { PromiseSuggestion } from '../types';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';

export function SuggestionsInbox() {
  const { hapticFeedback } = useTelegramWebApp();
  const [suggestions, setSuggestions] = useState<PromiseSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [processing, setProcessing] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadSuggestions();
  }, []);

  const loadSuggestions = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiClient.getSuggestionsInbox();
      setSuggestions(data.suggestions || []);
    } catch (err) {
      console.error('Failed to load suggestions:', err);
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to load suggestions');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleAccept = async (suggestionId: string) => {
    if (processing.has(suggestionId)) return;
    
    setProcessing(prev => new Set(prev).add(suggestionId));
    hapticFeedback?.impactOccurred('medium');
    
    try {
      await apiClient.acceptSuggestion(suggestionId);
      hapticFeedback?.notificationOccurred('success');
      // Remove from list
      setSuggestions(prev => prev.filter(s => s.suggestion_id !== suggestionId));
    } catch (err) {
      console.error('Failed to accept suggestion:', err);
      hapticFeedback?.notificationOccurred('error');
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to accept suggestion');
      }
    } finally {
      setProcessing(prev => {
        const next = new Set(prev);
        next.delete(suggestionId);
        return next;
      });
    }
  };

  const handleDecline = async (suggestionId: string) => {
    if (processing.has(suggestionId)) return;
    
    setProcessing(prev => new Set(prev).add(suggestionId));
    hapticFeedback?.impactOccurred('light');
    
    try {
      await apiClient.declineSuggestion(suggestionId);
      hapticFeedback?.notificationOccurred('success');
      // Remove from list
      setSuggestions(prev => prev.filter(s => s.suggestion_id !== suggestionId));
    } catch (err) {
      console.error('Failed to decline suggestion:', err);
      hapticFeedback?.notificationOccurred('error');
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to decline suggestion');
      }
    } finally {
      setProcessing(prev => {
        const next = new Set(prev);
        next.delete(suggestionId);
        return next;
      });
    }
  };

  if (loading) {
    return <div style={{ padding: '2rem', textAlign: 'center', color: 'rgba(232, 238, 252, 0.6)' }}>Loading suggestions...</div>;
  }

  if (error && suggestions.length === 0) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <div style={{ color: '#ff6b6b', marginBottom: '1rem' }}>{error}</div>
        <button className="button-primary" onClick={loadSuggestions}>Retry</button>
      </div>
    );
  }

  if (suggestions.length === 0) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: 'rgba(232, 238, 252, 0.6)' }}>
        No pending suggestions
      </div>
    );
  }

  return (
    <div style={{ padding: '1rem' }}>
      {error && (
        <div style={{ color: '#ff6b6b', marginBottom: '1rem', padding: '0.75rem', background: 'rgba(255, 107, 107, 0.1)', borderRadius: '6px' }}>
          {error}
        </div>
      )}
      
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {suggestions.map((suggestion) => {
          const isProcessing = processing.has(suggestion.suggestion_id);
          let draftData = null;
          if (suggestion.draft_json) {
            try {
              draftData = JSON.parse(suggestion.draft_json);
            } catch (e) {
              // Ignore parse errors
            }
          }

          return (
            <div
              key={suggestion.suggestion_id}
              style={{
                border: '1px solid rgba(232, 238, 252, 0.15)',
                borderRadius: '12px',
                padding: '1rem',
                background: 'linear-gradient(180deg, rgba(15,26,56,0.98), rgba(15,23,48,0.98))'
              }}
            >
              <div style={{ marginBottom: '0.75rem' }}>
                <div style={{ fontSize: '0.85rem', color: 'rgba(232, 238, 252, 0.6)', marginBottom: '0.25rem' }}>
                  From {suggestion.from_user_name || `User ${suggestion.from_user_id}`}
                </div>
                {suggestion.message && (
                  <div style={{ color: 'rgba(232, 238, 252, 0.8)', fontSize: '0.9rem', marginTop: '0.5rem' }}>
                    "{suggestion.message}"
                  </div>
                )}
              </div>

              <div style={{ marginBottom: '0.75rem' }}>
                {draftData ? (
                  <div>
                    <div style={{ fontWeight: '600', color: '#fff', marginBottom: '0.25rem' }}>
                      {draftData.title || 'Custom Promise'}
                    </div>
                    {draftData.why && (
                      <div style={{ fontSize: '0.85rem', color: 'rgba(232, 238, 252, 0.7)', marginTop: '0.25rem' }}>
                        {draftData.why}
                      </div>
                    )}
                  </div>
                ) : suggestion.template_id ? (
                  <div style={{ color: 'rgba(232, 238, 252, 0.8)' }}>
                    Template-based promise
                  </div>
                ) : (
                  <div style={{ color: 'rgba(232, 238, 252, 0.8)' }}>
                    Promise suggestion
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                <button
                  className="button-secondary"
                  onClick={() => handleDecline(suggestion.suggestion_id)}
                  disabled={isProcessing}
                  style={{ flex: 1 }}
                >
                  {isProcessing ? '...' : 'Decline'}
                </button>
                <button
                  className="button-primary"
                  onClick={() => handleAccept(suggestion.suggestion_id)}
                  disabled={isProcessing}
                  style={{ flex: 1 }}
                >
                  {isProcessing ? 'Processing...' : 'Accept'}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

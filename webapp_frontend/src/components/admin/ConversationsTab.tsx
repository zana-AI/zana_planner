import { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';
import type { AdminUser, ConversationMessage } from '../../types';
import { UserSelector } from './UserSelector';

interface ConversationsTabProps {
  users: AdminUser[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
}

export function ConversationsTab({
  users,
  searchQuery,
  setSearchQuery,
}: ConversationsTabProps) {
  const [conversations, setConversations] = useState<ConversationMessage[]>([]);
  const [loadingConversations, setLoadingConversations] = useState(false);
  const [selectedConversationUserId, setSelectedConversationUserId] = useState<number | null>(null);
  const [revealedMessageIds, setRevealedMessageIds] = useState<Set<number>>(new Set());
  const [showAllUserMessages, setShowAllUserMessages] = useState(false);

  useEffect(() => {
    if (!selectedConversationUserId) {
      setConversations([]);
      return;
    }
    const fetchConversations = async () => {
      setLoadingConversations(true);
      try {
        const response = await apiClient.getUserConversations(selectedConversationUserId.toString(), 100);
        setConversations([...response.messages].reverse());
        setRevealedMessageIds(new Set());
        setShowAllUserMessages(false);
      } catch (err) {
        console.error('Failed to fetch conversations:', err);
      } finally {
        setLoadingConversations(false);
      }
    };
    fetchConversations();
  }, [selectedConversationUserId]);

  const toggleRevealMessage = (messageId: number) => {
    const newRevealed = new Set(revealedMessageIds);
    if (newRevealed.has(messageId)) newRevealed.delete(messageId);
    else newRevealed.add(messageId);
    setRevealedMessageIds(newRevealed);
  };

  const toggleShowAllUserMessages = () => setShowAllUserMessages(!showAllUserMessages);

  const isMessageRevealed = (msg: ConversationMessage) => msg.message_type === 'bot' || showAllUserMessages || revealedMessageIds.has(msg.id);

  return (
    <div className="admin-panel-compose">
      <div className="admin-section">
        <h2 className="admin-section-title">Select User</h2>
        <UserSelector
          users={users}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          selectedUserId={selectedConversationUserId}
          onSelectUser={setSelectedConversationUserId}
          mode="single"
          maxHeight="200px"
        />
      </div>

      {selectedConversationUserId && (
        <div className="admin-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 className="admin-section-title" style={{ margin: 0 }}>Conversation History</h2>
            {conversations.some(m => m.message_type === 'user') && (
              <button
                onClick={toggleShowAllUserMessages}
                style={{
                  padding: '0.5rem 1rem',
                  background: showAllUserMessages ? 'rgba(255, 107, 107, 0.2)' : 'rgba(91, 163, 245, 0.2)',
                  border: `1px solid ${showAllUserMessages ? 'rgba(255, 107, 107, 0.4)' : 'rgba(91, 163, 245, 0.4)'}`,
                  borderRadius: '6px',
                  color: '#fff',
                  cursor: 'pointer',
                  fontSize: '0.85rem'
                }}
              >
                {showAllUserMessages ? 'Hide All User Messages' : 'Show All User Messages'}
              </button>
            )}
          </div>
          {loadingConversations ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: 'rgba(232, 238, 252, 0.6)' }}>Loading conversations...</div>
          ) : conversations.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: 'rgba(232, 238, 252, 0.6)' }}>No conversations found</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', maxHeight: '500px', overflowY: 'auto', padding: '0.5rem' }}>
              {conversations.map((msg) => {
                const isUser = msg.message_type === 'user';
                const revealed = isMessageRevealed(msg);
                return (
                  <div key={msg.id} style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start' }}>
                    <div style={{
                      maxWidth: '80%',
                      padding: '0.75rem 1rem',
                      borderRadius: isUser ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
                      background: isUser ? 'rgba(91, 163, 245, 0.2)' : 'rgba(232, 238, 252, 0.1)',
                      border: `1px solid ${isUser ? 'rgba(91, 163, 245, 0.3)' : 'rgba(232, 238, 252, 0.15)'}`
                    }}>
                      <div style={{ fontSize: '0.75rem', color: 'rgba(232, 238, 252, 0.5)', marginBottom: '0.25rem' }}>
                        {isUser ? 'User' : 'Bot'} • {new Date(msg.created_at_utc).toLocaleString()}
                      </div>
                      {revealed ? (
                        <div style={{ color: '#fff', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{msg.content}</div>
                      ) : (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <span style={{ color: 'rgba(232, 238, 252, 0.4)', fontStyle: 'italic' }}>[User message hidden]</span>
                          <button
                            onClick={() => toggleRevealMessage(msg.id)}
                            style={{
                              padding: '0.25rem 0.5rem',
                              background: 'rgba(91, 163, 245, 0.2)',
                              border: '1px solid rgba(91, 163, 245, 0.4)',
                              borderRadius: '4px',
                              color: '#5ba3f5',
                              cursor: 'pointer',
                              fontSize: '0.75rem'
                            }}
                          >
                            Show
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

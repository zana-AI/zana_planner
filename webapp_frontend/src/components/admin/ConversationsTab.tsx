import { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';
import type { AdminUser, ConversationMessage } from '../../types';
import { UserSelector } from './UserSelector';

const ALLOWED_RICH_TAGS = new Set([
  'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del',
  'code', 'pre', 'blockquote', 'a', 'br'
]);

const ALLOWED_RICH_ATTRIBUTES: Record<string, Set<string>> = {
  a: new Set(['href']),
  blockquote: new Set(['expandable'])
};

const SAFE_LINK_PROTOCOLS = new Set(['http:', 'https:', 'mailto:', 'tg:']);

function sanitizeConversationHtml(rawContent: string): string {
  if (!rawContent) return '';
  if (typeof window === 'undefined') return rawContent;

  const parser = new DOMParser();
  const doc = parser.parseFromString(rawContent, 'text/html');

  const sanitizeNode = (parent: Node) => {
    const children = Array.from(parent.childNodes);
    children.forEach((child) => {
      if (child.nodeType === Node.COMMENT_NODE) {
        child.remove();
        return;
      }

      if (child.nodeType !== Node.ELEMENT_NODE) {
        return;
      }

      const element = child as HTMLElement;
      const tagName = element.tagName.toLowerCase();
      if (!ALLOWED_RICH_TAGS.has(tagName)) {
        const fragment = document.createDocumentFragment();
        while (element.firstChild) {
          fragment.appendChild(element.firstChild);
        }
        element.replaceWith(fragment);
        sanitizeNode(fragment);
        return;
      }

      const allowedAttributes = ALLOWED_RICH_ATTRIBUTES[tagName] ?? new Set<string>();
      Array.from(element.attributes).forEach((attribute) => {
        const attrName = attribute.name.toLowerCase();
        if (!allowedAttributes.has(attrName)) {
          element.removeAttribute(attribute.name);
        }
      });

      if (tagName === 'a') {
        const href = element.getAttribute('href');
        if (!href) {
          element.removeAttribute('href');
        } else {
          try {
            const url = new URL(href, window.location.origin);
            if (!SAFE_LINK_PROTOCOLS.has(url.protocol)) {
              element.removeAttribute('href');
            }
          } catch {
            element.removeAttribute('href');
          }
        }
        if (element.getAttribute('href')) {
          element.setAttribute('target', '_blank');
          element.setAttribute('rel', 'noopener noreferrer');
        } else {
          element.removeAttribute('target');
          element.removeAttribute('rel');
        }
      }

      sanitizeNode(element);
    });
  };

  sanitizeNode(doc.body);
  return doc.body.innerHTML;
}

function toSafeFilePart(value: string): string {
  const normalized = value.trim().replace(/[^a-zA-Z0-9._-]+/g, '_').replace(/^_+|_+$/g, '');
  return normalized || 'conversation';
}

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
  const [exportingFormat, setExportingFormat] = useState<'html' | 'json' | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

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
  const selectedConversationUser = selectedConversationUserId
    ? users.find((user) => user.user_id === selectedConversationUserId.toString()) ?? null
    : null;

  const exportConversation = async (format: 'html' | 'json') => {
    if (!selectedConversationUserId) return;
    setExportError(null);
    setExportingFormat(format);
    try {
      const blob = await apiClient.exportUserConversations(selectedConversationUserId.toString(), {
        limit: 10000,
        format
      });

      const userLabel = selectedConversationUser?.username || selectedConversationUser?.first_name || `user_${selectedConversationUserId}`;
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      const extension = format === 'html' ? 'html' : 'json';
      const fileName = `${toSafeFilePart(userLabel)}_conversation_${timestamp}.${extension}`;

      const downloadUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(downloadUrl);
    } catch (err) {
      console.error('Failed to export conversation:', err);
      setExportError(`Failed to export ${format.toUpperCase()} conversation.`);
    } finally {
      setExportingFormat(null);
    }
  };

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
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
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
              <button
                onClick={() => exportConversation('html')}
                disabled={exportingFormat !== null}
                style={{
                  padding: '0.5rem 1rem',
                  background: 'rgba(91, 163, 245, 0.18)',
                  border: '1px solid rgba(91, 163, 245, 0.45)',
                  borderRadius: '6px',
                  color: '#fff',
                  cursor: exportingFormat ? 'not-allowed' : 'pointer',
                  fontSize: '0.85rem',
                  opacity: exportingFormat ? 0.6 : 1
                }}
              >
                {exportingFormat === 'html' ? 'Exporting HTML...' : 'Export HTML'}
              </button>
              <button
                onClick={() => exportConversation('json')}
                disabled={exportingFormat !== null}
                style={{
                  padding: '0.5rem 1rem',
                  background: 'rgba(232, 238, 252, 0.12)',
                  border: '1px solid rgba(232, 238, 252, 0.35)',
                  borderRadius: '6px',
                  color: '#fff',
                  cursor: exportingFormat ? 'not-allowed' : 'pointer',
                  fontSize: '0.85rem',
                  opacity: exportingFormat ? 0.6 : 1
                }}
              >
                {exportingFormat === 'json' ? 'Exporting JSON...' : 'Export JSON'}
              </button>
            </div>
          </div>
          {exportError && (
            <div style={{
              marginBottom: '0.75rem',
              color: '#fca5a5',
              fontSize: '0.85rem'
            }}>
              {exportError}
            </div>
          )}
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
                        {isUser ? 'User' : 'Bot'} | {new Date(msg.created_at_utc).toLocaleString()}
                      </div>
                      {revealed ? (
                        isUser ? (
                          <div style={{ color: '#fff', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{msg.content}</div>
                        ) : (
                          <div
                            className="admin-conversation-rich-content"
                            style={{ color: '#fff', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                            dangerouslySetInnerHTML={{ __html: sanitizeConversationHtml(msg.content) }}
                          />
                        )
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

import { useState, useMemo } from 'react';
import { apiClient, ApiError } from '../../api/client';
import type { AdminUser } from '../../types';

interface UsersTabProps {
  users: AdminUser[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  onUsersChange: (updatedUser: AdminUser) => void;
  onError: (error: string) => void;
}

interface EditState {
  non_latin_name: string;
  latin_name: string;
}

export function UsersTab({ users, searchQuery, setSearchQuery, onUsersChange, onError }: UsersTabProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editState, setEditState] = useState<EditState>({ non_latin_name: '', latin_name: '' });
  const [saving, setSaving] = useState(false);

  const filtered = useMemo(() => {
    const q = searchQuery.toLowerCase();
    if (!q) return users;
    return users.filter(
      (u) =>
        (u.first_name || '').toLowerCase().includes(q) ||
        (u.last_name || '').toLowerCase().includes(q) ||
        (u.username || '').toLowerCase().includes(q) ||
        (u.non_latin_name || '').includes(searchQuery) ||
        (u.latin_name || '').toLowerCase().includes(q) ||
        u.user_id.includes(q),
    );
  }, [users, searchQuery]);

  const startEdit = (user: AdminUser) => {
    setEditingId(user.user_id);
    setEditState({
      non_latin_name: user.non_latin_name || '',
      latin_name: user.latin_name || '',
    });
    onError('');
  };

  const cancelEdit = () => {
    setEditingId(null);
  };

  const saveEdit = async (userId: string) => {
    setSaving(true);
    onError('');
    try {
      const updated = await apiClient.updateAdminUser(userId, {
        non_latin_name: editState.non_latin_name || null,
        latin_name: editState.latin_name || null,
      });
      onUsersChange(updated);
      setEditingId(null);
    } catch (err) {
      if (err instanceof ApiError) {
        onError(err.message || 'Failed to save user names.');
      } else {
        onError('Failed to save user names.');
      }
    } finally {
      setSaving(false);
    }
  };

  const displayName = (u: AdminUser) =>
    [u.first_name, u.last_name].filter(Boolean).join(' ') || u.username || u.user_id;

  return (
    <div style={{ padding: '1rem' }}>
      <div style={{ marginBottom: '1rem' }}>
        <input
          type="text"
          placeholder="Search by name, username, or ID…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            width: '100%',
            padding: '0.6rem 0.8rem',
            background: 'rgba(255,255,255,0.07)',
            border: '1px solid rgba(255,255,255,0.15)',
            borderRadius: '8px',
            color: '#e8eeff',
            fontSize: '0.9rem',
            boxSizing: 'border-box',
          }}
        />
      </div>

      <div style={{ fontSize: '0.8rem', color: 'rgba(232,238,252,0.5)', marginBottom: '0.75rem' }}>
        {filtered.length} / {users.length} users — click Edit to set non-Latin / Latin name variants
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {filtered.map((user) => {
          const isEditing = editingId === user.user_id;
          return (
            <div
              key={user.user_id}
              style={{
                background: 'rgba(15, 23, 48, 0.7)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '10px',
                padding: '0.75rem 1rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem' }}>
                <div>
                  <span style={{ fontWeight: 600, color: '#e8eeff' }}>{displayName(user)}</span>
                  {user.username && (
                    <span style={{ marginLeft: '0.5rem', color: 'rgba(232,238,252,0.5)', fontSize: '0.85rem' }}>
                      @{user.username}
                    </span>
                  )}
                  <span style={{ marginLeft: '0.5rem', color: 'rgba(232,238,252,0.3)', fontSize: '0.75rem' }}>
                    #{user.user_id}
                  </span>
                </div>
                {!isEditing && (
                  <button
                    onClick={() => startEdit(user)}
                    style={{
                      padding: '0.3rem 0.7rem',
                      background: 'rgba(99,102,241,0.2)',
                      border: '1px solid rgba(99,102,241,0.4)',
                      borderRadius: '6px',
                      color: '#a5b4fc',
                      cursor: 'pointer',
                      fontSize: '0.8rem',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    Edit names
                  </button>
                )}
              </div>

              {!isEditing && (user.non_latin_name || user.latin_name) && (
                <div style={{ marginTop: '0.4rem', fontSize: '0.85rem', color: 'rgba(232,238,252,0.6)' }}>
                  {user.non_latin_name && <span>{user.non_latin_name}</span>}
                  {user.non_latin_name && user.latin_name && (
                    <span style={{ margin: '0 0.4rem', opacity: 0.4 }}>/</span>
                  )}
                  {user.latin_name && <span>{user.latin_name}</span>}
                </div>
              )}

              {isEditing && (
                <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <label style={{ fontSize: '0.8rem', color: 'rgba(232,238,252,0.6)' }}>
                    Non-Latin name (e.g. سپیده)
                    <input
                      type="text"
                      value={editState.non_latin_name}
                      onChange={(e) => setEditState((s) => ({ ...s, non_latin_name: e.target.value }))}
                      dir="auto"
                      style={{
                        display: 'block',
                        width: '100%',
                        marginTop: '0.25rem',
                        padding: '0.45rem 0.7rem',
                        background: 'rgba(255,255,255,0.07)',
                        border: '1px solid rgba(255,255,255,0.2)',
                        borderRadius: '6px',
                        color: '#e8eeff',
                        fontSize: '0.9rem',
                        boxSizing: 'border-box',
                      }}
                    />
                  </label>
                  <label style={{ fontSize: '0.8rem', color: 'rgba(232,238,252,0.6)' }}>
                    Latin name (e.g. Sepideh Hemmatan)
                    <input
                      type="text"
                      value={editState.latin_name}
                      onChange={(e) => setEditState((s) => ({ ...s, latin_name: e.target.value }))}
                      style={{
                        display: 'block',
                        width: '100%',
                        marginTop: '0.25rem',
                        padding: '0.45rem 0.7rem',
                        background: 'rgba(255,255,255,0.07)',
                        border: '1px solid rgba(255,255,255,0.2)',
                        borderRadius: '6px',
                        color: '#e8eeff',
                        fontSize: '0.9rem',
                        boxSizing: 'border-box',
                      }}
                    />
                  </label>
                  <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
                    <button
                      onClick={() => saveEdit(user.user_id)}
                      disabled={saving}
                      style={{
                        padding: '0.4rem 1rem',
                        background: saving ? 'rgba(99,102,241,0.1)' : 'rgba(99,102,241,0.3)',
                        border: '1px solid rgba(99,102,241,0.5)',
                        borderRadius: '6px',
                        color: '#a5b4fc',
                        cursor: saving ? 'not-allowed' : 'pointer',
                        fontSize: '0.85rem',
                      }}
                    >
                      {saving ? 'Saving…' : 'Save'}
                    </button>
                    <button
                      onClick={cancelEdit}
                      disabled={saving}
                      style={{
                        padding: '0.4rem 1rem',
                        background: 'transparent',
                        border: '1px solid rgba(255,255,255,0.15)',
                        borderRadius: '6px',
                        color: 'rgba(232,238,252,0.5)',
                        cursor: 'pointer',
                        fontSize: '0.85rem',
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

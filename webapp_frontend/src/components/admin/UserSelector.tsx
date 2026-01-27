import React from 'react';
import type { AdminUser } from '../../types';

interface UserSelectorProps {
  users: AdminUser[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  selectedUserIds?: Set<number>;
  onToggleUser?: (id: number) => void;
  selectedUserId?: number | null;
  onSelectUser?: (id: number) => void;
  mode: 'single' | 'multi';
  maxHeight?: string;
  showSearchInput?: boolean;
  onSelectAll?: () => void;
  selectAllLabel?: string;
}

export function UserSelector({
  users,
  searchQuery,
  setSearchQuery,
  selectedUserIds,
  onToggleUser,
  selectedUserId,
  onSelectUser,
  mode,
  maxHeight,
  showSearchInput = true,
  onSelectAll,
  selectAllLabel,
}: UserSelectorProps) {
  // Filter users based on search query
  const filteredUsers = users.filter(user => {
    const query = searchQuery.toLowerCase();
    const firstName = user.first_name?.toLowerCase() || '';
    const lastName = user.last_name?.toLowerCase() || '';
    const username = user.username?.toLowerCase() || '';
    const userId = user.user_id.toLowerCase();
    
    return firstName.includes(query) || 
           lastName.includes(query) || 
           username.includes(query) || 
           userId.includes(query);
  });

  if (mode === 'multi') {
    return (
      <>
        {showSearchInput && (
          <div className="admin-user-controls">
            <input
              type="text"
              className="admin-search-input"
              placeholder="Search users..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {onSelectAll && (
              <button
                className="admin-select-all-btn"
                onClick={onSelectAll}
              >
                {selectAllLabel || 'Select All'}
              </button>
            )}
          </div>
        )}
        <div
          className="admin-users-table-container"
          style={maxHeight ? { maxHeight, overflowY: 'auto' } : undefined}
        >
          <table className="admin-users-table">
            <thead>
              <tr>
                <th className="admin-users-col-select">Sel</th>
                <th className="admin-users-col-name">Name</th>
                <th className="admin-users-col-tz">TZ</th>
                <th className="admin-users-col-lang">Lang</th>
                <th className="admin-users-col-count">Prom</th>
                <th className="admin-users-col-count">Acts</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((user) => {
                const userId = parseInt(user.user_id);
                const isSelected = selectedUserIds?.has(userId) || false;
                const displayName = `${user.first_name || ''} ${user.last_name || ''}`.trim() || 'Unknown';
                const usernameDisplay = user.username ? `(@${user.username})` : '';
                return (
                  <tr
                    key={user.user_id}
                    className={`admin-user-row ${isSelected ? 'selected' : ''}`}
                    onClick={() => onToggleUser?.(userId)}
                  >
                    <td className="admin-users-col-select">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => onToggleUser?.(userId)}
                        onClick={(event) => event.stopPropagation()}
                      />
                    </td>
                    <td className="admin-users-col-name">
                      <span className="admin-user-name">
                        {displayName} {usernameDisplay}
                      </span>
                    </td>
                    <td className="admin-users-col-tz">{user.timezone || '-'}</td>
                    <td className="admin-users-col-lang">{user.language || '-'}</td>
                    <td className="admin-users-col-count">{user.promise_count ?? '-'}</td>
                    <td className="admin-users-col-count">{user.activity_count ?? '-'}</td>
                  </tr>
                );
              })}
              {filteredUsers.length === 0 && (
                <tr>
                  <td colSpan={6} className="admin-no-users">No users found</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </>
    );
  } else {
    return (
      <>
        {showSearchInput && (
          <input
            type="text"
            className="admin-search-input"
            placeholder="Search users..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        )}
        <div className="admin-users-list" style={maxHeight ? { maxHeight, overflowY: 'auto' } : undefined}>
          {filteredUsers.map((user) => {
            const userId = parseInt(user.user_id);
            const isSelected = selectedUserId === userId;
            return (
              <label key={user.user_id} className="admin-user-item">
                <input
                  type="radio"
                  name="selectedUser"
                  checked={isSelected}
                  onChange={() => onSelectUser?.(userId)}
                />
                <span className="admin-user-name">
                  {user.first_name || ''} {user.last_name || ''} {user.username ? `(@${user.username})` : ''}
                </span>
                <span className="admin-user-id">ID: {user.user_id}</span>
              </label>
            );
          })}
          {filteredUsers.length === 0 && (
            <div className="admin-no-users">No users found</div>
          )}
        </div>
      </>
    );
  }
}

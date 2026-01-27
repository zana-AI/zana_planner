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
        <div className="admin-users-list" style={maxHeight ? { maxHeight, overflowY: 'auto' } : undefined}>
          {filteredUsers.map((user) => {
            const userId = parseInt(user.user_id);
            const isSelected = selectedUserIds?.has(userId) || false;
            return (
              <label key={user.user_id} className="admin-user-item">
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => onToggleUser?.(userId)}
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

import type { WeeklyReportData, UserInfo, PublicUsersResponse } from '../types';

const API_BASE = '/api';

/**
 * API client for the Zana Web App backend.
 * All requests include Telegram initData for authentication.
 */
class ApiClient {
  private initData: string = '';

  /**
   * Set the Telegram initData for authentication.
   * Should be called once when the app initializes.
   */
  setInitData(initData: string): void {
    this.initData = initData;
  }

  /**
   * Make an authenticated API request.
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE}${endpoint}`;
    
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    };

    // Add Telegram auth header if available
    if (this.initData) {
      headers['X-Telegram-Init-Data'] = this.initData;
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        response.status,
        errorData.detail || `HTTP error ${response.status}`
      );
    }

    return response.json();
  }

  /**
   * Get weekly report for the authenticated user.
   */
  async getWeeklyReport(refTime?: string): Promise<WeeklyReportData> {
    const params = refTime ? `?ref_time=${encodeURIComponent(refTime)}` : '';
    return this.request<WeeklyReportData>(`/weekly${params}`);
  }

  /**
   * Get user info for the authenticated user.
   */
  async getUserInfo(): Promise<UserInfo> {
    return this.request<UserInfo>('/user');
  }

  /**
   * Health check endpoint (no auth required).
   */
  async healthCheck(): Promise<{ status: string; service: string }> {
    const response = await fetch(`${API_BASE}/health`);
    return response.json();
  }

  /**
   * Get public list of users (no auth required).
   */
  async getPublicUsers(limit: number = 20): Promise<PublicUsersResponse> {
    const response = await fetch(`${API_BASE}/public/users?limit=${limit}`);
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        response.status,
        errorData.detail || `Failed to fetch users: ${response.statusText}`
      );
    }
    return response.json();
  }

  /**
   * Follow a user.
   */
  async followUser(targetUserId: string): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/users/${targetUserId}/follow`, {
      method: 'POST',
    });
  }

  /**
   * Unfollow a user.
   */
  async unfollowUser(targetUserId: string): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/users/${targetUserId}/follow`, {
      method: 'DELETE',
    });
  }

  /**
   * Get follow status for a user.
   */
  async getFollowStatus(targetUserId: string): Promise<{ is_following: boolean }> {
    return this.request<{ is_following: boolean }>(`/users/${targetUserId}/follow-status`);
  }

  /**
   * Update promise visibility.
   */
  async updatePromiseVisibility(promiseId: string, visibility: 'private' | 'public'): Promise<{ status: string; visibility: string }> {
    return this.request<{ status: string; visibility: string }>(`/promises/${promiseId}/visibility`, {
      method: 'PATCH',
      body: JSON.stringify({ visibility }),
    });
  }

  /**
   * Log an action (time spent) for a promise.
   */
  async logAction(promiseId: string, timeSpent: number, actionDatetime?: string): Promise<{ status: string; message: string }> {
    const body: any = {
      promise_id: promiseId,
      time_spent: timeSpent,
    };
    if (actionDatetime) {
      body.action_datetime = actionDatetime;
    }
    return this.request<{ status: string; message: string }>('/actions', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  /**
   * Snooze a promise until next week.
   */
  async snoozePromise(promiseId: string): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/promises/${promiseId}/snooze`, {
      method: 'POST',
    });
  }
}

/**
 * Custom error class for API errors.
 */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// Export singleton instance
export const apiClient = new ApiClient();

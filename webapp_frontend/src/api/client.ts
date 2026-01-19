import type { 
  WeeklyReportData, 
  UserInfo, 
  PublicUsersResponse,
  AdminUsersResponse,
  Broadcast,
  CreateBroadcastRequest,
  UpdateBroadcastRequest,
  PromiseTemplate,
  TemplateDetail,
  SubscribeTemplateRequest,
  SubscribeTemplateResponse,
  PromiseInstance,
  CheckinRequest,
  WeeklyNoteRequest,
  LogDistractionRequest,
  WeeklyDistractionsResponse
} from '../types';

const API_BASE = '/api';

/**
 * API client for the Zana Web App backend.
 * All requests include Telegram initData for authentication.
 */
class ApiClient {
  private initData: string = '';
  private authToken: string | null = null;

  /**
   * Set the Telegram initData for authentication (Telegram Mini App).
   * Should be called once when the app initializes.
   */
  setInitData(initData: string): void {
    this.initData = initData;
  }

  /**
   * Set the authentication token (browser login).
   * Also stores it in localStorage for persistence.
   */
  setAuthToken(token: string): void {
    this.authToken = token;
    localStorage.setItem('telegram_auth_token', token);
  }

  /**
   * Load authentication token from localStorage.
   * Should be called on app initialization.
   */
  loadAuthToken(): void {
    const token = localStorage.getItem('telegram_auth_token');
    if (token) {
      this.authToken = token;
    }
  }

  /**
   * Clear authentication token (logout).
   */
  clearAuth(): void {
    this.authToken = null;
    this.initData = '';
    localStorage.removeItem('telegram_auth_token');
  }

  /**
   * Make an authenticated API request.
   * Supports both session token (browser) and initData (Telegram Mini App).
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

    // Check for session token first (browser login)
    const token = this.authToken || localStorage.getItem('telegram_auth_token');
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
      // Update internal state if loaded from localStorage
      if (!this.authToken) {
        this.authToken = token;
      }
    } else if (this.initData) {
      // Fall back to Telegram Mini App initData
      headers['X-Telegram-Init-Data'] = this.initData;
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      // Handle structured error details (e.g., from FastAPI HTTPException with detail object)
      let errorMessage: string;
      if (errorData.detail) {
        if (typeof errorData.detail === 'string') {
          errorMessage = errorData.detail;
        } else if (typeof errorData.detail === 'object') {
          // For structured errors, include the full object as JSON in the message
          errorMessage = JSON.stringify(errorData.detail);
        } else {
          errorMessage = String(errorData.detail);
        }
      } else {
        errorMessage = `HTTP error ${response.status}`;
      }
      throw new ApiError(response.status, errorMessage);
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
   * Update user timezone.
   * Automatically called by Mini App on load to detect and set timezone.
   * @param force - If true, update timezone even if already set
   */
  async updateTimezone(tz: string, offsetMin?: number, force?: boolean): Promise<{ status: string; message: string; timezone: string }> {
    return this.request<{ status: string; message: string; timezone: string }>('/user/timezone', {
      method: 'POST',
      body: JSON.stringify({ tz, offsetMin, force: force || false }),
    });
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
   * Get list of users that follow the specified user.
   */
  async getFollowers(userId: string): Promise<PublicUsersResponse> {
    return this.request<PublicUsersResponse>(`/users/${userId}/followers`);
  }

  /**
   * Get list of users that the specified user follows.
   */
  async getFollowing(userId: string): Promise<PublicUsersResponse> {
    return this.request<PublicUsersResponse>(`/users/${userId}/following`);
  }

  /**
   * Get public promises for a user with stats.
   */
  async getPublicPromises(userId: string): Promise<import('../types').PublicPromiseBadge[]> {
    return this.request<import('../types').PublicPromiseBadge[]>(`/users/${userId}/public-promises`);
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
   * Update promise recurring status.
   */
  async updatePromiseRecurring(promiseId: string, recurring: boolean): Promise<{ status: string; recurring: boolean }> {
    return this.request<{ status: string; recurring: boolean }>(`/promises/${promiseId}/recurring`, {
      method: 'PATCH',
      body: JSON.stringify({ recurring }),
    });
  }

  /**
   * Update promise fields (text, hours_per_week, end_date).
   */
  async updatePromise(
    promiseId: string,
    fields: { text?: string; hours_per_week?: number; end_date?: string }
  ): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/promises/${promiseId}`, {
      method: 'PATCH',
      body: JSON.stringify(fields),
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

  // Admin API methods
  /**
   * Get all users (admin only).
   */
  async getAdminUsers(limit: number = 1000): Promise<AdminUsersResponse> {
    return this.request<AdminUsersResponse>(`/admin/users?limit=${limit}`);
  }

  /**
   * Create or schedule a broadcast (admin only).
   */
  async createBroadcast(request: CreateBroadcastRequest): Promise<Broadcast> {
    return this.request<Broadcast>('/admin/broadcast', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /**
   * List scheduled broadcasts (admin only).
   */
  async getBroadcasts(status?: string, limit: number = 100): Promise<Broadcast[]> {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    params.append('limit', limit.toString());
    return this.request<Broadcast[]>(`/admin/broadcasts?${params.toString()}`);
  }

  /**
   * Get broadcast details (admin only).
   */
  async getBroadcast(broadcastId: string): Promise<Broadcast> {
    return this.request<Broadcast>(`/admin/broadcasts/${broadcastId}`);
  }

  /**
   * Update a scheduled broadcast (admin only).
   */
  async updateBroadcast(broadcastId: string, request: UpdateBroadcastRequest): Promise<Broadcast> {
    return this.request<Broadcast>(`/admin/broadcasts/${broadcastId}`, {
      method: 'PATCH',
      body: JSON.stringify(request),
    });
  }

  /**
   * Cancel a scheduled broadcast (admin only).
   */
  async cancelBroadcast(broadcastId: string): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/admin/broadcasts/${broadcastId}`, {
      method: 'DELETE',
    });
  }

  // Admin API methods
  /**
   * Check if current user is an admin.
   */
  async checkAdminStatus(): Promise<{ is_admin: boolean }> {
    return this.request<{ is_admin: boolean }>('/admin/check');
  }

  /**
   * Get app statistics (admin only).
   */
  async getAdminStats(): Promise<{ total_users: number; active_users: number; total_promises: number }> {
    return this.request<{ total_users: number; active_users: number; total_promises: number }>('/admin/stats');
  }

  /**
   * List all templates (admin only, includes inactive).
   */
  async getAdminTemplates(): Promise<{ templates: PromiseTemplate[] }> {
    return this.request<{ templates: PromiseTemplate[] }>('/admin/templates');
  }

  /**
   * Create a new template (admin only).
   */
  async createTemplate(templateData: Partial<PromiseTemplate>): Promise<{ status: string; template_id: string }> {
    return this.request<{ status: string; template_id: string }>('/admin/templates', {
      method: 'POST',
      body: JSON.stringify(templateData),
    });
  }

  /**
   * Update an existing template (admin only).
   */
  async updateTemplate(templateId: string, templateData: Partial<PromiseTemplate>): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/admin/templates/${templateId}`, {
      method: 'PUT',
      body: JSON.stringify(templateData),
    });
  }

  /**
   * Delete a template (admin only).
   */
  async deleteTemplate(templateId: string): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/admin/templates/${templateId}`, {
      method: 'DELETE',
    });
  }

  /**
   * Promote staging database to production (admin only).
   * This copies all staging data to production database.
   */
  async promoteStagingToProd(): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>('/admin/promote', {
      method: 'POST',
    });
  }

  // Template API methods
  /**
   * List templates with optional filters.
   */
  async getTemplates(category?: string, programKey?: string): Promise<{ templates: PromiseTemplate[] }> {
    const params = new URLSearchParams();
    if (category) params.append('category', category);
    if (programKey) params.append('program_key', programKey);
    const query = params.toString();
    return this.request<{ templates: PromiseTemplate[] }>(`/templates${query ? `?${query}` : ''}`);
  }

  /**
   * Get template details with unlock status.
   */
  async getTemplate(templateId: string): Promise<TemplateDetail> {
    return this.request<TemplateDetail>(`/templates/${templateId}`);
  }

  /**
   * Subscribe to a template (creates promise + instance).
   */
  async subscribeTemplate(templateId: string, request?: SubscribeTemplateRequest): Promise<SubscribeTemplateResponse> {
    return this.request<SubscribeTemplateResponse>(`/templates/${templateId}/subscribe`, {
      method: 'POST',
      body: JSON.stringify(request || {}),
    });
  }

  /**
   * List active template instances.
   */
  async getActiveInstances(): Promise<{ instances: PromiseInstance[] }> {
    return this.request<{ instances: PromiseInstance[] }>('/instances/active');
  }

  /**
   * Record a check-in for a promise (count-based templates).
   */
  async checkinPromise(promiseId: string, request?: CheckinRequest): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/promises/${promiseId}/checkin`, {
      method: 'POST',
      body: JSON.stringify(request || {}),
    });
  }

  /**
   * Update weekly note for a promise instance.
   */
  async updateWeeklyNote(promiseId: string, request: WeeklyNoteRequest): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/promises/${promiseId}/weekly-note`, {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /**
   * Log a distraction event (for budget templates).
   */
  async logDistraction(request: LogDistractionRequest): Promise<{ status: string; event_uuid: string; message: string }> {
    return this.request<{ status: string; event_uuid: string; message: string }>('/distractions', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /**
   * Get weekly distraction summary.
   */
  async getWeeklyDistractions(refTime?: string, category?: string): Promise<WeeklyDistractionsResponse> {
    const params = new URLSearchParams();
    if (refTime) params.append('ref_time', refTime);
    if (category) params.append('category', category);
    const query = params.toString();
    return this.request<WeeklyDistractionsResponse>(`/distractions/weekly${query ? `?${query}` : ''}`);
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

// Load auth token from localStorage on initialization
apiClient.loadAuthToken();

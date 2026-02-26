import type { 
  WeeklyReportData, 
  UserInfo, 
  PublicUsersResponse,
  PublicActivityResponse,
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
  WeeklyDistractionsResponse,
  PromiseSuggestion,
  CreateSuggestionRequest,
  BotToken,
  CreatePromiseForUserRequest,
  ConversationResponse,
  FocusSession,
  Content,
  MyContentsResponse,
  HeatmapData,
  ConsumeEventRequest,
  FollowGraphData
} from '../types';

const API_BASE = '/api';

/**
 * API client for the Zana Web App backend.
 * All requests include Telegram initData for authentication.
 */
class ApiClient {
  public initData: string = '';  // Made public for TestsTab to access
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

    const token = this.authToken || localStorage.getItem('telegram_auth_token');
    const isTelegramMiniApp = typeof window !== 'undefined' && !!window.Telegram?.WebApp;

    // In Telegram Mini App mode, initData is the source of truth and should not be
    // shadowed by any stale browser session token present in localStorage.
    if (isTelegramMiniApp && this.initData) {
      headers['X-Telegram-Init-Data'] = this.initData;
    } else if (token) {
      headers['Authorization'] = `Bearer ${token}`;
      // Update internal state if loaded from localStorage
      if (!this.authToken) {
        this.authToken = token;
      }
    } else if (this.initData) {
      // Fall back to Telegram Mini App initData (e.g. development mode with dev_init_data)
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
  async getWeeklyReport(refTime?: string, signal?: AbortSignal): Promise<WeeklyReportData> {
    const params = refTime ? `?ref_time=${encodeURIComponent(refTime)}` : '';
    return this.request<WeeklyReportData>(`/weekly${params}`, { signal });
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
   * Update user settings (partial). Only provided fields are updated.
   */
  async updateUserSettings(payload: {
    timezone?: string;
    language?: string;
    voice_mode?: string | null;
    first_name?: string | null;
  }): Promise<UserInfo> {
    return this.request<UserInfo>('/user/settings', {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  }

  /**
   * Resolve content URL and upsert into catalog. Returns content row.
   */
  async resolveContent(url: string): Promise<Content & { content_id?: string }> {
    return this.request<Content & { content_id?: string }>('/content/resolve', {
      method: 'POST',
      body: JSON.stringify({ url }),
    });
  }

  /**
   * Add content to user library.
   */
  async addUserContent(contentId: string): Promise<{ user_content_id: string; status: string }> {
    return this.request<{ user_content_id: string; status: string }>('/user-content', {
      method: 'POST',
      body: JSON.stringify({ content_id: contentId }),
    });
  }

  /**
   * Get paginated list of user's content (my-contents).
   */
  async getMyContents(status?: string, cursor?: string, limit?: number): Promise<MyContentsResponse> {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (cursor) params.set('cursor', cursor);
    if (limit != null) params.set('limit', String(limit));
    const q = params.toString() ? `?${params.toString()}` : '';
    return this.request<MyContentsResponse>(`/my-contents${q}`);
  }

  /**
   * Record a consumption segment.
   */
  async postConsumeEvent(body: ConsumeEventRequest): Promise<{ progress_ratio: number; status: string }> {
    return this.request<{ progress_ratio: number; status: string }>('/consume-event', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  /**
   * Get heatmap data for a content item.
   */
  async getContentHeatmap(contentId: string): Promise<HeatmapData> {
    return this.request<HeatmapData>(`/content/${encodeURIComponent(contentId)}/heatmap`);
  }

  /**
   * Update user_content (status, notes, rating).
   */
  async updateUserContent(contentId: string, body: { status?: string; notes?: string; rating?: number }): Promise<{ content_id: string; updated: boolean }> {
    return this.request<{ content_id: string; updated: boolean }>(`/user-content/${encodeURIComponent(contentId)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
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
   * Get public list of users (authentication required).
   */
  async getPublicUsers(limit: number = 20): Promise<PublicUsersResponse> {
    return this.request<PublicUsersResponse>(`/public/users?limit=${limit}`);
  }

  /**
   * Get recent public community activity.
   */
  async getPublicActivity(limit: number = 20): Promise<PublicActivityResponse> {
    return this.request<PublicActivityResponse>(`/public/activity?limit=${limit}`);
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
   * Get public user information by ID.
   */
  async getUser(userId: string): Promise<import('../types').PublicUser> {
    return this.request<import('../types').PublicUser>(`/users/${userId}`);
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
   * Delete a promise.
   */
  async deletePromise(promiseId: string): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/promises/${promiseId}`, {
      method: 'DELETE',
    });
  }

  /**
   * Log an action (time spent) for a promise.
   */
  async logAction(promiseId: string, timeSpent: number, actionDatetime?: string, notes?: string): Promise<{ status: string; message: string }> {
    const body: any = {
      promise_id: promiseId,
      time_spent: timeSpent,
    };
    if (actionDatetime) {
      body.action_datetime = actionDatetime;
    }
    if (notes) {
      body.notes = notes;
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

  /**
   * Focus Timer / Pomodoro methods
   */
  async startFocus(promiseId: string, durationMinutes: number): Promise<FocusSession> {
    return this.request<FocusSession>('/focus/start', {
      method: 'POST',
      body: JSON.stringify({
        promise_id: promiseId,
        duration_minutes: durationMinutes,
      }),
    });
  }

  async getCurrentFocus(): Promise<FocusSession | null> {
    try {
      return await this.request<FocusSession>('/focus/current', {
        method: 'GET',
      });
    } catch (err: any) {
      if (err.status === 404 || err.status === 400) {
        return null;
      }
      throw err;
    }
  }

  async pauseFocus(sessionId: string): Promise<FocusSession> {
    return this.request<FocusSession>('/focus/pause', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    });
  }

  async resumeFocus(sessionId: string): Promise<FocusSession> {
    return this.request<FocusSession>('/focus/resume', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    });
  }

  async stopFocus(sessionId: string): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>('/focus/stop', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    });
  }

  /**
   * Get recent logs/actions for a promise.
   */
  async getPromiseLogs(promiseId: string, limit: number = 20): Promise<{ logs: Array<{ datetime: string; date: string; time_spent: number; time_str: string; notes: string | null }> }> {
    return this.request<{ logs: Array<{ datetime: string; date: string; time_spent: number; time_str: string; notes: string | null }> }>(`/promises/${promiseId}/logs?limit=${limit}`);
  }

  // Admin API methods
  /**
   * Get all users (admin only).
   */
  async getAdminUsers(limit: number = 1000): Promise<AdminUsersResponse> {
    return this.request<AdminUsersResponse>(`/admin/users?limit=${limit}`);
  }

  /**
   * Get conversation history for a user (admin only).
   */
  async getUserConversations(
    userId: string,
    limit?: number,
    messageType?: 'user' | 'bot'
  ): Promise<ConversationResponse> {
    const params = new URLSearchParams();
    if (limit !== undefined) params.append('limit', limit.toString());
    if (messageType) params.append('message_type', messageType);
    const query = params.toString();
    return this.request<ConversationResponse>(`/admin/users/${userId}/conversations${query ? `?${query}` : ''}`);
  }

  /**
   * Export conversation history for a user (admin only).
   * Returns a downloadable file as Blob (HTML or JSON).
   */
  async exportUserConversations(
    userId: string,
    options: {
      limit?: number;
      messageType?: 'user' | 'bot';
      format?: 'html' | 'json';
    } = {}
  ): Promise<Blob> {
    const params = new URLSearchParams();
    if (options.limit !== undefined) params.append('limit', options.limit.toString());
    if (options.messageType) params.append('message_type', options.messageType);
    params.append('format', options.format || 'html');
    const query = params.toString();

    const headers: Record<string, string> = {};
    const token = this.authToken || localStorage.getItem('telegram_auth_token');
    const isTelegramMiniApp = typeof window !== 'undefined' && !!window.Telegram?.WebApp;

    if (isTelegramMiniApp && this.initData) {
      headers['X-Telegram-Init-Data'] = this.initData;
    } else if (token) {
      headers['Authorization'] = `Bearer ${token}`;
      if (!this.authToken) {
        this.authToken = token;
      }
    } else if (this.initData) {
      headers['X-Telegram-Init-Data'] = this.initData;
    }

    const response = await fetch(`${API_BASE}/admin/users/${userId}/conversations/export?${query}`, {
      method: 'GET',
      headers,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      let errorMessage: string;
      if (errorData.detail) {
        if (typeof errorData.detail === 'string') {
          errorMessage = errorData.detail;
        } else if (typeof errorData.detail === 'object') {
          errorMessage = JSON.stringify(errorData.detail);
        } else {
          errorMessage = String(errorData.detail);
        }
      } else {
        errorMessage = `HTTP error ${response.status}`;
      }
      throw new ApiError(response.status, errorMessage);
    }

    return response.blob();
  }

  /**
   * Get available bot tokens (admin only).
   */
  async getBotTokens(isActive?: boolean): Promise<BotToken[]> {
    const params = new URLSearchParams();
    if (isActive !== undefined) params.append('is_active', isActive.toString());
    const query = params.toString();
    return this.request<BotToken[]>(`/admin/bot-tokens${query ? `?${query}` : ''}`);
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
   * Generate a template draft from a prompt using AI (admin only).
   */
  async generateTemplateDraft(prompt: string): Promise<Partial<PromiseTemplate>> {
    return this.request<Partial<PromiseTemplate>>('/admin/templates/generate', {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    });
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
   * Get users using a template (for "used by" badges).
   */
  async getTemplateUsers(templateId: string, limit: number = 8): Promise<{ users: Array<{ user_id: string; first_name?: string; username?: string; avatar_path?: string; avatar_file_unique_id?: string }>; total: number }> {
    return this.request<{ users: Array<{ user_id: string; first_name?: string; username?: string; avatar_path?: string; avatar_file_unique_id?: string }>; total: number }>(`/templates/${templateId}/users?limit=${limit}`);
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

  // Promise suggestions
  async createSuggestion(request: CreateSuggestionRequest): Promise<{ status: string; suggestion_id: string }> {
    return this.request<{ status: string; suggestion_id: string }>('/suggestions', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async getSuggestionsInbox(): Promise<{ suggestions: PromiseSuggestion[] }> {
    return this.request<{ suggestions: PromiseSuggestion[] }>('/suggestions/inbox');
  }

  async getSuggestionsOutbox(): Promise<{ suggestions: PromiseSuggestion[] }> {
    return this.request<{ suggestions: PromiseSuggestion[] }>('/suggestions/outbox');
  }

  async acceptSuggestion(suggestionId: string): Promise<{ status: string; message: string; promise_id: string; instance_id: string }> {
    return this.request<{ status: string; message: string; promise_id: string; instance_id: string }>(`/suggestions/${suggestionId}/accept`, {
      method: 'POST',
    });
  }

  async declineSuggestion(suggestionId: string): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/suggestions/${suggestionId}/decline`, {
      method: 'POST',
    });
  }

  /**
   * Create a promise for a user (admin only).
   */
  async createPromiseForUser(request: CreatePromiseForUserRequest): Promise<{ status: string; promise_id: string; message: string }> {
    return this.request<{ status: string; promise_id: string; message: string }>('/admin/promises', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /**
   * Get reminders for a promise.
   */
  async getPromiseReminders(promiseId: string): Promise<{ reminders: any[] }> {
    return this.request<{ reminders: any[] }>(`/promises/${promiseId}/reminders`);
  }

  /**
   * Update reminders for a promise.
   */
  async updatePromiseReminders(promiseId: string, reminders: any[]): Promise<{ status: string; message: string; reminders_count: number }> {
    return this.request<{ status: string; message: string; reminders_count: number }>(`/promises/${promiseId}/reminders`, {
      method: 'PUT',
      body: JSON.stringify({ reminders }),
    });
  }

  /**
   * Start a test run (admin only).
   */
  async startTestRun(testSuite: 'pytest' | 'scenarios' | 'both'): Promise<{ run_id: string; status: string; test_suite: string }> {
    return this.request<{ run_id: string; status: string; test_suite: string }>('/admin/tests/run', {
      method: 'POST',
      body: JSON.stringify({ test_suite: testSuite }),
    });
  }

  /**
   * Get test run report (admin only).
   */
  async getFollowGraph(limit: number = 2000): Promise<FollowGraphData> {
    return this.request(`/admin/graph/follow?limit=${limit}`);
  }

  async getTestReport(runId: string): Promise<{
    run_id: string;
    status: string;
    test_suite: string;
    started_at: string;
    completed_at?: string;
    exit_code?: number;
    report_content?: string;
  }> {
    return this.request(`/admin/tests/report/${runId}`);
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

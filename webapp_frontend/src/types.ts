/**
 * Type definitions for the Zana Web App
 */

// Telegram Web App types
export interface TelegramWebApp {
  initData: string;
  initDataUnsafe: {
    query_id?: string;
    user?: TelegramUser;
    auth_date?: number;
    hash?: string;
    start_param?: string;
  };
  version: string;
  platform: string;
  colorScheme: 'light' | 'dark';
  themeParams: {
    bg_color?: string;
    text_color?: string;
    hint_color?: string;
    link_color?: string;
    button_color?: string;
    button_text_color?: string;
    secondary_bg_color?: string;
  };
  isExpanded: boolean;
  viewportHeight: number;
  viewportStableHeight: number;
  headerColor: string;
  backgroundColor: string;
  isClosingConfirmationEnabled: boolean;
  ready: () => void;
  expand: () => void;
  close: () => void;
  MainButton: {
    text: string;
    color: string;
    textColor: string;
    isVisible: boolean;
    isActive: boolean;
    isProgressVisible: boolean;
    setText: (text: string) => void;
    onClick: (callback: () => void) => void;
    offClick: (callback: () => void) => void;
    show: () => void;
    hide: () => void;
    enable: () => void;
    disable: () => void;
    showProgress: (leaveActive?: boolean) => void;
    hideProgress: () => void;
  };
  BackButton: {
    isVisible: boolean;
    onClick: (callback: () => void) => void;
    offClick: (callback: () => void) => void;
    show: () => void;
    hide: () => void;
  };
  HapticFeedback: {
    impactOccurred: (style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') => void;
    notificationOccurred: (type: 'error' | 'success' | 'warning') => void;
    selectionChanged: () => void;
  };
  setHeaderColor: (color: string) => void;
  setBackgroundColor: (color: string) => void;
}

export interface TelegramUser {
  id: number;
  is_bot?: boolean;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  is_premium?: boolean;
  photo_url?: string;
}

// API Response types
export interface SessionData {
  date: string;
  hours: number;
}

export interface PromiseData {
  text: string;
  hours_promised: number;
  hours_spent: number;
  sessions: SessionData[];
  visibility?: string; // "private" | "public"
  recurring?: boolean;
}

export interface WeeklyReportData {
  week_start: string;
  week_end: string;
  total_promised: number;
  total_spent: number;
  promises: Record<string, PromiseData>;
}

export interface UserInfo {
  user_id: number;
  timezone: string;
  language: string;
}

export interface PublicUser {
  user_id: string;
  first_name?: string;
  last_name?: string;
  display_name?: string;
  username?: string;
  avatar_path?: string;
  avatar_file_unique_id?: string;
  activity_count: number;
  promise_count: number;
  last_seen_utc?: string;
}

export interface PublicUsersResponse {
  users: PublicUser[];
  total: number;
}

// Admin types
export interface AdminUser {
  user_id: string;
  first_name?: string;
  last_name?: string;
  username?: string;
  last_seen_utc?: string;
}

export interface AdminUsersResponse {
  users: AdminUser[];
  total: number;
}

export interface Broadcast {
  broadcast_id: string;
  admin_id: string;
  message: string;
  target_user_ids: number[];
  scheduled_time_utc: string;
  status: 'pending' | 'completed' | 'cancelled';
  created_at: string;
  updated_at: string;
}

export interface CreateBroadcastRequest {
  message: string;
  target_user_ids: number[];
  scheduled_time_utc?: string;
}

export interface UpdateBroadcastRequest {
  message?: string;
  target_user_ids?: number[];
  scheduled_time_utc?: string;
}

// Template types
export interface PromiseTemplate {
  template_id: string;
  category: string;
  program_key?: string;
  level: string;
  title: string;
  why: string;
  done: string;
  effort: string;
  template_kind: 'commitment' | 'budget';
  metric_type: 'hours' | 'count';
  target_value: number;
  target_direction: 'at_least' | 'at_most';
  estimated_hours_per_unit: number;
  duration_type: 'week' | 'one_time' | 'date';
  duration_weeks?: number;
  is_active: number;
  created_at_utc: string;
  updated_at_utc: string;
  unlocked?: boolean;
  lock_reason?: string;
}

export interface TemplatePrerequisite {
  prereq_id: string;
  template_id: string;
  prereq_group: number;
  kind: 'completed_template' | 'success_rate';
  required_template_id?: string;
  min_success_rate?: number;
  window_weeks?: number;
  created_at_utc: string;
}

export interface TemplateDetail extends PromiseTemplate {
  prerequisites: TemplatePrerequisite[];
}

export interface SubscribeTemplateRequest {
  start_date?: string;
  target_date?: string;
}

export interface SubscribeTemplateResponse {
  status: string;
  instance_id: string;
  promise_id: string;
  promise_uuid: string;
  start_date: string;
  end_date?: string;
}

export interface PromiseInstance {
  instance_id: string;
  user_id: string;
  template_id: string;
  promise_uuid: string;
  status: 'active' | 'completed' | 'abandoned';
  metric_type: 'hours' | 'count';
  target_value: number;
  estimated_hours_per_unit: number;
  start_date: string;
  end_date?: string;
  created_at_utc: string;
  updated_at_utc: string;
  title: string;
  category: string;
  template_kind: 'commitment' | 'budget';
  target_direction: 'at_least' | 'at_most';
}

export interface CheckinRequest {
  action_datetime?: string;
}

export interface WeeklyNoteRequest {
  week_start: string;
  note?: string;
}

export interface LogDistractionRequest {
  category: string;
  minutes: number;
  at_utc?: string;
}

export interface WeeklyDistractionsResponse {
  total_minutes: number;
  total_hours: number;
  event_count: number;
}

// Extended PromiseData to include metric fields
export interface PromiseData {
  text: string;
  hours_promised: number;
  hours_spent: number;
  sessions: SessionData[];
  visibility?: string;
  recurring?: boolean;
  metric_type?: 'hours' | 'count';
  target_value?: number;
  target_direction?: 'at_least' | 'at_most';
  template_kind?: 'commitment' | 'budget';
  achieved_value?: number;
}

// Extend Window interface for Telegram
declare global {
  interface Window {
    Telegram?: {
      WebApp: TelegramWebApp;
    };
  }
}

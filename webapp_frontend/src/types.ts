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

// Session and navigation UI contracts
export type SessionMode = 'telegram_mini_app' | 'browser_token' | 'unauthenticated';
export type AppNavKey = 'today' | 'community' | 'explore';

export interface AppNavItem {
  key: AppNavKey;
  label: string;
  to: string;
}

// API Response types
export interface SessionData {
  date: string;
  hours: number;
  notes?: string[];  // Optional array of notes for actions on this date
}

export interface PromiseData {
  text: string;
  hours_promised: number;
  hours_spent: number;
  sessions: SessionData[];
  visibility?: string; // "private" | "public"
  recurring?: boolean;
  start_date?: string; // ISO date string (YYYY-MM-DD)
  end_date?: string; // ISO date string (YYYY-MM-DD)
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
  first_name?: string;
  voice_mode?: string | null;
}

export interface PublicPromiseBadge {
  promise_id: string;
  text: string;
  hours_promised: number;
  hours_spent: number;
  weekly_hours: number;
  streak: number;
  progress_percentage: number;
  metric_type: string;
  target_value: number;
  achieved_value: number;
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
  weekly_activity_count?: number;
  last_activity_at_utc?: string;
  promise_count: number;
  last_seen_utc?: string;
  public_promises?: PublicPromiseBadge[];
}

export interface PublicUsersResponse {
  users: PublicUser[];
  total: number;
}

export interface PublicActivityActor {
  user_id: string;
  first_name?: string;
  last_name?: string;
  display_name?: string;
  username?: string;
  avatar_path?: string;
  avatar_file_unique_id?: string;
  weekly_activity_count?: number;
  last_activity_at_utc?: string;
}

export interface PublicActivityItem {
  activity_id: string;
  action_type: string;
  action_label: string;
  duration_minutes?: number;
  timestamp_utc: string;
  promise_id?: string;
  promise_text?: string;
  actor: PublicActivityActor;
}

export interface PublicActivityResponse {
  items: PublicActivityItem[];
  total: number;
}

// Admin types
export interface AdminUser {
  user_id: string;
  first_name?: string;
  last_name?: string;
  username?: string;
  last_seen_utc?: string;
  timezone?: string;
  language?: string;
  promise_count?: number;
  activity_count?: number;
}

export interface AdminUsersResponse {
  users: AdminUser[];
  total: number;
}

export interface ConversationMessage {
  id: number;
  user_id: string;
  chat_id?: string;
  message_id?: number;
  message_type: 'user' | 'bot';
  content: string;
  created_at_utc: string;
}

export interface ConversationResponse {
  messages: ConversationMessage[];
}

export interface Broadcast {
  broadcast_id: string;
  admin_id: string;
  message: string;
  target_user_ids: number[];
  scheduled_time_utc: string;
  status: 'pending' | 'completed' | 'cancelled';
  bot_token_id?: string;
  created_at: string;
  updated_at: string;
}

export interface CreateBroadcastRequest {
  message: string;
  target_user_ids: number[];
  scheduled_time_utc?: string;
  bot_token_id?: string;
  translate_to_user_language?: boolean;
  source_language?: string;
}

export interface BotToken {
  bot_token_id: string;
  bot_username?: string;
  is_active: boolean;
  description?: string;
  created_at_utc: string;
  updated_at_utc: string;
}

export interface UpdateBroadcastRequest {
  message?: string;
  target_user_ids?: number[];
  scheduled_time_utc?: string;
}

// Template types (simplified schema)
export interface PromiseTemplate {
  template_id: string;
  title: string;
  description?: string;
  category: string;
  target_value: number;
  metric_type: 'hours' | 'count';
  emoji?: string;
  created_by_user_id?: string;
  is_active: number;
  created_at_utc: string;
  updated_at_utc: string;
  unlocked?: boolean;
  lock_reason?: string;
}

// TemplateDetail is now just an alias for PromiseTemplate (simplified schema)
export type TemplateDetail = PromiseTemplate;

export interface SubscribeTemplateRequest {
  start_date?: string;
  target_date?: string;
  target_value?: number;
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

// Promise suggestion types
export interface PromiseSuggestion {
  suggestion_id: string;
  from_user_id: string;
  from_user_name?: string;
  to_user_id: string;
  to_user_name?: string;
  status: 'pending' | 'accepted' | 'declined' | 'cancelled';
  template_id?: string;
  draft_json?: string;
  message?: string;
  created_at_utc: string;
  responded_at_utc?: string;
}

export interface CreateSuggestionRequest {
  to_user_id: string;
  template_id?: string;
  freeform_text?: string;
  message?: string;
}

// Admin create promise types
export interface DayReminder {
  weekday: number; // 0-6 (Monday-Sunday)
  time: string; // HH:MM format
  enabled: boolean;
}

export interface CreatePromiseForUserRequest {
  target_user_id: number;
  text: string;
  hours_per_week: number;
  recurring?: boolean;
  start_date?: string; // ISO date string (YYYY-MM-DD)
  end_date?: string; // ISO date string (YYYY-MM-DD)
  visibility?: 'private' | 'followers' | 'clubs' | 'public';
  description?: string;
  reminders?: DayReminder[];
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
  start_date?: string; // ISO date string (YYYY-MM-DD)
  end_date?: string; // ISO date string (YYYY-MM-DD)
}

// Content consumption manager
export interface Content {
  id: string;
  canonical_url: string;
  original_url: string;
  provider: string;
  content_type: 'video' | 'audio' | 'text' | 'other';
  title?: string;
  description?: string;
  author_channel?: string;
  language?: string;
  published_at?: string;
  duration_seconds?: number;
  estimated_read_seconds?: number;
  thumbnail_url?: string;
  metadata_json?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface UserContent {
  id: string;
  user_id: string;
  content_id: string;
  status: 'saved' | 'in_progress' | 'completed' | 'archived';
  added_at: string;
  last_interaction_at?: string;
  completed_at?: string;
  last_position?: number;
  position_unit?: 'seconds' | 'ratio';
  progress_ratio?: number;
  total_consumed_seconds?: number;
  notes?: string;
  rating?: number;
}

export interface UserContentWithDetails extends Content, UserContent {
  user_content_id?: string;
  bucket_count?: number;
  buckets?: number[];
}

export interface HeatmapData {
  bucket_count: number;
  buckets: number[];
}

export interface ConsumeEventRequest {
  content_id: string;
  start_position: number;
  end_position: number;
  position_unit: 'seconds' | 'ratio';
  started_at?: string;
  ended_at?: string;
  client?: string;
}

export interface MyContentsResponse {
  items: UserContentWithDetails[];
  count: number;
}

// Focus Timer / Pomodoro types
export interface FocusSession {
  session_id: string;
  promise_id: string;
  promise_text?: string;
  status: 'running' | 'paused' | 'finished' | 'aborted';
  started_at: string; // ISO datetime
  expected_end_utc: string; // ISO datetime
  planned_duration_minutes: number;
  timer_kind: 'focus' | 'break';
  elapsed_seconds?: number; // Current elapsed time if running/paused
}

// -- Follow Graph (admin) -------------------------------------
export interface FollowGraphNode {
  id: string;
  username: string | null;
  first_name: string | null;
  follower_count: number;
  following_count: number;
}

export interface FollowGraphEdge {
  source: string;
  target: string;
}

export interface FollowGraphData {
  nodes: FollowGraphNode[];
  edges: FollowGraphEdge[];
  total_edges: number;
  total_nodes: number;
}

// Extend Window interface for Telegram
declare global {
  interface Window {
    Telegram?: {
      WebApp: TelegramWebApp;
    };
  }
}

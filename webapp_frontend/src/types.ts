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

// Extend Window interface for Telegram
declare global {
  interface Window {
    Telegram?: {
      WebApp: TelegramWebApp;
    };
  }
}

# TODO Implementations - ZanaAI Telegram Bot

This document lists all the incomplete implementations that need to be fixed in the refactored bot code.

## 🔧 Critical Issues to Fix

### 1. **Import Path Issues**
- **File:** `services/planner_api_adapter.py:138`
- **Issue:** `from schema import UserAction` should be `from llms.schema import UserAction`
- **Impact:** Runtime import error

### 2. **Language Code Error**
- **File:** `i18n/translations.py:14`
- **Issue:** Spanish language code is set to "fa" (Farsi) instead of "es" (Spanish)
- **Impact:** Incorrect language detection

## 🚧 Incomplete Implementations

### Message Handlers (`handlers/message_handlers.py`)

1. **Job Rescheduling** (Line 358)
   - `_reschedule_user_jobs()` method is empty
   - **TODO:** Implement timezone change job rescheduling

2. **Reminder Methods** (Lines 363, 370)
   - `send_nightly_reminders()` and `send_morning_reminders()` are empty
   - **TODO:** These methods are implemented in callback_handlers.py but not connected

### Callback Handlers (`handlers/callback_handlers.py`)

3. **Session Ticker System** (Lines 75, 80, 85)
   - `_schedule_session_ticker()` - empty implementation
   - `_stop_ticker()` - empty implementation  
   - `_schedule_session_resume()` - empty implementation
   - **TODO:** Implement real-time session timer updates

4. **Session Calculations** (Line 95)
   - `_session_effective_hours()` returns placeholder value (0.5)
   - **TODO:** Implement proper session time calculation

5. **Weekly Report Refresh** (Line 572)
   - `_handle_refresh_weekly()` - placeholder implementation
   - **TODO:** Implement actual weekly report refresh logic

6. **Timer Display** (Line 368)
   - `show_timer=True` parameter not implemented in `time_options_kb()`
   - **TODO:** Add timer display functionality to time options keyboard

### Bot Utilities (`utils/bot_utils.py`)

7. **Session Calculations** (Line 199)
   - `calculate_effective_hours()` returns placeholder value (0.5)
   - **TODO:** Implement proper session time calculation

### Internationalization (`i18n/translations.py`)

8. **User Language Preferences** (Line 463)
   - `get_user_language()` always returns default language
   - **TODO:** Implement user language preference storage in settings repository

### LLM Handler (`llms/llm_handler.py`)

9. **Chat History with System Messages** (Lines 86-89, 94-95)
   - System messages are commented out in chat history
   - **TODO:** Uncomment to enable proper context initialization

### Sessions Service (`services/sessions.py`)

10. **Session Recovery** (Line 113)
    - `recover_on_startup()` doesn't handle interrupted sessions
    - **TODO:** Implement logic to handle sessions that were running when bot went down

11. **Session Bump Functionality** (Line 129)
    - `bump()` method is empty
    - **TODO:** Implement adding additional time to sessions

12. **Session Peek** (Line 138)
    - `peek()` method is basic implementation
    - **TODO:** Enhance for display purposes

### UI Keyboards (`ui/keyboards.py`)

13. **Timer Display** (Line 70)
    - `show_timer` parameter added but not implemented
    - **TODO:** Implement timer display in time options keyboard

## 🎯 Priority Order

### High Priority (Critical for Basic Functionality)
1. Fix import path in `planner_api_adapter.py`
2. Fix Spanish language code in `translations.py`
3. Connect reminder methods between message_handlers and callback_handlers

### Medium Priority (Important Features)
4. Implement session ticker system
5. Implement proper session time calculations
6. Implement user language preferences
7. Implement weekly report refresh

### Low Priority (Nice to Have)
8. Implement session recovery on startup
9. Implement session bump functionality
10. Implement timer display in keyboards
11. Enable chat history with system messages

## 🔍 How to Find TODOs

Search for these patterns in the codebase:
- `# TODO:` - Main implementation todos
- `TODO: implement` - Specific implementation todos
- `TODO: Fix` - Bug fixes needed
- `placeholder` - Placeholder implementations
- `empty implementation` - Empty method bodies

## 📝 Notes

- All TODO items have been marked with clear comments
- Placeholder values (like 0.5 for session hours) are clearly marked
- Import issues are flagged with specific fix instructions
- Most functionality is working but some features are incomplete
- The bot should run with current implementation but some features will be limited

## 🚀 Next Steps

1. Fix critical import and language issues first
2. Implement session ticker system for real-time updates
3. Add proper session time calculations
4. Connect reminder methods properly
5. Implement user language preferences
6. Add remaining feature implementations

Each TODO item includes enough context to understand what needs to be implemented.

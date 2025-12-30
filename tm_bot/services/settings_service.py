"""Service for user settings operations."""
from repositories.settings_repo import SettingsRepository
from models.models import UserSettings


class SettingsService:
    """Service layer for user settings."""
    
    def __init__(self, settings_repo: SettingsRepository):
        self.settings_repo = settings_repo
    
    def get_settings(self, user_id: int) -> UserSettings:
        """Get user settings."""
        return self.settings_repo.get_settings(user_id)
    
    def save_settings(self, settings: UserSettings) -> None:
        """Save user settings."""
        self.settings_repo.save_settings(settings)
    
    def get_user_timezone(self, user_id: int) -> str:
        """Get user timezone."""
        settings = self.get_settings(user_id)
        return settings.timezone
    
    def set_user_timezone(self, user_id: int, tzname: str) -> None:
        """Set user timezone."""
        settings = self.get_settings(user_id)
        settings.timezone = tzname
        self.save_settings(settings)


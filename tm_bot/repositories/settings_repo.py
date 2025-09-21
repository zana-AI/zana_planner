import os
import json
from typing import Optional

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from models.models import UserSettings


class SettingsRepository:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def _get_file_path(self, user_id: int) -> str:
        """Get the settings file path for a user."""
        return os.path.join(self.root_dir, str(user_id), 'settings.yaml')

    def _ensure_user_dir(self, user_id: int) -> None:
        """Ensure user directory exists."""
        user_dir = os.path.join(self.root_dir, str(user_id))
        os.makedirs(user_dir, exist_ok=True)

    def get_settings(self, user_id: int) -> UserSettings:
        """Get user settings, creating defaults if not found."""
        file_path = self._get_file_path(user_id)
        
        if os.path.exists(file_path):
            try:
                if YAML_AVAILABLE:
                    with open(file_path, 'r') as f:
                        data = yaml.safe_load(f) or {}
                else:
                    # Fallback to JSON
                    with open(file_path, 'r') as f:
                        data = json.load(f) or {}
                
                return UserSettings(
                    user_id=user_id,
                    timezone=data.get('timezone', 'Europe/Paris'),
                    nightly_hh=data.get('nightly_hh', 22),
                    nightly_mm=data.get('nightly_mm', 0)
                )
            except Exception:
                pass
        
        # Return default settings if file doesn't exist or can't be read
        return UserSettings(user_id=user_id)

    def save_settings(self, settings: UserSettings) -> None:
        """Save user settings to YAML or JSON file."""
        self._ensure_user_dir(settings.user_id)
        
        file_path = self._get_file_path(settings.user_id)
        data = {
            'timezone': settings.timezone,
            'nightly_hh': settings.nightly_hh,
            'nightly_mm': settings.nightly_mm
        }
        
        with open(file_path, 'w') as f:
            if YAML_AVAILABLE:
                yaml.safe_dump(data, f)
            else:
                # Fallback to JSON
                json.dump(data, f, indent=2)

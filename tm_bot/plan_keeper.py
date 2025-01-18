import os
import csv
import yaml
from datetime import datetime


class PlanKeeper:
    def __init__(self, root_dir):
        self.root_dir = root_dir

    def _get_file_path(self, filename):
        """Helper to get full file path."""
        return os.path.join(self.root_dir, filename)

    def add_promise(self, promise_text, num_hours_promised_per_week, start_date, end_date, promise_angle, promise_radius):
        """
        Add a new promise to promises.csv.
        """
        promise_id = self._generate_promise_id(promise_text)
        promises_file = self._get_file_path('promises.csv')
        with open(promises_file, 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                promise_text,
                promise_id,
                num_hours_promised_per_week,
                start_date,
                end_date,
                promise_angle,
                promise_radius
            ])
        return f"Promise '{promise_text}' added successfully."

    def add_action(self, date, time, promise_id, time_spent):
        """
        Add an action to actions.csv.
        """
        actions_file = self._get_file_path('actions.csv')
        with open(actions_file, 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([date, time, promise_id, time_spent])
        return f"Action logged for promise ID '{promise_id}'."

    def update_setting(self, setting_key, setting_value):
        """
        Update a setting in settings.yaml.
        """
        settings_file = self._get_file_path('settings.yaml')
        if not os.path.exists(settings_file):
            settings = {}
        else:
            with open(settings_file, 'r') as file:
                settings = yaml.safe_load(file) or {}

        # Update the setting
        settings[setting_key] = setting_value
        with open(settings_file, 'w') as file:
            yaml.dump(settings, file)

        return f"Setting '{setting_key}' updated to '{setting_value}'."

    def _generate_promise_id(self, promise_text):
        """
        Generate a unique 12-character ID from the promise text.
        """
        return promise_text[:12].upper().replace(" ", "_")[:12]


# Example Usage
if __name__ == "__main__":
    ROOT_DIR = r'C:\Users\Mohamed CHETOUANI\Dropbox\Javad_plan\TEMP_USER_DIR'
    keeper = PlanKeeper(ROOT_DIR)

    # Simulated user message
    user_message = "I want to add a promise to read for 10 hours a week starting next Monday."
    result = keeper.process_message(user_message)
    print(result)

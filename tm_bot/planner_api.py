import os
import csv
import yaml
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from tqdm import tqdm


class PlannerAPI:
    def __init__(self, root_dir):
        if not os.path.exists(root_dir):
            raise FileNotFoundError(f"Root directory does not exist: {root_dir}")
        self.root_dir = root_dir

    def _get_file_path(self, filename, user_id):
        """Helper to get full file path."""
        try:
            path = os.path.join(self.root_dir, str(user_id), filename)
            if not os.path.exists(os.path.dirname(path)):
                raise FileNotFoundError(f"User directory does not exist for user_id: {user_id}")
            return path
        except Exception as e:
            raise FileNotFoundError(f"Error accessing file path: {str(e)}")

    def add_promise(self,
                    user_id,
                    promise_text: str,
                    num_hours_promised_per_week: float,
                    start_date: Optional[datetime] = None,
                    end_date: Optional[datetime] = None,
                    promise_angle_deg: int = 0,
                    promise_radius: Optional[int] = 0
                    ):
        """
        Add a new promise to promises.json.
        """
        try:
            # Validate inputs
            if not promise_text or not isinstance(promise_text, str):
                raise ValueError("Promise text must be a non-empty string")
            if not isinstance(num_hours_promised_per_week, (int, float)) or num_hours_promised_per_week <= 0:
                raise ValueError("Hours promised must be a positive number")

            promise_id = self._generate_promise_id(promise_text)
            promises_file = self._get_file_path('promises.json', user_id)

            if not start_date:
                start_date = datetime.now().date()
            if not end_date: # end of the current year
                end_date = datetime(datetime.now().year, 12, 31).date()

            # Load existing promises
            if os.path.exists(promises_file):
                with open(promises_file, 'r') as file:
                    promises = json.load(file)
            else:
                promises = []

            # Create new promise object
            new_promise = {
                'id': promise_id,
                'text': promise_text.replace(" ", "_"),
                'hours_per_week': num_hours_promised_per_week,
                'start_date': str(start_date),
                'end_date': str(end_date),
                'angle_deg': promise_angle_deg,
                'radius': promise_radius
            }

            promises.append(new_promise)

            # Save updated promises
            with open(promises_file, 'w') as file:
                json.dump(promises, file, indent=4)

            return f"Promise '{promise_text}' added successfully."

        except (ValueError, FileNotFoundError) as e:
            # logger.error(f"Error in add_promise: {str(e)}")
            raise RuntimeError(f"Failed to add promise: {str(e)}")

    def add_action(self, user_id, date: datetime, time: str, promise_id: str, time_spent: float):
        """
        Add an action to actions.csv.
        """
        actions_file = self._get_file_path('actions.csv', user_id)
        with open(actions_file, 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([date, time, promise_id, time_spent])
        return f"Action logged for promise ID '{promise_id}'."

    def get_promises(self, user_id) -> List[Dict]:
        """Get all promises from promises.json."""
        promises_file = self._get_file_path('promises.json', user_id)
        if not os.path.exists(promises_file):
            return []
        with open(promises_file, 'r') as file:
            promises = json.load(file)
        return promises

    def get_promise_hours(self, user_id, promise_id: str) -> Optional[float]:
        """
        Get the number of hours promised per week for a specific promise.
        """
        promises_file = self._get_file_path('promises.json', user_id)

        if not os.path.exists(promises_file):
            return None

        with open(promises_file, 'r') as file:
            promises = json.load(file)

        for promise in promises:
            if promise['id'] == promise_id:
                return promise.get('hours_per_week')

        return None

    def get_actions(self, user_id):
        """Get all actions from actions.csv."""
        actions_file = self._get_file_path('actions.csv', user_id)
        with open(actions_file, 'r') as file:
            reader = csv.reader(file)
            actions = [row for row in reader]
        return actions

    def delete_promise(self, user_id, promise_id: str):
        """Delete a promise from promises.json."""
        promises_file = self._get_file_path('promises.json', user_id)

        if not os.path.exists(promises_file):
            return f"No promises file found for user '{user_id}'"

        with open(promises_file, 'r') as file:
            promises = json.load(file)

        # Filter out the promise to delete and set a flag if found
        promise_found = False
        updated_promises = []
        for promise in promises:
            if promise['id'] == promise_id:
                promise_found = True
            else:
                updated_promises.append(promise)

        if not promise_found:
            return f"Promise with ID '{promise_id}' not found."

        with open(promises_file, 'w') as file:
            json.dump(updated_promises, file, indent=4)

        return f"Promise with ID '{promise_id}' deleted successfully."

    def update_setting(self, user_id, setting_key, setting_value):
        """
        Update a setting in settings.yaml.
        """
        settings_file = self._get_file_path('settings.yaml', user_id)
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

    # def _generate_promise_id(self, promise_text):
    #     """
    #     Generate a unique 12-character ID from the promise text.
    #     """
    #     return promise_text[:12].upper().replace(" ", "_")[:12]
    def _generate_promise_id(self, user_id):
        """Generate a unique ID for the promise."""
        promises = self.get_promises(user_id)
        promise_count = len(promises) + 1
        return f"P{promise_count:02d}"

    def delete_action(self, user_id, date: datetime, promise_id: str):
        """
        Delete an action from actions.csv.
        """
        actions_file = self._get_file_path('actions.csv', user_id)
        updated_actions = []

        with open(actions_file, 'r') as file:
            reader = csv.reader(file)
            for row in reader:
                if not (row[0] == date and row[2] == promise_id):  # Keep all actions except the one to delete
                    updated_actions.append(row)

        with open(actions_file, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerows(updated_actions)

        return f"Action for promise ID '{promise_id}' on date '{date}' deleted successfully."

    def get_weekly_report(self, user_id):
        """
        Generate a weekly report of promises and actions.
        """
        promises = self.get_promises(user_id)
        actions = self.get_actions(user_id)

        # Initialize report data
        report_data = {promise['id']: {'text': promise['text'], 'hours_promised': promise['hours_per_week'], 'hours_spent': 0} for promise in promises}

        # Calculate hours spent for each promise
        one_week_ago = datetime.now() - timedelta(days=7)
        for action in actions:
            action_date = datetime.strptime(action[0], '%Y-%m-%d')
            if action_date >= one_week_ago:
                promise_id = action[2]
                time_spent = float(action[3])
                if promise_id in report_data:
                    report_data[promise_id]['hours_spent'] += time_spent

        # Generate report
        report_lines = []
        for promise_id, data in report_data.items():
            hours_promised = data['hours_promised']
            hours_spent = data['hours_spent']
            progress = min(100, int((hours_spent / hours_promised) * 100)) if hours_promised > 0 else 0
            progress_bar = tqdm(total=100, ncols=50, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}').format_dict['bar_format']
            report_lines.append(f"Promise: {data['text'].replace('_', ' ')}\nProgress: {progress_bar.format(l_bar='', bar='█' * (progress // 2), n_fmt=progress, total_fmt='100')} {progress}%\n")

        return "\n".join(report_lines)

    def delete_all_promises(self, user_id):
        """Delete all promises for a user."""
        promises_file = self._get_file_path('promises.json', user_id)
        if os.path.exists(promises_file):
            os.remove(promises_file)
        return "All promises deleted successfully."

# Example Usage
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    ROOT_DIR = os.getenv("ROOT_DIR")
    keeper = PlannerAPI(ROOT_DIR)

    user_id = "test_user"
    result = keeper.get_promises(user_id)

    print(result)

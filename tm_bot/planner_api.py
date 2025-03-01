import os
import csv
import yaml
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import pandas as pd
from schema import UserAction


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
                    recurring: bool = False,
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

            if recurring:
                promise_type = 'P'
            else:
                promise_type = 'T'

            promise_id = self._generate_promise_id(user_id=user_id, promise_type=promise_type)
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
                'recurring': recurring,
                'start_date': str(start_date),
                'end_date': str(end_date),
                'angle_deg': promise_angle_deg,
                'radius': promise_radius
            }

            promises.append(new_promise)

            # Save updated promises
            with open(promises_file, 'w') as file:
                json.dump(promises, file, indent=4)

            return f"#{promise_id} Promise '{promise_text}' added successfully."

        except (ValueError, FileNotFoundError) as e:
            # logger.error(f"Error in add_promise: {str(e)}")
            raise RuntimeError(f"Failed to add promise: {str(e)}")

    def add_action(self, user_id, promise_id: str, time_spent: float) -> str:
        """
        Add an action to actions.csv.
        Args:
           - user_id: The ID of the user.
           - promise_id: The ID of the promise.
           - time_spent: The amount of time spent on the action.
        Returns: A message indicating the success or failure of the action addition.
        """
        # Validate the promise ID
        promises = self.get_promises(user_id)
        if not any(p['id'] == promise_id for p in promises):
            return f"Promise with ID '{promise_id}' not found."

        if time_spent <= 0:
            return "Time spent must be a positive number."

        actions_file = self._get_file_path('actions.csv', user_id)
        date = datetime.now().date()
        time = datetime.now().strftime("%H:%M:%S")
        with open(actions_file, 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([date, time, promise_id, time_spent])
        return f"Action logged for promise ID '{promise_id}'."

    def get_promise_weekly_progress(self, user_id, promise_id: str) -> float:
        """
        Get the weekly progress of a promise.
        """
        promises = self.get_promises(user_id)
        actions_df = self.get_actions_df(user_id)

        try:
            actions_df['date'] = pd.to_datetime(actions_df['date']).dt.date
            actions_df['time'] = pd.to_datetime(actions_df['time']).dt.time
            actions_df['datetime'] = pd.to_datetime(actions_df['date'].astype(str) + ' ' + actions_df['time'].astype(str))
            actions_df['time_spent'] = actions_df['time_spent'].astype(float)
        except Exception as e:
            pass

        # Get the promise details
        promise = next((p for p in promises if p['id'] == promise_id), None)
        if not promise:
            #return f"Promise with ID '{promise_id}' not found."
            return 0.

        # Extract promised hours per week
        promise_hours_per_week = promise['hours_per_week']

        # Calculate the current week's start and end (Monday at 3 AM)
        now = datetime.now() - timedelta(hours=3)
        current_week_start = (now - timedelta(days=now.weekday()))
        current_week_end = current_week_start + timedelta(days=7) - timedelta(seconds=1)

        # filter actions for the current week
        current_week_actions = actions_df[
                        (actions_df['datetime'] >= current_week_start) &
                        (actions_df['datetime'] <= current_week_end) &
                        (actions_df['promise_id'] == promise_id)
        ]
        current_week_hours_spent = current_week_actions['time_spent'].sum()

        progress_this_week = round(current_week_hours_spent / (promise_hours_per_week + 1e-6), 2)
        return progress_this_week

    def get_promises(self, user_id) -> List[Dict]:
        """Get all promises from promises.json."""
        promises_file = self._get_file_path('promises.json', user_id)
        if not os.path.exists(promises_file):
            return []
        with open(promises_file, 'r') as file:
            promises = json.load(file)
        for p in promises:
            if 'recurring' not in p:
                p['recurring'] = p['id'].startswith('P')
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

    def get_actions_df(self, user_id) -> pd.DataFrame:
        """Get all actions from actions.csv as a pandas dataframe."""
        actions_file = self._get_file_path('actions.csv', user_id)
        if not os.path.exists(actions_file):
            return pd.DataFrame(columns=['date', 'time', 'promise_id', 'time_spent'])
        df = pd.read_csv(actions_file, names=['date', 'time', 'promise_id', 'time_spent'])
        df['time'] = pd.to_datetime(df['time'], errors='coerce', infer_datetime_format=True).dt.strftime("%H:%M:%S")
        return df

    def get_last_action_on_promise(self, user_id, promise_id: str) -> Optional[UserAction]:
        """
        Get the last action for a specific promise by considering both date and time.
        """
        actions = self.get_actions_df(user_id)
        if actions.empty:
            return None

        # Helper to parse a combined date-time string.
        def parse_dt(dt_str):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    return datetime.strptime(dt_str, fmt)
                except ValueError:
                    continue
            raise ValueError(f"Unrecognized datetime format: {dt_str}")

        # Create a new 'datetime' column by combining the 'date' and 'time' columns.
        combined = actions['date'] + ' ' + actions['time']
        actions['datetime'] = combined.apply(parse_dt)

        # Filter actions for the given promise_id and sort by the combined datetime column.
        last_action = actions[actions['promise_id'] == promise_id].sort_values('datetime', ascending=False).head(1)
        if last_action.empty:
            return None
        return UserAction(
            action_date=last_action['date'].values[0],
            action_time=last_action['time'].values[0],
            promise_id=last_action['promise_id'].values[0],
            time_spent=last_action['time_spent'].values[0]
        )

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

        return f"Promise #{promise_id} deleted successfully."

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

    def _generate_promise_id(self, user_id, promise_type='P'):
        """Generate a unique ID for the promise."""
        last_id = 0
        promises = self.get_promises(user_id)
        if promises:
            try:
                promise_ids = [p['id'] for p in promises if p['id'].startswith(promise_type)]
                numeric_ids = [int(p_id[1:]) for p_id in promise_ids]
                last_id = sorted(numeric_ids)[-1]
            except Exception as e:
                pass
        return f"{promise_type}{(last_id+1):02d}"

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

    def get_weekly_report(self, user_id, reference_time=None):
        """
        Generate a weekly report of promises and actions.
        Only includes actions from the current week (starting Monday at 3:00 AM)
        based on the provided reference_time (or current time if None).
        """

        if reference_time is None:
            reference_time = datetime.now()
        now = reference_time

        # Compute the current week’s Monday at 3:00 AM.
        monday = now - timedelta(days=now.weekday())
        week_start = monday.replace(hour=3, minute=0, second=0, microsecond=0)
        # If the current time is before Monday 3 AM (e.g., early Monday), use the previous Monday.
        if now < week_start:
            week_start = week_start - timedelta(days=7)

        promises = self.get_promises(user_id)
        actions_df = self.get_actions_df(user_id)

        # Initialize report data.
        report_data = {
            promise['id']: {
                'text': promise['text'],
                'hours_promised': promise['hours_per_week'],
                'hours_spent': 0
            }
            for promise in promises
        }

        # Create a datetime column by combining date and time.
        # errors='coerce' converts unparseable rows to NaT.
        actions_df['datetime'] = pd.to_datetime(
            actions_df['date'] + ' ' + actions_df['time'],
            errors='coerce', infer_datetime_format=True
        )

        # Drop rows with unparseable datetime.
        actions_df = actions_df.dropna(subset=['datetime'])

        # Ensure time_spent is numeric.
        actions_df['time_spent'] = pd.to_numeric(actions_df['time_spent'], errors='coerce').fillna(0)

        # Filter actions between week_start and now.
        filtered_actions = actions_df[(actions_df['datetime'] >= week_start) & (actions_df['datetime'] <= now)]

        # Accumulate hours for each promise.
        for _, row in filtered_actions.iterrows():
            promise_id = row['promise_id']
            time_spent = float(row['time_spent'])
            if promise_id in report_data:
                report_data[promise_id]['hours_spent'] += time_spent

        # Build the report text.
        report_lines = []
        for promise_id, data in report_data.items():
            hours_promised = data['hours_promised']
            hours_spent = data['hours_spent']
            progress = min(100, int((hours_spent / hours_promised) * 100)) if hours_promised > 0 else 0

            bar_width = 10
            filled_length = (progress * bar_width) // 100
            empty_length = bar_width - filled_length
            progress_bar = f"{'█' * filled_length}{'_' * empty_length}"

            # Determine the diamond emoji based on progress
            if progress < 30:
                diamond = "🔴"  # Red warning # diamond = "🔺"
            elif progress < 60:
                diamond = "🟠"
            elif progress < 90:
                diamond = "🟡"
            else:
                diamond = "✅"  # Green check

            report_lines.append(
                f"{diamond} #{promise_id} **{data['text'][:36].replace('_', ' ')}**:\n"
                f" └──`[{progress_bar}] {progress:2d}%` ({hours_spent:.1f}/{hours_promised:.1f} h)"
            )

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

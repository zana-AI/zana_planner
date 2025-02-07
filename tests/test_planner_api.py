import os
import sys
import json
import csv
import shutil
import tempfile
import time
import unittest
import random

import pandas as pd
from datetime import datetime, timedelta, date

import yaml
tm_bot_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tm_bot"))
sys.path.append(tm_bot_dir)
from planner_api import PlannerAPI


# ---------------------------
# TEST SUITE WITH RANDOM 8-DIGIT USER ID
# ---------------------------
class TestPlannerAPI(unittest.TestCase):
    def setUp(self):
        # Generate a random 8-digit user id as a string
        self.user_id = str(random.randint(10 ** 7, 10 ** 8 - 1))
        # Create a temporary directory to serve as the root directory.
        self.temp_dir = tempfile.mkdtemp()
        # Create a subdirectory for the user.
        self.user_dir = os.path.join(self.temp_dir, self.user_id)
        os.makedirs(self.user_dir, exist_ok=True)
        # Initialize the PlannerAPI with the temporary directory.
        self.planner = PlannerAPI(self.temp_dir)
        # Explanation:
        # Here we ensure that each test works in isolation with its own random user.

    def tearDown(self):
        # Clean up the temporary directory after each test.
        shutil.rmtree(self.temp_dir)

    def test_init_invalid_directory(self):
        # Test that initializing with a non-existent directory raises an error.
        with self.assertRaises(FileNotFoundError):
            PlannerAPI("non_existent_directory")

    def test_get_file_path_valid(self):
        # Verify that _get_file_path returns the correct path.
        file_path = self.planner._get_file_path("promises.json", self.user_id)
        expected = os.path.join(self.temp_dir, self.user_id, "promises.json")
        self.assertEqual(file_path, expected)

    def test_get_file_path_invalid_user_directory(self):
        # Test that accessing a file for a user with no directory raises an error.
        with self.assertRaises(FileNotFoundError):
            self.planner._get_file_path("promises.json", "00000000")

    def test_add_promise_valid(self):
        # Add a promise and verify that it's correctly stored.
        result = self.planner.add_promise(
            self.user_id,
            promise_text="Test Promise",
            num_hours_promised_per_week=5.0,
            recurring=True
        )
        self.assertIn("Promise 'Test Promise' added successfully", result)
        # Check that the promise was written to promises.json.
        promises_file = self.planner._get_file_path("promises.json", self.user_id)
        with open(promises_file, 'r') as f:
            promises = json.load(f)
        self.assertEqual(len(promises), 1)
        self.assertEqual(promises[0]['text'], "Test_Promise")

    def test_add_promise_invalid_text(self):
        # An empty promise text should trigger a RuntimeError.
        with self.assertRaises(RuntimeError):
            self.planner.add_promise(self.user_id, "", 5.0)

    def test_add_promise_invalid_hours(self):
        # Non-positive hours should trigger a RuntimeError.
        with self.assertRaises(RuntimeError):
            self.planner.add_promise(self.user_id, "Valid Text", -3)

    def test_add_action_valid(self):
        # Add a promise first so that we can then add an action.
        add_result = self.planner.add_promise(self.user_id, "Action Test", 10.0)
        # Extract promise_id from the response.
        promise_id = add_result.split()[0].lstrip("#")
        result = self.planner.add_action(self.user_id, promise_id, 2.5)
        self.assertIn("Action logged for promise ID", result)
        # Verify that the action is appended to actions.csv.
        actions_file = self.planner._get_file_path("actions.csv", self.user_id)
        with open(actions_file, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], promise_id)

    def test_add_action_invalid_promise(self):
        # Attempt to add an action for a non-existent promise.
        result = self.planner.add_action(self.user_id, "NON_EXISTENT", 2.0)
        self.assertEqual(result, "Promise with ID 'NON_EXISTENT' not found.")

    def test_add_action_invalid_time_spent(self):
        # Add a promise and then try to add an action with negative time spent.
        add_result = self.planner.add_promise(self.user_id, "Invalid Time", 10.0)
        promise_id = add_result.split()[0].lstrip("#")
        result = self.planner.add_action(self.user_id, promise_id, -1)
        self.assertEqual(result, "Time spent must be a positive number.")

    def test_get_promise_weekly_progress(self):
        # Add a promise and log an action; then verify weekly progress.
        add_result = self.planner.add_promise(self.user_id, "Weekly Progress", 10.0)
        promise_id = add_result.split()[0].lstrip("#")
        self.planner.add_action(self.user_id, promise_id, 5.0)
        progress = self.planner.get_promise_weekly_progress(self.user_id, promise_id)
        # With 5 hours logged and 10 promised, progress should be 0.5 (or 50%).
        self.assertAlmostEqual(progress, 0.5, places=2)

    def test_get_promises_empty(self):
        # If promises.json does not exist, get_promises should return an empty list.
        promises_file = os.path.join(self.user_dir, "promises.json")
        if os.path.exists(promises_file):
            os.remove(promises_file)
        promises = self.planner.get_promises(self.user_id)
        self.assertEqual(promises, [])

    def test_get_promise_hours(self):
        # Add a promise and then verify the hours promised are returned correctly.
        add_result = self.planner.add_promise(self.user_id, "Hours Test", 7.5)
        promise_id = add_result.split()[0].lstrip("#")
        hours = self.planner.get_promise_hours(self.user_id, promise_id)
        self.assertEqual(hours, 7.5)

    def test_get_actions(self):
        # After logging an action, verify that get_actions returns it.
        add_result = self.planner.add_promise(self.user_id, "Actions Test", 10.0)
        promise_id = add_result.split()[0].lstrip("#")
        self.planner.add_action(self.user_id, promise_id, 3.0)
        actions = self.planner.get_actions(self.user_id)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0][2], promise_id)

    def test_get_actions_df(self):
        # Check that get_actions_df returns a proper DataFrame.
        actions_df = self.planner.get_actions_df(self.user_id)
        self.assertTrue(isinstance(actions_df, pd.DataFrame))
        self.assertListEqual(list(actions_df.columns), ['date', 'time', 'promise_id', 'time_spent'])

    def test_get_last_action_on_promise(self):
        # Add a promise, log two actions, and then ensure the last action is retrieved.
        add_result = self.planner.add_promise(self.user_id, "Last Action", 10.0)
        promise_id = add_result.split()[0].lstrip("#")
        self.planner.add_action(self.user_id, promise_id, 2.0)
        time.sleep(2)  # Ensure the second action has a later timestamp.
        self.planner.add_action(self.user_id, promise_id, 4.0)
        last_action = self.planner.get_last_action_on_promise(self.user_id, promise_id)
        self.assertIsNotNone(last_action)
        self.assertAlmostEqual(float(last_action.time_spent), 4.0, places=1)

    def test_delete_promise(self):
        # Add a promise and then delete it.
        add_result = self.planner.add_promise(self.user_id, "Delete Me", 10.0)
        promise_id = add_result.split()[0].lstrip("#")
        del_result = self.planner.delete_promise(self.user_id, promise_id)
        self.assertIn("deleted successfully", del_result)
        promises = self.planner.get_promises(self.user_id)
        self.assertFalse(any(p['id'] == promise_id for p in promises))

    def test_update_setting(self):
        # Update a setting and verify that the setting is stored in settings.yaml.
        result = self.planner.update_setting(self.user_id, "theme", "dark")
        self.assertIn("Setting 'theme' updated to 'dark'", result)
        settings_file = self.planner._get_file_path("settings.yaml", self.user_id)
        with open(settings_file, 'r') as f:
            settings = yaml.safe_load(f)
        self.assertEqual(settings.get("theme"), "dark")

    def test_delete_action(self):
        # Add an action, then delete it and verify that the action file is updated.
        add_result = self.planner.add_promise(self.user_id, "Delete Action", 10.0)
        promise_id = add_result.split()[0].lstrip("#")
        self.planner.add_action(self.user_id, promise_id, 3.0)
        actions_file = self.planner._get_file_path("actions.csv", self.user_id)
        with open(actions_file, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
        self.assertEqual(len(rows), 1)
        action_date_str = rows[0][0]
        del_result = self.planner.delete_action(self.user_id, action_date_str, promise_id)
        self.assertIn("deleted successfully", del_result)
        with open(actions_file, 'r') as f:
            reader = csv.reader(f)
            rows_after = list(reader)
        self.assertEqual(len(rows_after), 0)

    def test_get_weekly_report(self):
        # Add a promise and an action, then generate and check the weekly report.
        add_result = self.planner.add_promise(self.user_id, "Report Test", 8.0)
        promise_id = add_result.split()[0].lstrip("#")
        self.planner.add_action(self.user_id, promise_id, 4.0)
        report = self.planner.get_weekly_report(self.user_id)
        self.assertIn(f"#{promise_id}", report)
        self.assertIn("Report Test", report)

    def test_delete_all_promises(self):
        # Add a promise, verify the promises file exists, then delete all promises.
        self.planner.add_promise(self.user_id, "Promise 1", 5.0)
        promises_file = self.planner._get_file_path("promises.json", self.user_id)
        self.assertTrue(os.path.exists(promises_file))
        del_result = self.planner.delete_all_promises(self.user_id)
        self.assertIn("All promises deleted successfully", del_result)
        self.assertFalse(os.path.exists(promises_file))


if __name__ == '__main__':
    unittest.main()
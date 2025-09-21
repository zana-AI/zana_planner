import os
import time
from datetime import datetime, timedelta
from services.planner_api_adapter import PlannerAPIAdapter

def nightly(user_id: str, num_promises: int = 3):
    """
    Nightly function to remind the user about their promises.
    
    Args:
        user_id (str): The ID of the user.
        num_promises (int): The number of promises to remind the user about.
    """
    # Initialize the PlannerAPI
    root_dir = os.getenv("ROOT_DIR")
    planner_api = PlannerAPIAdapter(root_dir)

    # Get the user's promises
    promises = planner_api.get_promises(user_id)

    # Select N promises to remind the user about
    promises_to_remind = promises[:num_promises]

    # Ask the user about each promise one by one
    for promise in promises_to_remind:
        promise_id = promise[0]
        promise_text = promise[1].replace("_", " ")  # Replace underscores with spaces for readability
        print(f"Reminder: {promise_text}")

        # Here you can implement the logic to send a message to the user
        # For example, using a Telegram bot or any other messaging service
        # await update.message.reply_text(f"Reminder: {promise_text}")

        # Wait for a response from the user (this is a placeholder)
        time.sleep(5)  # Simulate waiting for user response

    print("All reminders sent.")

# Example usage
if __name__ == "__main__":
    user_id = "user123"  # Replace with actual user ID
    nightly(user_id) 
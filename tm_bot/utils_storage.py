import os
import csv
import yaml

def create_user_directory(root_dir, user_id: int) -> bool:
    """Create a directory for the user if it doesn't exist and initialize files."""
    user_dir = os.path.join(root_dir, str(user_id))
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
        initialize_files(user_dir)
        return True
    return False

def initialize_files(user_dir: str) -> None:
    """Initialize the required files in the user's directory."""
    promises_file = os.path.join(user_dir, 'promises.csv')
    actions_file = os.path.join(user_dir, 'actions.csv')
    settings_file = os.path.join(user_dir, 'settings.yaml')

    # Create promises.csv and actions.csv with headers
    for file_path in [promises_file, actions_file]:
        with open(file_path, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['id', 'content'])  # Example headers, adjust as needed

    # Create settings.yaml with default settings
    default_settings = {'setting1': 'value1', 'setting2': 'value2'}  # Example settings, adjust as needed
    with open(settings_file, 'w') as file:
        yaml.dump(default_settings, file)
# llm_env_utils.py
import os
import base64
import tempfile
from dotenv import load_dotenv

def load_llm_env():
    """
    Loads environment variables from .env and prepares credentials for Vertex AI.
    Returns a dict with project, location, and model.
    """
    load_dotenv()  # ensure .env is loaded

    openai_key = os.getenv("OPENAI_API_KEY", "")
    # if not self.openai_key:
    #     raise ValueError("OpenAI API key is not set in environment variables.")

    project_id = os.getenv("GCP_PROJECT_ID")
    location   = os.getenv("GCP_LOCATION", "us-central1")
    model_name = os.getenv("GCP_GEMINI_MODEL", "gemini-2.5-flash")

    if not project_id:
        raise ValueError("GCP_PROJECT_ID is missing in .env")
    if not location:
        raise ValueError("GCP_LOCATION is missing in .env")

    # Handle base64 JSON credentials
    creds_b64 = os.getenv("GCP_CREDENTIALS_B64")
    if not creds_b64:
        raise ValueError("GCP_CREDENTIALS_B64 is missing in .env")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    tmp.write(base64.b64decode(creds_b64))
    tmp.close()
    # os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"E:\workspace\ZanaAI\zana_planner\demo_features\vertex-access.json"

    return {
        "GCP_PROJECT_ID": project_id,
        "GCP_LOCATION": location,
        "GCP_GEMINI_MODEL": model_name,
        "OPENAI_API_KEY": openai_key
    }

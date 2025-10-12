from llm_env_utils import load_llm_env
from google import genai

cfg = load_llm_env()

PROJECT_ID = cfg["GCP_PROJECT_ID"]
LOCATION   = "us-central1"

client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

resp = client.models.generate_content(
    model="gemini-2.5-flash",   # or "gemini-1.5-pro"
    contents="Say hi from Gemini on GCP!"
)
print(resp.text)

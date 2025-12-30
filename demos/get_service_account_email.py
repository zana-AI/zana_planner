"""
Quick script to extract service account email from GCP credentials.
This helps you get the correct email for IAM role binding commands.
"""

import os
import json
import base64
from dotenv import load_dotenv

load_dotenv()

creds_b64 = os.getenv("GCP_CREDENTIALS_B64")
if not creds_b64:
    print("ERROR: GCP_CREDENTIALS_B64 not found in .env")
    exit(1)

# Decode credentials
creds_json = json.loads(base64.b64decode(creds_b64))
service_account_email = creds_json.get("client_email")

if not service_account_email:
    print("ERROR: client_email not found in credentials")
    exit(1)

project_id = os.getenv("GCP_PROJECT_ID", "YOUR_PROJECT_ID")

print("=" * 60)
print("Service Account Email:")
print(f"  {service_account_email}")
print()
print("gcloud command to add Cloud Trace Agent role:")
print("=" * 60)
print(f'gcloud projects add-iam-policy-binding {project_id} \\')
print(f'  --member="serviceAccount:{service_account_email}" \\')
print(f'  --role="roles/cloudtrace.agent"')
print("=" * 60)



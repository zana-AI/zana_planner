# pip install google-cloud-translate==3.*
from google.cloud import translate_v3 as translate
import os

from llms.llm_env_utils import load_llm_env

cfg = load_llm_env()

project_id = cfg.get("GCP_PROJECT_ID")
location   = cfg.get("GCP_LOCATION", "us-central1")

def translate_text_gcp(text: str, target: str, source: str | None = None,
                       project_id: str = project_id,
                       location: str = location,  # or "us-central1", "europe-west1", etc.
                       glossary_id: str | None = None,
                       mime_type: str = "text/plain") -> str:
    client = translate.TranslationServiceClient()
    parent = f"projects/{project_id}/locations/{location}"

    # Optional glossary config
    glossary_config = None
    if glossary_id:
        glossary_config = translate.TranslateTextGlossaryConfig(
            glossary=f"{parent}/glossaries/{glossary_id}"
        )

    request = translate.TranslateTextRequest(
        contents=[text],
        target_language_code=target,
        source_language_code=source or "",
        parent=parent,
        mime_type=mime_type,  # "text/plain" or "text/html"
        glossary_config=glossary_config
    )

    response = client.translate_text(request=request)
    # If a glossary was applied, preferred text is in glossary_translations
    if glossary_config and response.glossary_translations:
        return response.glossary_translations[0].translated_text
    return response.translations[0].translated_text

if __name__ == "__main__":
    text = "Hello, world!"
    target = "es"
    source = "en"
    print(translate_text_gcp(text, target, source))

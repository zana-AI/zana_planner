"""
Demo script for Persian (fa-IR) text-to-speech using Gemini TTS via Cloud Text-to-Speech API.

Uses the same API as Vertex AI Gemini TTS (model gemini-2.5-flash-tts) but via
google.cloud.texttospeech, which works without vertexai.preview SpeechConfig/VoiceConfig.

Usage:
    python demos/demo_tts_gcp.py

Requirements (in .env):
    - GCP_PROJECT_ID
    - GCP_CREDENTIALS_B64 (base64-encoded service account JSON)
    - GCP_LOCATION (optional, default: us-central1)

Requires: google-cloud-texttospeech >= 2.29.0 (for Gemini TTS model_name).

Input:
    demos/demo_tts_input.txt — text to synthesize (UTF-8).

Output:
    demos/persian_gemini_tts.mp3 — play this file to hear the synthesized speech.
"""

import sys
from pathlib import Path

# Add project root so we can import from tm_bot
sys.path.insert(0, str(Path(__file__).parent.parent))

from tm_bot.llms.llm_env_utils import load_llm_env
from google.cloud import texttospeech

# Load GCP credentials from .env (sets GOOGLE_APPLICATION_CREDENTIALS)
load_llm_env()

# Input text file next to this script (UTF-8)
INPUT_TXT = Path(__file__).parent / "demo_tts_input.txt"


def main():
    # Read text to synthesize from the txt file next to this script
    if not INPUT_TXT.is_file():
        raise FileNotFoundError(f"Input file not found: {INPUT_TXT}. Create it with UTF-8 text to speak.")
    text = INPUT_TXT.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Input file is empty: {INPUT_TXT}")

    # Cloud Text-to-Speech client (uses same credentials as Vertex)
    client = texttospeech.TextToSpeechClient()

    # Input: text and optional prompt for style (each max 4000 bytes)
    synthesis_input = texttospeech.SynthesisInput(
        text=text,
        prompt="Say the following clearly and naturally.",
    )
    # Gemini 2.5 Flash TTS with Persian (fa-IR) and Studio voice Achernar
    voice = texttospeech.VoiceSelectionParams(
        language_code="fa-IR",
        name="Achernar",
        model_name="gemini-2.5-flash-tts",
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )

    out_path = Path(__file__).parent / "persian_gemini_tts.mp3"
    out_path.write_bytes(response.audio_content)
    print(f"Persian TTS written to: {out_path}")
    print(f"Text ({len(text)} chars): {text[:80]}{'...' if len(text) > 80 else ''}")


# ---------------------------------------------------------------------------
# Alternative: Google Cloud Text-to-Speech API (list voices + synthesize).
# Uncomment and use this if you prefer the classic Cloud TTS instead of Gemini.
# ---------------------------------------------------------------------------
# from google.cloud import texttospeech
#
# def main():
#     client = texttospeech.TextToSpeechClient()
#
#     # List available fa-IR voices (Google may change/retire voice names)
#     voices_response = client.list_voices(language_code="fa-IR")
#     if not voices_response.voices:
#         raise RuntimeError("No Persian (fa-IR) voices found in Cloud TTS.")
#     voice_info = None
#     for v in voices_response.voices:
#         if v.ssml_gender == texttospeech.SsmlVoiceGender.FEMALE:
#             voice_info = v
#             break
#     if voice_info is None:
#         voice_info = voices_response.voices[0]
#     voice_name = voice_info.name
#     language_code = voice_info.language_codes[0] if voice_info.language_codes else "fa-IR"
#     print(f"Using voice: {voice_name} ({language_code})")
#
#     synthesis_input = texttospeech.SynthesisInput(text=PERSIAN_TEXT)
#     voice = texttospeech.VoiceSelectionParams(
#         language_code=language_code,
#         name=voice_name,
#         ssml_gender=voice_info.ssml_gender,
#     )
#     audio_config = texttospeech.AudioConfig(
#         audio_encoding=texttospeech.AudioEncoding.OGG_OPUS,
#     )
#     response = client.synthesize_speech(
#         input=synthesis_input, voice=voice, audio_config=audio_config,
#     )
#
#     out_path = Path(__file__).parent / "demo_tts_output.ogg"
#     out_path.write_bytes(response.audio_content)
#     print(f"Persian TTS written to: {out_path}")
#     print(f"Text: {PERSIAN_TEXT}")


if __name__ == "__main__":
    main()

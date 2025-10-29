# image_vlm_parser.py
from typing import Literal
from pydantic import BaseModel
from langchain_google_vertexai import ChatVertexAI
from langchain.schema import HumanMessage
from llms.llm_env_utils import load_llm_env

AllowedType = Literal[
    "screenshot","photo","document","whiteboard","slide","chart",
    "receipt","form","id","business_card","meme","other"
]
AllowedApp = Literal[
    "email","whatsapp","telegram","slack","discord","sms","browser","twitter_x",
    "linkedin","youtube","calendar","maps","pdf_viewer","doc_editor","sheet",
    "presentation","ide","terminal","file_manager","settings","camera","gallery","null"
]

class Meta(BaseModel):
    language: str = "unknown"   # ← not Optional
    confidence: float = 0.0     # ← not Optional

class VLMOutput(BaseModel):
    type: AllowedType
    is_screenshot: bool
    app: AllowedApp
    caption: str
    text: str
    meta: Meta

    @classmethod
    def prompt(cls) -> str:
        return (
            "You are a vision-language parser. Produce ONLY the fields of the schema exactly.\n"
            "Fields: type, is_screenshot, app, caption, text, meta.language, meta.confidence.\n"
            "- type ∈ {screenshot, photo, document, whiteboard, slide, chart, receipt, form, id, business_card, meme, other}\n"
            "- app ∈ {email, whatsapp, telegram, slack, discord, sms, browser, twitter_x, linkedin, youtube, calendar, maps, "
            "pdf_viewer, doc_editor, sheet, presentation, ide, terminal, file_manager, settings, camera, gallery, null}\n"
            "- If not a screenshot, set app=\"null\".\n"
            "- caption ≤ 15 words. text = all visible text (truncate ~1200 chars). Do not invent.\n"
            "- meta.language is ISO 639-1 or \"unknown\". meta.confidence ∈ [0,1]."
        )

class ImageVLMParser:
    def __init__(self):
        env = load_llm_env()
        base = ChatVertexAI(
            model=env["GCP_GEMINI_MODEL"],
            project=env["GCP_PROJECT_ID"],
            location=env["GCP_LOCATION"],
            temperature=0.1,
        )
        self.llm_struct = base.with_structured_output(VLMOutput)

    def parse(self, image_url: str) -> VLMOutput:
        msg = [HumanMessage(content=[
            {"type": "text", "text": VLMOutput.prompt()},
            {"type": "image_url", "image_url": {"url": image_url}},
        ])]
        return self.llm_struct.invoke(msg)


# main.py
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

parser = ImageVLMParser()

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    f = await (m.photo[-1].get_file() if m.photo else m.document.get_file())
    out = parser.parse(f.file_path)  # VLMOutput instance
    await m.reply_text(out.model_dump_json(indent=2, ensure_ascii=False)[:4000])

if __name__ == "__main__":
    load_dotenv()
    app = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()
    app.add_handler(MessageHandler(filters.PHOTO | (filters.Document.IMAGE), handle_image))
    print("🤖 Bot running...")
    app.run_polling()

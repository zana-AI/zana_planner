"""
Image processing service using Vision Language Model (VLM) for text extraction and analysis.
"""

import base64
from typing import Literal, Optional
from pathlib import Path
from pydantic import BaseModel

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from llms.llm_env_utils import load_llm_env
from utils.logger import get_logger

logger = get_logger(__name__)

# Type definitions
AllowedType = Literal[
    "screenshot", "photo", "document", "whiteboard", "slide", "chart",
    "receipt", "form", "id", "business_card", "meme", "other"
]

AllowedApp = Literal[
    "email", "whatsapp", "telegram", "slack", "discord", "sms", "browser", "twitter_x",
    "linkedin", "youtube", "calendar", "maps", "pdf_viewer", "doc_editor", "sheet",
    "presentation", "ide", "terminal", "file_manager", "settings", "camera", "gallery", "null"
]


class ImageMeta(BaseModel):
    """Metadata about the image."""
    language: str = "unknown"
    confidence: float = 0.0


class ImageAnalysisOutput(BaseModel):
    """Output from image analysis."""
    type: AllowedType
    is_screenshot: bool
    app: AllowedApp
    caption: str
    text: str
    meta: ImageMeta

    @classmethod
    def get_analysis_prompt(cls) -> str:
        """Get the prompt for image analysis."""
        return (
            "You are a vision-language parser that extracts and analyzes content from images.\n"
            "Extract ALL visible text, including handwritten notes, printed text, diagrams, and any other content.\n\n"
            "Produce ONLY the fields of the schema exactly:\n"
            "- type: Categorize the image type (screenshot, photo, document, whiteboard, slide, chart, receipt, form, id, business_card, meme, other)\n"
            "- is_screenshot: true if this appears to be a screenshot, false otherwise\n"
            "- app: If it's a screenshot, identify the app (email, whatsapp, telegram, slack, discord, sms, browser, twitter_x, linkedin, youtube, calendar, maps, pdf_viewer, doc_editor, sheet, presentation, ide, terminal, file_manager, settings, camera, gallery). Otherwise set to 'null'\n"
            "- caption: A brief descriptive caption (2-3 sentences) summarizing what the image contains\n"
            "- text: Extract ALL visible text content from the image. Include:\n"
            "  * All handwritten text (preserve original language)\n"
            "  * All printed text\n"
            "  * Text from diagrams, charts, or visual elements\n"
            "  * Lists, bullet points, numbered items\n"
            "  * Preserve structure and formatting where possible\n"
            "  * Do NOT truncate - include everything you can read\n"
            "- meta.language: Detect the primary language(s) used (ISO 639-1 codes, comma-separated if multiple)\n"
            "- meta.confidence: Your confidence in the text extraction (0.0 to 1.0)\n\n"
            "Be thorough and extract as much context as possible. If the image contains notes, tasks, or planning content, preserve all details."
        )


class ImageService:
    """Service for processing images with Vision Language Model."""
    
    def __init__(self):
        try:
            env = load_llm_env()
            base = ChatGoogleGenerativeAI(
                model=env["GCP_GEMINI_MODEL"],
                project=env["GCP_PROJECT_ID"],
                location=env.get("GCP_LLM_LOCATION", env["GCP_LOCATION"]),
                temperature=0.1,
            )
            self.llm_struct = base.with_structured_output(ImageAnalysisOutput)
            logger.info("ImageService initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ImageService: {str(e)}")
            raise
    
    def _encode_image_to_base64(self, image_path: str) -> str:
        """Encode image file to base64 string."""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to encode image to base64: {str(e)}")
            raise
    
    def _get_image_mime_type(self, image_path: str) -> str:
        """Detect MIME type from file extension."""
        path = Path(image_path)
        ext = path.suffix.lower()
        mime_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
        }
        return mime_map.get(ext, 'image/jpeg')
    
    def parse_image(self, image_path: str, image_url: Optional[str] = None) -> ImageAnalysisOutput:
        """
        Parse image to extract text and context.
        
        Args:
            image_path: Local path to the image file
            image_url: Optional URL to the image (preferred if available)
        
        Returns:
            ImageAnalysisOutput with extracted text and metadata
        """
        try:
            # Prefer URL if available (for Telegram files)
            if image_url:
                logger.debug(f"Parsing image from URL: {image_url}")
                image_content = {
                    "type": "image_url",
                    "image_url": {"url": image_url}
                }
            else:
                # Encode local file to base64
                logger.debug(f"Parsing local image file: {image_path}")
                base64_image = self._encode_image_to_base64(image_path)
                mime_type = self._get_image_mime_type(image_path)
                image_content = {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_image}"
                    }
                }
            
            # Create message with prompt and image
            message = HumanMessage(content=[
                {"type": "text", "text": ImageAnalysisOutput.get_analysis_prompt()},
                image_content,
            ])
            
            # Invoke LLM for analysis
            result = self.llm_struct.invoke([message])
            
            logger.info(f"Image parsed successfully. Type: {result.type}, Text length: {len(result.text)}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to parse image: {str(e)}")
            raise
    
    def extract_text_for_processing(self, analysis: ImageAnalysisOutput) -> str:
        """
        Extract and format text from analysis for further processing.
        
        Args:
            analysis: ImageAnalysisOutput from parse_image
        
        Returns:
            Formatted text string ready for LLM processing
        """
        parts = []
        
        # Add caption for context
        if analysis.caption:
            parts.append(f"Image context: {analysis.caption}")
        
        # Add extracted text
        if analysis.text:
            parts.append(f"\nExtracted content:\n{analysis.text}")
        
        # Add metadata if useful
        if analysis.meta.language and analysis.meta.language != "unknown":
            parts.append(f"\nDetected language(s): {analysis.meta.language}")
        
        return "\n".join(parts).strip()

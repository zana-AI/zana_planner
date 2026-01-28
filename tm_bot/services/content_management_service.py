"""
Service for managing user content: processing links, summarizing content, and formatting summaries.
"""
from typing import Optional, Dict, Any

from services.content_service import ContentService
from services.time_estimation_service import TimeEstimationService
from utils.logger import get_logger

logger = get_logger(__name__)


class ContentManagementService:
    """Service for managing user content operations."""
    
    def __init__(
        self,
        content_service: ContentService,
        time_estimation_service: TimeEstimationService
    ):
        self.content_service = content_service
        self.time_estimation_service = time_estimation_service
        self._llm_handler = None
    
    def set_llm_handler(self, llm_handler):
        """Set LLM handler for content summarization."""
        self._llm_handler = llm_handler
    
    def process_shared_link(self, user_id: int, url: str) -> str:
        """
        Process a shared link and return formatted summary with time estimate.
        
        Args:
            user_id: User ID
            url: URL to process
        
        Returns:
            Formatted string with link summary and time estimate
        """
        try:
            # Process the link to extract metadata
            link_metadata = self.content_service.process_link(url)
            
            # Estimate time needed
            estimated_duration = self.time_estimation_service.estimate_content_duration(
                link_metadata, user_id
            )
            
            # Format duration string
            duration_str = self._format_duration(estimated_duration)
            
            # Generate summary
            title = link_metadata.get('title', 'Content')
            description = link_metadata.get('description', 'No description available')
            url_type = link_metadata.get('type', 'unknown')
            
            summary = (
                f"📄 *{title}*\n\n"
                f"{description[:300]}{'...' if len(description) > 300 else ''}\n\n"
                f"⏱ Estimated time: {duration_str}\n"
                f"🔗 Type: {url_type}"
            )
            
            return summary
        
        except Exception as e:
            logger.error(f"Error processing link {url}: {str(e)}")
            return f"Error processing link: {str(e)}"
    
    def summarize_content(
        self,
        user_id: int,
        url: str,
        content_metadata: Dict[str, Any]
    ) -> str:
        """
        Summarize content using LLM.
        
        Args:
            user_id: User ID
            url: URL of the content
            content_metadata: Content metadata dict with title, description, type, etc.
        
        Returns:
            Summary string
        """
        try:
            content_type = content_metadata.get('type', 'unknown')
            title = content_metadata.get('title', 'Content')
            description = content_metadata.get('description', '')
            metadata = content_metadata.get('metadata', {})
            
            # For blogs/articles, try to get full content using Trafilatura if available
            full_content = None
            if content_type == 'blog' or content_type == 'unknown':
                try:
                    import trafilatura
                    downloaded = trafilatura.fetch_url(url)
                    if downloaded:
                        extracted = trafilatura.extract(
                            downloaded,
                            include_comments=False,
                            include_tables=False,
                            include_images=False,
                            include_links=False
                        )
                        if extracted and len(extracted) > len(description):
                            full_content = extracted
                except Exception:
                    pass  # Fallback to description
            
            # Build content text for summarization
            content_text = f"Title: {title}\n\n"
            
            if content_type == 'youtube':
                # For YouTube, use description and subtitles if available
                if description:
                    content_text += f"Description: {description}\n\n"
                if metadata.get('has_subtitles'):
                    content_text += "Note: This video has subtitles available.\n\n"
                content_text += f"Video URL: {url}"
            else:
                # For blogs/articles, use full content if available, otherwise description
                if full_content:
                    # Use full content but limit length for LLM
                    content_text += f"Content: {full_content[:3000]}\n\n"  # Limit to 3000 chars
                    if len(full_content) > 3000:
                        content_text += "[Content truncated...]\n\n"
                elif description:
                    content_text += f"Content: {description}\n\n"
                content_text += f"Article URL: {url}"
            
            # Build summarization prompt
            prompt = f"""Please provide a concise summary of the following content:

{content_text}

Provide a summary that:
- Captures the main points and key ideas
- Is 2-4 sentences long
- Helps the reader decide if they want to consume the full content
- Is clear and informative

Summary:"""
            
            # Call LLM
            if self._llm_handler:
                user_id_str = str(user_id)
                summary = self._llm_handler.get_response_custom(prompt, user_id_str)
                return summary
            else:
                # Fallback: return a basic summary from description
                if description:
                    # Take first 200 characters as summary
                    return description[:200] + ("..." if len(description) > 200 else "")
                return f"Summary of: {title}"
        
        except Exception as e:
            logger.error(f"Error summarizing content: {str(e)}")
            return f"Unable to generate summary. Error: {str(e)}"
    
    def estimate_time_for_content(
        self,
        user_id: int,
        content_type: str,
        metadata: Dict[str, Any]
    ) -> float:
        """
        Estimate time needed for content.
        
        Args:
            user_id: User ID
            content_type: Type of content (blog, youtube, podcast, etc.)
            metadata: Content metadata dict
        
        Returns:
            Estimated duration in hours
        """
        try:
            content_metadata = {
                'type': content_type,
                **metadata
            }
            return self.time_estimation_service.estimate_content_duration(content_metadata, user_id)
        except Exception as e:
            logger.warning(f"Error estimating time for content: {str(e)}")
            # Return default estimate on error
            if content_type == 'youtube':
                return 0.17  # ~10 minutes
            elif content_type == 'blog':
                return 0.08  # ~5 minutes
            elif content_type == 'podcast':
                return 0.5  # 30 minutes
            return 0.25  # 15 minutes default
    
    def get_work_hour_suggestion(
        self,
        user_id: int,
        day_of_week: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get work hour suggestion based on user patterns.
        
        Args:
            user_id: User ID
            day_of_week: Optional day name (e.g., 'Monday'). If None, uses current day.
        
        Returns:
            Dict with suggested_hours, day_of_week, reasoning, and patterns
        """
        try:
            return self.time_estimation_service.suggest_daily_work_hours(
                user_id, day_of_week, self._llm_handler
            )
        except Exception as e:
            logger.error(f"Error getting work hour suggestion: {str(e)}")
            return {
                'suggested_hours': 0.0,
                'day_of_week': day_of_week or 'Unknown',
                'reasoning': f'Error: {str(e)}',
                'patterns': {}
            }
    
    def _format_duration(self, duration_hours: Optional[float]) -> str:
        """Format duration in hours to a human-readable string."""
        if not duration_hours:
            return "Unknown"
        
        if duration_hours < 1.0:
            minutes = int(duration_hours * 60)
            return f"{minutes} minutes"
        else:
            hours = int(duration_hours)
            minutes = int((duration_hours - hours) * 60)
            if minutes > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{hours} hour{'s' if hours > 1 else ''}"

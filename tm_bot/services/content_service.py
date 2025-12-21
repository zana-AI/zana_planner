"""
Content processing service for extracting metadata from URLs.
Supports blogs, YouTube videos, podcasts, and other content types.
"""
import re
from typing import Dict, Optional, List
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False

from utils.logger import get_logger

logger = get_logger(__name__)

# URL pattern for detection
URL_PATTERN = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
)


class ContentService:
    """Service for processing and extracting metadata from URLs."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def detect_urls(self, text: str) -> List[str]:
        """Detect all URLs in a text string."""
        return URL_PATTERN.findall(text)
    
    def detect_url_type(self, url: str) -> str:
        """Detect the type of content from URL."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # YouTube
        if 'youtube.com' in domain or 'youtu.be' in domain:
            return 'youtube'
        
        # Podcast platforms
        if any(p in domain for p in ['spotify.com', 'apple.com/podcasts', 'podcasts.google.com', 'anchor.fm']):
            return 'podcast'
        
        # Blog/article platforms
        if any(p in domain for p in ['medium.com', 'substack.com', 'dev.to', 'hashnode.com']):
            return 'blog'
        
        # Generic blog/article (most websites)
        return 'blog'
    
    def process_link(self, url: str) -> Dict[str, any]:
        """
        Process a URL and extract metadata.
        
        Returns:
            Dict with keys: title, description, duration (in hours), url, type, metadata
        """
        try:
            url_type = self.detect_url_type(url)
            logger.info(f"Processing {url_type} link: {url}")
            
            if url_type == 'youtube':
                return self._process_youtube(url)
            elif url_type == 'podcast':
                return self._process_podcast(url)
            else:
                return self._process_blog(url)
        
        except Exception as e:
            logger.error(f"Error processing link {url}: {str(e)}")
            return {
                'title': 'Unknown Content',
                'description': f'Failed to process link: {str(e)}',
                'duration': None,
                'url': url,
                'type': 'unknown',
                'metadata': {}
            }
    
    def _process_youtube(self, url: str) -> Dict[str, any]:
        """Extract metadata from YouTube video."""
        if not YT_DLP_AVAILABLE:
            logger.warning("yt-dlp not available, falling back to basic extraction")
            return self._process_youtube_basic(url)
        
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                title = info.get('title', 'YouTube Video')
                description = info.get('description', '')[:500]  # Limit description length
                duration_seconds = info.get('duration', 0)
                duration_hours = duration_seconds / 3600.0 if duration_seconds else None
                
                # Try to get subtitles
                subtitles = {}
                if 'subtitles' in info:
                    subtitles = info['subtitles']
                elif 'automatic_captions' in info:
                    subtitles = info['automatic_captions']
                
                # Extract subtitle text if available
                subtitle_text = None
                if subtitles:
                    # Try to get English subtitles first
                    for lang in ['en', 'en-US', 'en-GB']:
                        if lang in subtitles:
                            subtitle_url = subtitles[lang][0].get('url', '')
                            if subtitle_url:
                                try:
                                    sub_response = self.session.get(subtitle_url, timeout=5)
                                    if sub_response.status_code == 200:
                                        # Parse WebVTT or similar format
                                        subtitle_text = sub_response.text[:1000]  # Limit length
                                        break
                                except Exception:
                                    pass
                
                return {
                    'title': title,
                    'description': description or subtitle_text or 'No description available',
                    'duration': duration_hours,
                    'url': url,
                    'type': 'youtube',
                    'metadata': {
                        'duration_seconds': duration_seconds,
                        'channel': info.get('uploader', ''),
                        'view_count': info.get('view_count', 0),
                        'has_subtitles': bool(subtitles)
                    }
                }
        
        except Exception as e:
            logger.error(f"Error extracting YouTube metadata with yt-dlp: {str(e)}")
            return self._process_youtube_basic(url)
    
    def _process_youtube_basic(self, url: str) -> Dict[str, any]:
        """Fallback method for YouTube when yt-dlp is not available."""
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                title_tag = soup.find('meta', property='og:title')
                title = title_tag.get('content', 'YouTube Video') if title_tag else 'YouTube Video'
                
                desc_tag = soup.find('meta', property='og:description')
                description = desc_tag.get('content', '') if desc_tag else ''
                
                return {
                    'title': title,
                    'description': description[:500],
                    'duration': None,  # Can't extract duration without yt-dlp
                    'url': url,
                    'type': 'youtube',
                    'metadata': {}
                }
        except Exception as e:
            logger.error(f"Error in basic YouTube extraction: {str(e)}")
        
        return {
            'title': 'YouTube Video',
            'description': 'Unable to extract video information',
            'duration': None,
            'url': url,
            'type': 'youtube',
            'metadata': {}
        }
    
    def _process_blog(self, url: str) -> Dict[str, any]:
        """Extract metadata from blog/article URL."""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try to get title from various meta tags
            title = None
            for tag in ['og:title', 'twitter:title']:
                meta = soup.find('meta', property=tag) or soup.find('meta', attrs={'name': tag})
                if meta:
                    title = meta.get('content', '')
                    break
            
            # Fallback to <title> tag
            if not title:
                title_tag = soup.find('title')
                title = title_tag.get_text(strip=True) if title_tag else 'Article'
            
            # Try to get description
            description = None
            for tag in ['og:description', 'twitter:description', 'description']:
                meta = soup.find('meta', property=tag) or soup.find('meta', attrs={'name': tag})
                if meta:
                    description = meta.get('content', '')
                    break
            
            # Fallback: try to extract main content
            if not description:
                # Try common article content selectors
                for selector in ['article', '.post-content', '.article-content', 'main', '[role="article"]']:
                    content = soup.select_one(selector)
                    if content:
                        # Get text and limit length
                        description = content.get_text(strip=True)[:500]
                        break
            
            # Estimate reading time (average reading speed: 200-250 words per minute)
            word_count = len(description.split()) if description else 0
            reading_time_hours = (word_count / 200) / 60.0  # Convert minutes to hours
            
            return {
                'title': title[:200],  # Limit title length
                'description': description[:500] if description else 'No description available',
                'duration': reading_time_hours if reading_time_hours > 0 else None,
                'url': url,
                'type': 'blog',
                'metadata': {
                    'word_count': word_count,
                    'estimated_reading_minutes': int((word_count / 200) + 0.5) if word_count > 0 else None
                }
            }
        
        except requests.RequestException as e:
            logger.error(f"Error fetching blog URL {url}: {str(e)}")
            return {
                'title': 'Article',
                'description': f'Unable to fetch content: {str(e)}',
                'duration': None,
                'url': url,
                'type': 'blog',
                'metadata': {}
            }
        except Exception as e:
            logger.error(f"Error processing blog URL {url}: {str(e)}")
            return {
                'title': 'Article',
                'description': f'Error processing link: {str(e)}',
                'duration': None,
                'url': url,
                'type': 'blog',
                'metadata': {}
            }
    
    def _process_podcast(self, url: str) -> Dict[str, any]:
        """Extract metadata from podcast URL."""
        # For now, treat podcasts similar to blogs
        # Future: could parse RSS feeds or use podcast APIs
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try to get title
            title = None
            for tag in ['og:title', 'twitter:title']:
                meta = soup.find('meta', property=tag) or soup.find('meta', attrs={'name': tag})
                if meta:
                    title = meta.get('content', '')
                    break
            
            if not title:
                title_tag = soup.find('title')
                title = title_tag.get_text(strip=True) if title_tag else 'Podcast'
            
            # Try to get description
            description = None
            for tag in ['og:description', 'twitter:description']:
                meta = soup.find('meta', property=tag) or soup.find('meta', attrs={'name': tag})
                if meta:
                    description = meta.get('content', '')
                    break
            
            # For podcasts, duration might be in metadata or we estimate
            duration = None
            
            return {
                'title': title[:200],
                'description': description[:500] if description else 'Podcast episode',
                'duration': duration,
                'url': url,
                'type': 'podcast',
                'metadata': {}
            }
        
        except Exception as e:
            logger.error(f"Error processing podcast URL {url}: {str(e)}")
            return {
                'title': 'Podcast',
                'description': f'Unable to fetch podcast information: {str(e)}',
                'duration': None,
                'url': url,
                'type': 'podcast',
                'metadata': {}
            }

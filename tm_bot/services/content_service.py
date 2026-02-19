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

try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False

try:
    import podcastparser
    PODCASTPARSER_AVAILABLE = True
except ImportError:
    PODCASTPARSER_AVAILABLE = False

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
        path = parsed.path.lower()
        
        # YouTube
        if 'youtube.com' in domain or 'youtu.be' in domain:
            return 'youtube'
        
        # Podcast platforms
        if any(p in domain for p in ['spotify.com', 'apple.com/podcasts', 'podcasts.google.com', 'anchor.fm']):
            return 'podcast'
        
        # Substack article (has /p/ in path)
        if 'substack.com' in domain and '/p/' in path:
            return 'substack_article'
        
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
            elif url_type == 'substack_article':
                return self._process_substack_article(url)
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
        """Extract metadata from YouTube video via youtube_utils (single source of truth)."""
        try:
            from utils.youtube_utils import get_video_info, extract_video_id
            video_id = extract_video_id(url)
            if not video_id:
                return self._process_youtube_basic(url)
            info = get_video_info(video_id, url=url)
            duration_seconds = info.get("duration_seconds")
            duration_hours = duration_seconds / 3600.0 if duration_seconds else None
            description = (info.get("description_snippet") or "")[:500] or "No description available"
            return {
                "title": info.get("title") or "YouTube Video",
                "description": description,
                "duration": duration_hours,
                "url": url,
                "type": "youtube",
                "metadata": {
                    "duration_seconds": duration_seconds or 0,
                    "channel": info.get("channel") or "",
                    "view_count": info.get("view_count") or 0,
                    "has_subtitles": info.get("captions_available", False),
                },
            }
        except Exception as e:
            logger.error(f"Error extracting YouTube metadata: {str(e)}")
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
    
    def _process_substack_article(self, url: str) -> Dict[str, any]:
        """Extract metadata from Substack article URL."""
        try:
            # Try Trafilatura first for better extraction
            if TRAFILATURA_AVAILABLE:
                try:
                    downloaded = trafilatura.fetch_url(url)
                    if downloaded:
                        extracted = trafilatura.extract(
                            downloaded,
                            include_comments=False,
                            include_tables=False,
                            include_images=False,
                            include_links=False
                        )
                        if extracted:
                            metadata = trafilatura.extract_metadata(downloaded)
                            
                            title = metadata.title if metadata and metadata.title else None
                            description = extracted[:500] if extracted else None
                            author = metadata.author if metadata and metadata.author else None
                            date = metadata.date if metadata and metadata.date else None
                            
                            # If we got good content, use it
                            if description and len(description) > 100:
                                word_count = len(extracted.split())
                                reading_time_hours = (word_count / 200) / 60.0
                                
                                return {
                                    'title': (title or 'Substack Article')[:200],
                                    'description': description[:500],
                                    'duration': reading_time_hours if reading_time_hours > 0 else None,
                                    'url': url,
                                    'type': 'blog',
                                    'metadata': {
                                        'word_count': word_count,
                                        'estimated_reading_minutes': int((word_count / 200) + 0.5) if word_count > 0 else None,
                                        'author': author,
                                        'date': date.isoformat() if date else None
                                    }
                                }
                except Exception as e:
                    logger.warning(f"Trafilatura extraction failed for {url}: {str(e)}, falling back to BeautifulSoup")
            
            # Fallback to BeautifulSoup
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
                title = title_tag.get_text(strip=True) if title_tag else 'Substack Article'
            
            # Try to get description
            description = None
            for tag in ['og:description', 'twitter:description', 'description']:
                meta = soup.find('meta', property=tag) or soup.find('meta', attrs={'name': tag})
                if meta:
                    description = meta.get('content', '')
                    break
            
            # Try Substack-specific selectors for content
            if not description:
                # Substack-specific selectors
                substack_selectors = [
                    'article[data-testid="post-content"]',
                    '.post-content',
                    '.pencraft',
                    '[data-testid="post-content"]',
                    'article .pencraft',
                    '.pencraft-text',
                    'div[class*="post-content"]',
                    'div[class*="pencraft"]'
                ]
                
                for selector in substack_selectors:
                    try:
                        content = soup.select_one(selector)
                        if content:
                            description = content.get_text(strip=True)
                            if description and len(description) > 50:  # Ensure we got meaningful content
                                break
                    except Exception:
                        continue
            
            # Fallback: try to extract from meta description and estimate based on title
            if not description or len(description.strip()) < 50:
                # If we have a title, estimate based on it
                if title and len(title) > 20:
                    # Estimate: longer titles suggest longer articles
                    estimated_words = len(title.split()) * 50  # Rough estimate
                    description = f"{title}. Article content not fully accessible."
                else:
                    description = "Substack article content not fully accessible."
            
            # Estimate reading time (average reading speed: 200-250 words per minute)
            word_count = len(description.split()) if description else 0
            
            # If word count is very low, try to estimate from title length
            if word_count < 20 and title:
                # Estimate based on title length - longer titles often indicate longer articles
                title_words = len(title.split())
                # Conservative estimate: assume at least 200 words for a Substack article
                word_count = max(200, title_words * 30)
                logger.info(f"Substack article: low word count, estimated {word_count} words from title")
            
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
            logger.error(f"Error fetching Substack article URL {url}: {str(e)}")
            return {
                'title': 'Substack Article',
                'description': f'Unable to fetch content: {str(e)}',
                'duration': None,
                'url': url,
                'type': 'blog',
                'metadata': {}
            }
        except Exception as e:
            logger.error(f"Error processing Substack article URL {url}: {str(e)}")
            return {
                'title': 'Substack Article',
                'description': f'Error processing link: {str(e)}',
                'duration': None,
                'url': url,
                'type': 'blog',
                'metadata': {}
            }
    
    def _process_blog(self, url: str) -> Dict[str, any]:
        """Extract metadata from blog/article URL."""
        try:
            # Try Trafilatura first for better extraction
            if TRAFILATURA_AVAILABLE:
                try:
                    downloaded = trafilatura.fetch_url(url)
                    if downloaded:
                        extracted = trafilatura.extract(
                            downloaded,
                            include_comments=False,
                            include_tables=False,
                            include_images=False,
                            include_links=False
                        )
                        if extracted:
                            metadata = trafilatura.extract_metadata(downloaded)
                            
                            title = metadata.title if metadata and metadata.title else None
                            description = extracted[:500] if extracted else None
                            author = metadata.author if metadata and metadata.author else None
                            date = metadata.date if metadata and metadata.date else None
                            
                            # If we got good content, use it
                            if description and len(description) > 50:
                                word_count = len(extracted.split())
                                reading_time_hours = (word_count / 200) / 60.0
                                
                                return {
                                    'title': (title or 'Article')[:200],
                                    'description': description[:500],
                                    'duration': reading_time_hours if reading_time_hours > 0 else None,
                                    'url': url,
                                    'type': 'blog',
                                    'metadata': {
                                        'word_count': word_count,
                                        'estimated_reading_minutes': int((word_count / 200) + 0.5) if word_count > 0 else None,
                                        'author': author,
                                        'date': date.isoformat() if date else None
                                    }
                                }
                except Exception as e:
                    logger.warning(f"Trafilatura extraction failed for {url}: {str(e)}, falling back to BeautifulSoup")
            
            # Fallback to BeautifulSoup
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
        try:
            # Try to find RSS feed URL if this is a podcast platform page
            # For Spotify, Apple Podcasts, etc., we might need to extract RSS feed URL first
            rss_url = None
            
            # Check if URL is already an RSS feed
            if url.endswith('.xml') or 'rss' in url.lower() or 'feed' in url.lower():
                rss_url = url
            else:
                # Try to find RSS feed link on the page
                try:
                    response = self.session.get(url, timeout=10)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Look for RSS feed links
                    rss_link = soup.find('link', type='application/rss+xml') or \
                              soup.find('link', type='application/atom+xml') or \
                              soup.find('a', href=re.compile(r'\.(rss|xml|feed)'))
                    
                    if rss_link:
                        rss_url = rss_link.get('href') or rss_link.get('href')
                        if rss_url and not rss_url.startswith('http'):
                            from urllib.parse import urljoin
                            rss_url = urljoin(url, rss_url)
                except Exception as e:
                    logger.debug(f"Could not find RSS feed for {url}: {str(e)}")
            
            # If we have an RSS feed URL, use podcastparser
            if rss_url and PODCASTPARSER_AVAILABLE:
                try:
                    feed_response = self.session.get(rss_url, timeout=10)
                    feed_response.raise_for_status()
                    
                    # podcastparser.parse expects a file-like object
                    import io
                    feed_file = io.BytesIO(feed_response.content)
                    feed = podcastparser.parse(rss_url, feed_file)
                    
                    if feed:
                        title = feed.get('title', 'Podcast')
                        description = feed.get('description', '')
                        
                        # Try to find the specific episode if URL points to one
                        episodes = feed.get('episodes', [])
                        episode = None
                        if episodes:
                            # Try to match URL with episode
                            for ep in episodes:
                                if url in ep.get('link', '') or url in ep.get('enclosures', [{}])[0].get('url', ''):
                                    episode = ep
                                    break
                            
                            # If no match, use latest episode
                            if not episode and episodes:
                                episode = episodes[0]
                        
                        if episode:
                            title = episode.get('title', title)
                            description = episode.get('description', description)
                            duration_seconds = episode.get('total_time', 0)
                            duration_hours = duration_seconds / 3600.0 if duration_seconds else None
                        else:
                            duration_hours = None
                        
                        return {
                            'title': title[:200],
                            'description': description[:500] if description else 'Podcast episode',
                            'duration': duration_hours,
                            'url': url,
                            'type': 'podcast',
                            'metadata': {
                                'feed_title': feed.get('title'),
                                'episode_count': len(episodes) if episodes else 0
                            }
                        }
                except Exception as e:
                    logger.warning(f"Podcastparser failed for {rss_url}: {str(e)}, falling back to HTML parsing")
            
            # Fallback to HTML parsing (for podcast platform pages)
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

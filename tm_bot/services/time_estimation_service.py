"""
Time estimation service using LLMs to estimate content duration
and analyze user work patterns to suggest optimal work hours.
"""
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from collections import defaultdict

from repositories.actions_repo import ActionsRepository
from utils.logger import get_logger

logger = get_logger(__name__)


class TimeEstimationService:
    """Service for estimating content duration and analyzing user work patterns."""
    
    def __init__(self, actions_repo: ActionsRepository, llm_handler=None):
        self.actions_repo = actions_repo
        self.llm_handler = llm_handler
    
    def _round_to_5_minutes(self, hours: float) -> float:
        """Round duration in hours to nearest 5 minutes."""
        if hours is None or hours <= 0:
            return 0.0
        minutes = hours * 60
        rounded_minutes = round(minutes / 5) * 5
        return rounded_minutes / 60.0
    
    def estimate_content_duration(self, content_metadata: Dict, user_id: int = None) -> float:
        """
        Estimate the time needed to consume content using LLM.
        
        Args:
            content_metadata: Dict with title, description, duration, type, metadata
            user_id: Optional user ID for personalized estimation
        
        Returns:
            Estimated duration in hours (rounded to nearest 5 minutes)
        """
        # If we already have duration (e.g., from YouTube), use it
        if content_metadata.get('duration'):
            return self._round_to_5_minutes(content_metadata['duration'])
        
        # If we have word count, estimate reading time
        metadata = content_metadata.get('metadata', {})
        if 'word_count' in metadata and metadata['word_count']:
            # Average reading speed: 200-250 words per minute
            reading_time_hours = (metadata['word_count'] / 200) / 60.0
            return self._round_to_5_minutes(reading_time_hours)
        
        # Use LLM to estimate if available
        if self.llm_handler:
            try:
                prompt = self._build_estimation_prompt(content_metadata)
                user_id_str = str(user_id) if user_id else "0"
                response = self.llm_handler.get_response_custom(prompt, user_id_str)
                
                # Try to extract number from response
                import re
                numbers = re.findall(r'\d+\.?\d*', str(response))
                if numbers:
                    hours = float(numbers[0])
                    # If the number seems too large, it might be in minutes
                    if hours > 24:
                        hours = hours / 60.0
                    return self._round_to_5_minutes(hours)
            except Exception as e:
                logger.error(f"Error estimating duration with LLM: {str(e)}")
        
        # Fallback: rule-based estimation
        return self._round_to_5_minutes(self._fallback_estimation(content_metadata))
    
    def _build_estimation_prompt(self, content_metadata: Dict) -> str:
        """Build prompt for LLM to estimate content duration."""
        title = content_metadata.get('title', 'Content')
        description = content_metadata.get('description', '')
        content_type = content_metadata.get('type', 'unknown')
        metadata = content_metadata.get('metadata', {})
        
        prompt = f"""Estimate how long it would take to consume this content:

Title: {title}
Type: {content_type}
Description: {description[:300]}

"""
        
        if 'word_count' in metadata:
            prompt += f"Word count: {metadata['word_count']}\n"
        
        if 'duration_seconds' in metadata:
            prompt += f"Video duration: {metadata['duration_seconds']} seconds\n"
        
        prompt += """
Provide a single number representing the estimated time in HOURS needed to:
- Read/watch/listen to the content
- Understand and process the information
- Take notes if needed (for educational content)

Respond with just a number (e.g., "1.5" for 1.5 hours, or "0.25" for 15 minutes).
"""
        return prompt
    
    def _fallback_estimation(self, content_metadata: Dict) -> float:
        """Fallback rule-based estimation when LLM is not available."""
        content_type = content_metadata.get('type', 'unknown')
        metadata = content_metadata.get('metadata', {})
        
        if content_type == 'youtube':
            # Default YouTube video: 10 minutes
            return 10 / 60.0
        elif content_type == 'blog':
            word_count = metadata.get('word_count', 0)
            if word_count > 0:
                return (word_count / 200) / 60.0
            # Default blog post: 5 minutes
            return 5 / 60.0
        elif content_type == 'podcast':
            # Default podcast: 30 minutes
            return 0.5
        else:
            # Default: 15 minutes
            return 0.25
    
    def analyze_user_work_patterns(self, user_id: int) -> Dict:
        """
        Analyze user's historical actions to identify work patterns.
        
        Returns:
            Dict with patterns like:
            {
                'by_day_of_week': {'Monday': 5.2, 'Tuesday': 4.8, ...},
                'by_hour': {9: 0.5, 10: 1.2, ...},
                'average_daily': 4.5,
                'most_productive_day': 'Monday',
                'most_productive_hour': 10
            }
        """
        try:
            # Get all actions for the user
            actions = self.actions_repo.list_actions(user_id)
            
            if not actions:
                return {
                    'by_day_of_week': {},
                    'by_hour': {},
                    'average_daily': 0.0,
                    'most_productive_day': None,
                    'most_productive_hour': None,
                    'total_actions': 0
                }
            
            # Group by day of week
            by_day = defaultdict(float)
            by_hour = defaultdict(float)
            daily_totals = defaultdict(float)  # date -> total hours
            
            for action in actions:
                at = action.at
                day_name = at.strftime('%A')
                hour = at.hour
                
                by_day[day_name] += action.time_spent
                by_hour[hour] += action.time_spent
                
                date_key = at.date()
                daily_totals[date_key] += action.time_spent
            
            # Calculate averages
            day_counts = defaultdict(int)
            for action in actions:
                day_name = action.at.strftime('%A')
                day_counts[day_name] += 1
            
            # Average per day of week (total hours / number of occurrences)
            avg_by_day = {}
            for day, total in by_day.items():
                count = day_counts.get(day, 1)
                avg_by_day[day] = total / count if count > 0 else 0.0
            
            # Average daily hours
            if daily_totals:
                average_daily = sum(daily_totals.values()) / len(daily_totals)
            else:
                average_daily = 0.0
            
            # Find most productive day
            most_productive_day = max(avg_by_day.items(), key=lambda x: x[1])[0] if avg_by_day else None
            
            # Find most productive hour
            most_productive_hour = max(by_hour.items(), key=lambda x: x[1])[0] if by_hour else None
            
            return {
                'by_day_of_week': dict(avg_by_day),
                'by_hour': dict(by_hour),
                'average_daily': round(average_daily, 2),
                'most_productive_day': most_productive_day,
                'most_productive_hour': most_productive_hour,
                'total_actions': len(actions),
                'total_days': len(daily_totals)
            }
        
        except Exception as e:
            logger.error(f"Error analyzing work patterns for user {user_id}: {str(e)}")
            return {
                'by_day_of_week': {},
                'by_hour': {},
                'average_daily': 0.0,
                'most_productive_day': None,
                'most_productive_hour': None,
                'total_actions': 0
            }
    
    def suggest_daily_work_hours(self, user_id: int, day_of_week: str = None, 
                                   llm_handler=None) -> Dict:
        """
        Suggest optimal work hours for a given day based on user patterns.
        
        Args:
            user_id: User ID
            day_of_week: Optional day name (e.g., 'Monday'). If None, uses current day.
            llm_handler: Optional LLM handler for reasoning
        
        Returns:
            Dict with suggestion and reasoning
        """
        if not day_of_week:
            day_of_week = datetime.now().strftime('%A')
        
        patterns = self.analyze_user_work_patterns(user_id)
        
        # Get average for this day
        day_avg = patterns['by_day_of_week'].get(day_of_week, patterns['average_daily'])
        
        # Use LLM for reasoning if available
        if llm_handler and patterns['total_actions'] > 0:
            try:
                prompt = self._build_suggestion_prompt(patterns, day_of_week)
                user_id_str = str(user_id)
                reasoning = llm_handler.get_response_custom(prompt, user_id_str)
                
                # Try to extract suggested hours from reasoning
                import re
                numbers = re.findall(r'\d+\.?\d*', str(reasoning))
                if numbers:
                    suggested_hours = float(numbers[0])
                    # If number seems too large, it might be in minutes
                    if suggested_hours > 24:
                        suggested_hours = suggested_hours / 60.0
                else:
                    suggested_hours = day_avg
                
                return {
                    'suggested_hours': round(suggested_hours, 1),
                    'day_of_week': day_of_week,
                    'reasoning': reasoning,
                    'patterns': patterns
                }
            except Exception as e:
                logger.error(f"Error getting LLM suggestion: {str(e)}")
        
        # Fallback: use average for the day
        suggested_hours = day_avg if day_avg > 0 else patterns['average_daily']
        
        return {
            'suggested_hours': round(suggested_hours, 1),
            'day_of_week': day_of_week,
            'reasoning': f"Based on your historical patterns, you typically work {suggested_hours:.1f} hours on {day_of_week}s.",
            'patterns': patterns
        }
    
    def _build_suggestion_prompt(self, patterns: Dict, day_of_week: str) -> str:
        """Build prompt for LLM to suggest work hours."""
        prompt = f"""Analyze this user's work patterns and suggest optimal work hours for {day_of_week}:

Work patterns by day of week:
"""
        for day, hours in patterns['by_day_of_week'].items():
            prompt += f"- {day}: {hours:.1f} hours average\n"
        
        prompt += f"""
Average daily hours: {patterns['average_daily']:.1f}
Most productive day: {patterns['most_productive_day']}
Total actions logged: {patterns['total_actions']}
Total days with activity: {patterns['total_days']}

Based on these patterns, suggest how many hours the user should aim to work on {day_of_week}.
Consider:
- Their historical average for this day
- Their overall average
- Whether they tend to work more or less on this day

Provide:
1. A single number (hours) as the suggestion
2. A brief reasoning (1-2 sentences)

Format: "X.X hours - [reasoning]"
"""
        return prompt

import re
from datetime import datetime
import math

def format_date(date_obj, include_time=True):
    """
    Format a datetime object into a readable string
    
    Args:
        date_obj: Datetime object
        include_time: Whether to include time in the output
    
    Returns:
        str: Formatted date string
    """
    if not date_obj:
        return ""
        
    if include_time:
        return date_obj.strftime("%b %d, %Y at %I:%M %p")
    else:
        return date_obj.strftime("%b %d, %Y")


def truncate_text(text, max_length=100):
    """
    Truncate text to a max length and add ellipsis
    
    Args:
        text: Text to truncate
        max_length: Maximum length
    
    Returns:
        str: Truncated text
    """
    if not text:
        return ""
        
    if len(text) <= max_length:
        return text
        
    return text[:max_length].rsplit(' ', 1)[0] + "..."


def get_reading_time(text):
    """
    Calculate reading time in minutes
    
    Args:
        text: Content to read
    
    Returns:
        int: Reading time in minutes
    """
    if not text:
        return 1
        
    # Average reading speed: 200 words per minute
    word_count = len(re.findall(r'\w+', text))
    reading_time = math.ceil(word_count / 200)
    
    return max(1, reading_time)  # Minimum 1 minute


def is_valid_url(url):
    """
    Check if a URL is valid
    
    Args:
        url: URL to check
    
    Returns:
        bool: Whether URL is valid
    """
    url_pattern = re.compile(
        r'^(?:http|ftp)s?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or IP
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
    return url_pattern.match(url) is not None


def sanitize_html(html):
    """
    Remove potentially dangerous HTML tags
    
    Args:
        html: HTML content to sanitize
    
    Returns:
        str: Sanitized HTML
    """
    if not html:
        return ""
        
    # Remove script and iframe tags
    sanitized = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL)
    sanitized = re.sub(r'<iframe.*?>.*?</iframe>', '', sanitized, flags=re.DOTALL)
    
    # Remove on* attributes
    sanitized = re.sub(r'\s+on\w+=["\'][^"\']*["\']', '', sanitized)
    
    return sanitized

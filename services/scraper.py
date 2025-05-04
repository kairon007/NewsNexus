import logging
import feedparser
import requests
import trafilatura
from datetime import datetime
from bs4 import BeautifulSoup
from app import db
from models import Article

logger = logging.getLogger(__name__)

def fetch_rss_feed(feed):
    """Fetch and parse an RSS feed, saving new articles to the database"""
    try:
        # Parse the feed
        parsed_feed = feedparser.parse(feed.url)
        
        if not parsed_feed.entries:
            logger.warning(f"No entries found in feed: {feed.url}")
            return []
        
        new_articles = []
        
        for entry in parsed_feed.entries:
            # Check if article already exists
            existing = Article.query.filter_by(url=entry.link, feed_id=feed.id).first()
            if existing:
                continue
            
            # Parse publication date
            published_at = None
            if hasattr(entry, 'published_parsed'):
                published_at = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, 'updated_parsed'):
                published_at = datetime(*entry.updated_parsed[:6])
            
            # Get content
            content = ""
            if hasattr(entry, 'content'):
                content = entry.content[0].value
            elif hasattr(entry, 'summary'):
                content = entry.summary
            elif hasattr(entry, 'description'):
                content = entry.description
            
            # Create new article
            new_article = Article(
                title=entry.title,
                url=entry.link,
                content=content,
                published_at=published_at,
                feed_id=feed.id
            )
            
            db.session.add(new_article)
            new_articles.append(new_article)
        
        db.session.commit()
        logger.info(f"Added {len(new_articles)} new articles from feed: {feed.url}")
        
        return new_articles
        
    except Exception as e:
        logger.error(f"Error fetching RSS feed {feed.url}: {str(e)}")
        raise


def fetch_website_content(feed):
    """Fetch and parse a regular website, saving article content to the database"""
    try:
        # Check if article already exists for this URL
        existing = Article.query.filter_by(url=feed.url, feed_id=feed.id).first()
        if existing:
            logger.info(f"Content for {feed.url} already exists, skipping")
            return []
        
        # Send a request to the website
        downloaded = trafilatura.fetch_url(feed.url)
        
        if not downloaded:
            logger.warning(f"Could not download content from {feed.url}")
            return []
        
        # Extract main content
        extracted_text = trafilatura.extract(downloaded)
        
        if not extracted_text:
            logger.warning(f"Could not extract content from {feed.url}")
            return []
        
        # Try to extract title
        title = feed.name  # Default to feed name
        
        try:
            response = requests.get(feed.url, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                page_title = soup.find('title')
                if page_title:
                    title = page_title.text.strip()
        except Exception as e:
            logger.error(f"Error extracting title from {feed.url}: {str(e)}")
        
        # Create new article
        new_article = Article(
            title=title,
            url=feed.url,
            content=extracted_text,
            published_at=datetime.utcnow(),  # Use current time as we don't know when it was published
            feed_id=feed.id
        )
        
        db.session.add(new_article)
        db.session.commit()
        
        logger.info(f"Added content from website: {feed.url}")
        return [new_article]
        
    except Exception as e:
        logger.error(f"Error fetching website content {feed.url}: {str(e)}")
        raise


def get_website_text_content(url):
    """
    This function takes a url and returns the main text content of the website.
    The text content is extracted using trafilatura and easier to understand.
    """
    # Send a request to the website
    downloaded = trafilatura.fetch_url(url)
    text = trafilatura.extract(downloaded)
    return text

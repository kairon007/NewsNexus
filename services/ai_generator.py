import logging
import os
import requests
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqGeneration

logger = logging.getLogger(__name__)

# Try to use a smaller model that can fit in memory
DEFAULT_MODEL = "facebook/bart-large-cnn"
HUGGINGFACE_API_KEY = os.environ.get("HUGGINGFACE_API_KEY")

def generate_newsletter_draft(articles):
    """
    Generate a newsletter draft from a list of articles
    
    Args:
        articles: List of Article objects
    
    Returns:
        tuple: (title, content)
    """
    try:
        # Prepare article summaries
        article_texts = []
        article_titles = []
        
        for article in articles:
            article_titles.append(article.title)
            
            # Use original content or summary (max 1000 chars)
            article_content = article.content[:1000] if article.content else ""
            article_texts.append(f"Title: {article.title}\nSource: {article.url}\n\nContent: {article_content}")
        
        # Generate summaries for each article
        article_summaries = []
        
        if HUGGINGFACE_API_KEY:
            # Use Hugging Face Inference API for production use
            for i, text in enumerate(article_texts):
                summary = summarize_text_api(text)
                if summary:
                    article_summaries.append(f"## {article_titles[i]}\n\n{summary}\n\nRead more: {articles[i].url}")
                else:
                    # Fallback to using the title and URL if summary fails
                    article_summaries.append(f"## {article_titles[i]}\n\nRead more: {articles[i].url}")
        else:
            # Load the model locally (this can be memory intensive)
            try:
                summarizer = get_local_summarizer()
                
                for i, text in enumerate(article_texts):
                    if text:
                        summary = summarize_text_local(summarizer, text)
                        article_summaries.append(f"## {article_titles[i]}\n\n{summary}\n\nRead more: {articles[i].url}")
                    else:
                        # Fallback to using the title and URL if no content
                        article_summaries.append(f"## {article_titles[i]}\n\nRead more: {articles[i].url}")
            except Exception as e:
                logger.error(f"Error loading local summarizer: {str(e)}")
                # Fall back to using titles and URLs only
                for i, title in enumerate(article_titles):
                    article_summaries.append(f"## {title}\n\nRead more: {articles[i].url}")
        
        # Generate a newsletter title
        if len(article_titles) > 1:
            newsletter_title = generate_title(article_titles)
        else:
            newsletter_title = article_titles[0]
        
        # Generate the final newsletter content
        newsletter_content = f"# {newsletter_title}\n\n"
        newsletter_content += "\n\n".join(article_summaries)
        
        return newsletter_title, newsletter_content
    
    except Exception as e:
        logger.error(f"Error generating newsletter draft: {str(e)}")
        raise


def summarize_text_api(text, max_length=150):
    """Use Hugging Face Inference API to summarize text"""
    try:
        API_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
        headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}
        
        # Truncate input text if necessary
        max_input_length = 1024
        if len(text) > max_input_length:
            text = text[:max_input_length]
            
        payload = {
            "inputs": text,
            "parameters": {
                "max_length": max_length,
                "min_length": 30,
                "do_sample": False
            }
        }
        
        response = requests.post(API_URL, headers=headers, json=payload)
        result = response.json()
        
        if isinstance(result, list) and len(result) > 0:
            return result[0].get('summary_text', '')
        elif isinstance(result, dict) and 'summary_text' in result:
            return result['summary_text']
        else:
            logger.warning(f"Unexpected response format: {result}")
            return ""
            
    except Exception as e:
        logger.error(f"Error using Hugging Face API: {str(e)}")
        return ""


def get_local_summarizer():
    """Load a local summarization model"""
    try:
        tokenizer = AutoTokenizer.from_pretrained(DEFAULT_MODEL)
        model = AutoModelForSeq2SeqGeneration.from_pretrained(DEFAULT_MODEL)
        summarizer = pipeline("summarization", model=model, tokenizer=tokenizer)
        return summarizer
    except Exception as e:
        logger.error(f"Error loading local summarizer: {str(e)}")
        raise


def summarize_text_local(summarizer, text, max_length=150):
    """Use local Hugging Face model to summarize text"""
    try:
        # Truncate input text if necessary
        max_input_length = summarizer.tokenizer.model_max_length
        input_ids = summarizer.tokenizer.encode(text, truncation=True, max_length=max_input_length)
        truncated_text = summarizer.tokenizer.decode(input_ids, skip_special_tokens=True)
        
        summary = summarizer(truncated_text, max_length=max_length, min_length=30, do_sample=False)
        
        if summary and len(summary) > 0:
            return summary[0]['summary_text']
        return ""
    except Exception as e:
        logger.error(f"Error summarizing text locally: {str(e)}")
        return ""


def generate_title(article_titles, max_titles=5):
    """Generate a newsletter title based on article titles"""
    try:
        # Use only up to 5 titles to keep the input manageable
        titles_to_use = article_titles[:max_titles]
        
        topics = []
        for title in titles_to_use:
            # Extract key topics (simple approach)
            words = title.split()
            if len(words) > 2:
                topics.append(" ".join(words[:3]))
            else:
                topics.append(title)
        
        if len(topics) == 1:
            return f"Newsletter: {topics[0]}"
        elif len(topics) == 2:
            return f"Newsletter: {topics[0]} and {topics[1]}"
        else:
            return f"Newsletter: {', '.join(topics[:-1])} and {topics[-1]}"
            
    except Exception as e:
        logger.error(f"Error generating title: {str(e)}")
        return "Weekly Newsletter"

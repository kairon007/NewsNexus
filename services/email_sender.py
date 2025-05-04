import os
import logging
import sys
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, Personalization
from datetime import datetime

logger = logging.getLogger(__name__)

def send_newsletter(newsletter, content_html, subscribers, api_key=None):
    """
    Send a newsletter to subscribers via SendGrid
    
    Args:
        newsletter: Newsletter object
        content_html: HTML content of the newsletter
        subscribers: List of Subscriber objects
        api_key: SendGrid API key (optional, falls back to env var)
    
    Returns:
        tuple: (success, error_message)
    """
    try:
        # Check if we have subscribers
        if not subscribers:
            return False, "No subscribers to send to"
        
        # Get API key
        sendgrid_key = api_key or os.environ.get('SENDGRID_API_KEY')
        
        if not sendgrid_key:
            return False, "SendGrid API key not configured"
        
        sg = SendGridAPIClient(sendgrid_key)
        
        # Format content
        formatted_content = format_newsletter_content(newsletter.subject, content_html)
        
        # Create message
        message = Mail(
            from_email=Email(os.environ.get('FROM_EMAIL', 'newsletter@example.com')),
            subject=newsletter.subject
        )
        
        # Add subscribers
        for subscriber in subscribers:
            personalization = Personalization()
            personalization.add_to(To(subscriber.email, subscriber.name))
            message.add_personalization(personalization)
        
        # Add content
        message.content = Content("text/html", formatted_content)
        
        # Send the message
        response = sg.send(message)
        
        if response.status_code >= 200 and response.status_code < 300:
            logger.info(f"Newsletter sent successfully to {len(subscribers)} subscribers")
            return True, None
        else:
            error_msg = f"SendGrid error: Status code {response.status_code}"
            logger.error(error_msg)
            return False, error_msg
            
    except Exception as e:
        error_msg = f"Error sending newsletter: {str(e)}"
        logger.error(error_msg)
        return False, error_msg


def format_newsletter_content(subject, content_html):
    """
    Format newsletter content into a nice HTML template
    
    Args:
        subject: Newsletter subject
        content_html: Raw newsletter content (Markdown/HTML)
    
    Returns:
        str: Formatted HTML content
    """
    # Convert content to HTML if it's in Markdown
    html_content = convert_markdown_to_html(content_html)
    
    # Email template
    template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{subject}</title>
        <style>
            body {{
                font-family: 'Helvetica Neue', Arial, sans-serif;
                line-height: 1.6;
                color: #2B2D42;
                margin: 0;
                padding: 0;
                background-color: #EDF2F4;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background-color: #ffffff;
            }}
            .header {{
                text-align: center;
                padding: 20px 0;
                border-bottom: 1px solid #8D99AE;
            }}
            .content {{
                padding: 20px 0;
            }}
            h1 {{
                color: #2B2D42;
                margin-top: 0;
            }}
            h2 {{
                color: #2B2D42;
                border-bottom: 1px solid #EDF2F4;
                padding-bottom: 10px;
            }}
            a {{
                color: #EF233C;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            .footer {{
                text-align: center;
                font-size: 12px;
                color: #8D99AE;
                padding: 20px 0;
                border-top: 1px solid #8D99AE;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{subject}</h1>
                <p>{datetime.now().strftime('%B %d, %Y')}</p>
            </div>
            <div class="content">
                {html_content}
            </div>
            <div class="footer">
                <p>This newsletter was sent to you because you subscribed to our list.</p>
                <p>&copy; {datetime.now().year} Newsletter Automation System</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return template


def convert_markdown_to_html(content):
    """
    Convert Markdown to HTML
    
    Args:
        content: Markdown content
    
    Returns:
        str: HTML content
    """
    try:
        import markdown
        return markdown.markdown(content)
    except ImportError:
        # Simple fallback for Markdown conversion if the library is not available
        html_content = content
        
        # Convert headings
        lines = html_content.split('\n')
        for i, line in enumerate(lines):
            if line.startswith('# '):
                lines[i] = f'<h1>{line[2:]}</h1>'
            elif line.startswith('## '):
                lines[i] = f'<h2>{line[3:]}</h2>'
            elif line.startswith('### '):
                lines[i] = f'<h3>{line[4:]}</h3>'
        
        # Join lines and handle paragraphs
        html_content = '\n'.join(lines)
        paragraphs = html_content.split('\n\n')
        html_content = '\n'.join([f'<p>{p}</p>' for p in paragraphs if p and not (p.startswith('<h') and p.endswith('</h>'))])
        
        # Replace markdown links [text](url) with HTML links
        import re
        html_content = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', html_content)
        
        return html_content


def send_email(to_email, from_email, subject, text_content=None, html_content=None):
    """
    Send a single email using SendGrid
    
    Args:
        to_email: Recipient email
        from_email: Sender email
        subject: Email subject
        text_content: Plain text content
        html_content: HTML content
    
    Returns:
        bool: Success status
    """
    sendgrid_key = os.environ.get('SENDGRID_API_KEY')
    
    if not sendgrid_key:
        logger.error("SendGrid API key not configured")
        return False
    
    sg = SendGridAPIClient(sendgrid_key)

    message = Mail(
        from_email=Email(from_email),
        to_emails=To(to_email),
        subject=subject
    )

    if html_content:
        message.content = Content("text/html", html_content)
    elif text_content:
        message.content = Content("text/plain", text_content)

    try:
        sg.send(message)
        return True
    except Exception as e:
        logger.error(f"SendGrid error: {e}")
        return False

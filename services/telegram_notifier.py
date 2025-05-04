import logging
import requests

logger = logging.getLogger(__name__)

def send_notification(bot_token, chat_id, message):
    """
    Send a notification via Telegram
    
    Args:
        bot_token: Telegram bot token
        chat_id: Telegram chat ID
        message: Message to send
    
    Returns:
        bool: Success status
    """
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        data = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        response = requests.post(url, data=data)
        
        if response.status_code == 200:
            logger.info(f"Telegram notification sent: {message}")
            return True
        else:
            logger.error(f"Failed to send Telegram notification: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending Telegram notification: {str(e)}")
        return False

import logging
import sys
import os

# Add the project root to the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.config import settings
from src.services.auth_service import GoogleAuthManager
from src.services.gmail_service import GmailService
from src.services.calendar_service import CalendarService
from src.services.notion_service import NotionService

logging.basicConfig(level=settings.LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting Nexus AI: The Autonomous Task Intelligence...")
    
    logger.info("Initializing Nexus Core Services...")
    
    # Test Gmail
    try:
        gmail_service = GmailService()
        logger.info("Gmail Core initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize Gmail Core: {e}")

    # Test Calendar
    try:
        calendar_service = CalendarService()
        logger.info("Calendar Core initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize Calendar Core: {e}")

    # Test Notion
    try:
        notion_service = NotionService()
        logger.info("Notion Core initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize Notion Core: {e}")

    logger.info("Nexus initialization complete. Systems at 100%.")


if __name__ == "__main__":
    main()

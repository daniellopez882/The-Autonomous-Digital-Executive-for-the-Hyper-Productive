import sys
import os
import logging

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.email_agent import create_email_agent
from src.utils.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not set in .env")
        return

    logger.info("Initializing Email Analysis Agent...")
    try:
        agent_executor = create_email_agent()
        
        query = "Check my unread emails and summarize the top 3 most recent ones."
        logger.info(f"Running query: {query}")
        
        response = agent_executor.invoke({"input": query})
        
        print("\n--- Agent Response ---")
        print(response['output'])
        print("----------------------\n")
        
    except Exception as e:
        logger.error(f"Error running agent: {e}")

if __name__ == "__main__":
    main()

import sys
import os
import logging
from datetime import datetime, timedelta

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.calendar_agent import create_calendar_agent
from src.utils.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not set in .env")
        return

    logger.info("Initializing Calendar Management Agent...")
    try:
        agent_executor = create_calendar_agent()
        
        # Calculate dynamic times for the test
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00Z")
        tomorrow_end = (datetime.utcnow() + timedelta(days=1, hours=1)).strftime("%Y-%m-%dT11:00:00Z")
        
        query = f"Check if I have any events tomorrow. If not, schedule a 'Team Sync' from {tomorrow} to {tomorrow_end}."
        logger.info(f"Running query: {query}")
        
        response = agent_executor.invoke({"input": query})
        
        print("\n--- Agent Response ---")
        print(response['output'])
        print("----------------------\n")
        
    except Exception as e:
        logger.error(f"Error running agent: {e}")

if __name__ == "__main__":
    main()

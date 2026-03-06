import sys
import os
import logging

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.task_agent import create_task_agent
from src.utils.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not set in .env")
        return

    logger.info("Initializing Task Management Agent...")
    try:
        agent_executor = create_task_agent()
        
        query = "Create a high priority task named 'Review Project Proposal' in Notion."
        logger.info(f"Running query: {query}")
        
        response = agent_executor.invoke({"input": query})
        
        print("\n--- Agent Response ---")
        print(response['output'])
        print("----------------------\n")
        
    except Exception as e:
        logger.error(f"Error running agent: {e}")

if __name__ == "__main__":
    main()

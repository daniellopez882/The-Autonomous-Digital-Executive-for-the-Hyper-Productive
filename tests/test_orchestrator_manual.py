import sys
import os
import logging

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.orchestrator import MasterOrchestrator
from src.utils.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not set in .env")
        return

    logger.info("Initializing Master Orchestrator...")
    try:
        orchestrator = MasterOrchestrator()
        
        # Test routing
        print("\n--- Testing Routing (Calendar) ---")
        response1 = orchestrator.route_request("Schedule a meeting with the team for next Friday at 2 PM.")
        print(f"Response: {response1}")
        
        print("\n--- Testing Routing (Email) ---")
        response2 = orchestrator.route_request("Do I have any emails from my boss?")
        print(f"Response: {response2}")

        # Test Workflow
        print("\n--- Testing Daily Summary Workflow ---")
        summary = orchestrator.run_workflow("daily_summary")
        print(f"Summary:\n{summary}")
        
    except Exception as e:
        logger.error(f"Error running orchestrator: {e}")

if __name__ == "__main__":
    main()

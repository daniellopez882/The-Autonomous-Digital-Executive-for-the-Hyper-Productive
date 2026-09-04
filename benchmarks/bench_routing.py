import sys
import os
import time
import logging

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.orchestrator import MasterOrchestrator
from src.utils.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def measure_execution_time(func, *args, **kwargs):
    start_time = time.time()
    result = func(*args, **kwargs)
    end_time = time.time()
    execution_time = end_time - start_time
    return result, execution_time

def main():
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not set in .env")
        return

    logger.info("Initializing Master Orchestrator for Performance Test...")
    orchestrator = MasterOrchestrator()

    test_cases = [
        {"input": "Do I have any emails today?", "type": "Routing + Email"},
        {"input": "Schedule a meeting for tomorrow at 10am.", "type": "Routing + Calendar"},
        {"input": "Add a task to buy groceries.", "type": "Routing + Task"},
        {"input": "What is on my schedule today?", "type": "Routing + Calendar Check"},
    ]

    print("\n--- Performance Test Results ---")
    print(f"{'Test Case Type':<25} | {'Execution Time (s)':<20} | {'Status'}")
    print("-" * 60)

    for test in test_cases:
        try:
            _, duration = measure_execution_time(orchestrator.route_request, test["input"])
            print(f"{test['type']:<25} | {duration:<20.4f} | PASS")
        except Exception as e:
            print(f"{test['type']:<25} | {'N/A':<20} | FAIL ({e})")
    
    print("-" * 60)

if __name__ == "__main__":
    main()

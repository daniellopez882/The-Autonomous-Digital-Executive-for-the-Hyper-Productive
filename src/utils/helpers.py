import datetime
import time
import random
import logging
from functools import wraps

logger = logging.getLogger(__name__)

def get_current_time_iso():
    return datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time

def parse_date(date_str: str):
    # Implement specific date parsing logic here if needed
    pass

def retry_with_backoff(retries=3, backoff_in_seconds=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            x = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if x == retries:
                        logger.error(f"Function {func.__name__} failed after {retries} retries.")
                        raise e
                    sleep = (backoff_in_seconds * 2 ** x + random.uniform(0, 1))
                    logger.warning(f"Function {func.__name__} failed. Retrying in {sleep:.2f}s... Error: {e}")
                    time.sleep(sleep)
                    x += 1
        return wrapper
    return decorator

class LangGraphAdapter:
    def __init__(self, graph):
        self.graph = graph
    
    def invoke(self, inputs: dict):
        # Adapt AgentExecutor style input to LangGraph
        user_input = inputs.get("input")
        if not user_input:
             return {"output": "No input provided"}
        
        # Invoke graph with messages
        state = self.graph.invoke({"messages": [("user", user_input)]})
        
        # Extract final response
        if "messages" in state and state["messages"]:
            return {"output": state["messages"][-1].content}
        return {"output": "No response generated"}

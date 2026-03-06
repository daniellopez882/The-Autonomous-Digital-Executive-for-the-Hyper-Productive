from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from src.tools.gmail_tools import GmailReadTool
from src.utils.config import settings
from src.utils.helpers import LangGraphAdapter

def create_email_agent():
    llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=settings.GEMINI_API_KEY)
    tools = [GmailReadTool()]
    
    # Create LangGraph agent
    graph = create_react_agent(llm, tools)
    
    # Return adapted agent
    return LangGraphAdapter(graph)

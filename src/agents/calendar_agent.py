from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from src.tools.calendar_tools import CalendarCreateTool, CalendarListTool, CalendarUpdateTool
from src.utils.config import settings
from src.utils.helpers import LangGraphAdapter

def create_calendar_agent():
    llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=settings.GEMINI_API_KEY)
    tools = [CalendarCreateTool(), CalendarListTool(), CalendarUpdateTool()]
    
    graph = create_react_agent(llm, tools)
    return LangGraphAdapter(graph)

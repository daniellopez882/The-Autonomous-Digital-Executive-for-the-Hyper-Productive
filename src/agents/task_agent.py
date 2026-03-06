from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from src.tools.notion_tools import NotionCreateTaskTool, NotionListTasksTool, NotionUpdateTaskTool
from src.utils.config import settings
from src.utils.helpers import LangGraphAdapter

def create_task_agent():
    llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=settings.GEMINI_API_KEY)
    tools = [NotionCreateTaskTool(), NotionListTasksTool(), NotionUpdateTaskTool()]
    
    graph = create_react_agent(llm, tools)
    return LangGraphAdapter(graph)

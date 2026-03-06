from typing import List, Dict, Any
# from langchain.agents import AgentExecutor # Removed
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from src.agents.email_agent import create_email_agent
from src.agents.calendar_agent import create_calendar_agent
from src.agents.task_agent import create_task_agent
from src.utils.config import settings
import logging

logger = logging.getLogger(__name__)

class MasterOrchestrator:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=settings.GEMINI_API_KEY)
        self.email_agent = create_email_agent()
        self.calendar_agent = create_calendar_agent()
        self.task_agent = create_task_agent()

    def route_request(self, user_input: str) -> str:
        """
        Analyzes the user input and routes it to the appropriate sub-agent.
        """
        prompt = PromptTemplate.from_template(
            """You are Nexus Intelligence, a cutting-edge autonomous digital executive. 
            Your purpose is to seamlessly orchestrate complex workflows across the user's digital ecosystem.
            
            You have three specialized sub-intelligence units at your disposal:
            1. Email Intelligence: Specialized in deep analysis and synthesis of Gmail communications.
            2. Calendar Intelligence: Expert in temporal management and Google Calendar scheduling.
            3. Task Intelligence: Master of organizational structure and Notion database management.

            Analyze the user's intent with extreme precision and delegate to the appropriate unit.
            Return exactly one of the following tokens: "EMAIL", "CALENDAR", "TASK", or "GENERAL".
            
            User Request: {input}
            Nexus Routing Decision:"""
        )
        
        chain = prompt | self.llm
        decision = chain.invoke({"input": user_input}).content.strip().upper()
        
        logger.info(f"Routing decision: {decision}")
        
        if "EMAIL" in decision:
            return self.email_agent.invoke({"input": user_input})['output']
        elif "CALENDAR" in decision:
            return self.calendar_agent.invoke({"input": user_input})['output']
        elif "TASK" in decision:
            return self.task_agent.invoke({"input": user_input})['output']
        else:
            return "I am not sure how to handle this request directly. Please be more specific about using Email, Calendar, or Tasks."

    def run_workflow(self, workflow_type: str, context: Dict[str, Any] = None):
        """
        Executes predefined multi-step workflows.
        """
        if workflow_type == "daily_summary":
            return self._run_daily_summary()
        # Add more workflows here
        return "Unknown workflow type."

    def _run_daily_summary(self):
        # 1. Get calendar events for today
        events = self.calendar_agent.invoke({"input": "What are my events for today?"})['output']
        
        # 2. Get high priority tasks
        tasks = self.task_agent.invoke({"input": "List my high priority tasks."})['output']
        
        # 3. Get unread emails (limit to top 3)
        emails = self.email_agent.invoke({"input": "Summarize my top 3 unread emails."})['output']
        
        # 4. Synthesize summary
        summary_prompt = f"""
        Identity: Nexus Intelligence
        Task: Synthesize a high-level executive briefing.
        
        Raw Intelligence Data:
        - Calendar: {events}
        - Tasks: {tasks}
        - Communications: {emails}
        
        Instruction: Provide a sophisticated, concise, and empowering executive briefing for the user. 
        Focus on clarity, priority, and momentum. Use professional yet encouraging tone.
        """
        summary = self.llm.invoke(summary_prompt).content
        return summary

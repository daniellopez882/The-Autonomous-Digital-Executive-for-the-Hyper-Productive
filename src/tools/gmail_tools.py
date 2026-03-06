from typing import List, Optional, Type
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from src.services.gmail_service import GmailService
import logging

logger = logging.getLogger(__name__)

class GmailReadInput(BaseModel):
    query: str = Field(description="Gmail search query (e.g., 'is:unread', 'from:boss@example.com')")
    max_results: int = Field(default=10, description="Maximum number of emails to retrieve")

class GmailReadTool(BaseTool):
    name: str = "gmail_read"
    description: str = "Read emails from Gmail based on a search query."
    args_schema: Type[BaseModel] = GmailReadInput
    gmail_service: GmailService = Field(default_factory=GmailService)

    def _run(self, query: str, max_results: int = 10) -> str:
        try:
            messages = self.gmail_service.list_messages(query=query, max_results=max_results)
            if not messages:
                return "No emails found matching the query."
            
            email_contents = []
            for msg_meta in messages:
                msg = self.gmail_service.get_message(msg_meta['id'])
                if not msg:
                    continue
                    
                payload = msg.get('payload', {})
                headers = payload.get('headers', [])
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
                snippet = msg.get('snippet', '')
                
                email_contents.append(f"From: {sender}\nSubject: {subject}\nSnippet: {snippet}\n---")
            
            return "\n".join(email_contents)
        except Exception as e:
            logger.error(f"Error reading emails: {e}")
            return f"Error reading emails: {str(e)}"

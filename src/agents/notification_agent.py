from typing import Type
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from src.services.gmail_service import GmailService
import logging
from email.mime.text import MIMEText
import base64

logger = logging.getLogger(__name__)

class NotificationSendInput(BaseModel):
    recipient: str = Field(description="Email address of requestor")
    subject: str = Field(description="Subject of the notification")
    body: str = Field(description="Body of the notification")

class NotificationSendTool(BaseTool):
    name: str = "notification_send"
    description: str = "Send an email notification."
    args_schema: Type[BaseModel] = NotificationSendInput
    gmail_service: GmailService = Field(default_factory=GmailService)

    def _run(self, recipient: str, subject: str, body: str) -> str:
        try:
            message = MIMEText(body)
            message['to'] = recipient
            message['subject'] = subject
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            service = self.gmail_service.get_service()
            if not service:
                 return "Gmail service unavailable."

            sent_message = service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
            return f"Notification sent! Id: {sent_message['id']}"
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return f"Error sending notification: {str(e)}"

from googleapiclient.discovery import build
from src.services.auth_service import GoogleAuthManager
from src.utils.helpers import retry_with_backoff

class GmailService:
    def __init__(self, auth_manager: GoogleAuthManager = None):
        self.auth_manager = auth_manager or GoogleAuthManager()
        self.service = None

    def get_service(self):
        if not self.service:
            creds = self.auth_manager.authenticate()
            if creds:
                self.service = build('gmail', 'v1', credentials=creds)
        return self.service
    
    @retry_with_backoff(retries=3)
    def list_messages(self, query: str = '', max_results: int = 10):
        service = self.get_service()
        if not service:
            return []
        
        results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        messages = results.get('messages', [])
        return messages

    @retry_with_backoff(retries=3)
    def get_message(self, msg_id: str):
        service = self.get_service()
        if not service:
             return None
        
        message = service.users().messages().get(userId='me', id=msg_id).execute()
        return message

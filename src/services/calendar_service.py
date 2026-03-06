from googleapiclient.discovery import build
from src.services.auth_service import GoogleAuthManager
from src.utils.helpers import retry_with_backoff

class CalendarService:
    def __init__(self, auth_manager: GoogleAuthManager = None):
        self.auth_manager = auth_manager or GoogleAuthManager()
        self.service = None

    def get_service(self):
        if not self.service:
            creds = self.auth_manager.authenticate()
            if creds:
                self.service = build('calendar', 'v3', credentials=creds)
        return self.service
    
    @retry_with_backoff(retries=3)
    def list_events(self, max_results: int = 10):
        service = self.get_service()
        if not service:
            return []
        
        events_result = service.events().list(calendarId='primary', maxResults=max_results, singleEvents=True, orderBy='startTime').execute()
        events = events_result.get('items', [])
        return events

    @retry_with_backoff(retries=3)
    def create_event(self, event_body: dict):
        service = self.get_service()
        if not service:
            return None
        
        event = service.events().insert(calendarId='primary', body=event_body).execute()
        return event

    @retry_with_backoff(retries=3)
    def update_event(self, event_id: str, event_body: dict):
        service = self.get_service()
        if not service:
            return None
        
        # First retrieve the event to preserve fields not being updated (simple merge)
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
        
        # Update fields
        for key, value in event_body.items():
            if value is not None:
                event[key] = value

        updated_event = service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
        return updated_event

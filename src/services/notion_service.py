from notion_client import Client
from src.services.auth_service import NotionAuthManager
from src.utils.config import settings
from src.utils.helpers import retry_with_backoff

class NotionService:
    def __init__(self, auth_manager: NotionAuthManager = None):
        self.auth_manager = auth_manager or NotionAuthManager()
        self.client = Client(auth=self.auth_manager.api_key)
        self.database_id = settings.NOTION_DATABASE_ID

    @retry_with_backoff(retries=3)
    def create_page(self, properties: dict):
        if not self.database_id:
            raise ValueError("Notion Database ID is not set.")
        
        response = self.client.pages.create(
            parent={"database_id": self.database_id},
            properties=properties
        )
        return response

    @retry_with_backoff(retries=3)
    def query_database(self, query: dict = None):
         if not self.database_id:
            raise ValueError("Notion Database ID is not set.")
         
         if query is None:
             query = {}
             
         response = self.client.databases.query(
             database_id=self.database_id,
             **query
         )
         return response

    @retry_with_backoff(retries=3)
    def update_page(self, page_id: str, properties: dict):
        response = self.client.pages.update(
            page_id=page_id,
            properties=properties
        )
        return response

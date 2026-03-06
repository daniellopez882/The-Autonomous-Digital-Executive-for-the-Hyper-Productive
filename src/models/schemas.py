from pydantic import BaseModel
from typing import List, Optional

class EmailSchema(BaseModel):
    id: str
    threadId: str
    snippet: str
    sender: str
    subject: str
    date: str

class EventSchema(BaseModel):
    summary: str
    location: Optional[str] = None
    description: Optional[str] = None
    start: dict
    end: dict

class TaskSchema(BaseModel):
    id: str
    title: str
    status: str
    priority: Optional[str] = None
    due_date: Optional[str] = None

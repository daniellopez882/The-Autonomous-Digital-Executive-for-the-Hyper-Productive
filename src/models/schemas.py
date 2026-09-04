from pydantic import BaseModel


class EmailSchema(BaseModel):
    id: str
    threadId: str
    snippet: str
    sender: str
    subject: str
    date: str


class EventSchema(BaseModel):
    summary: str
    location: str | None = None
    description: str | None = None
    start: dict
    end: dict


class TaskSchema(BaseModel):
    id: str
    title: str
    status: str
    priority: str | None = None
    due_date: str | None = None

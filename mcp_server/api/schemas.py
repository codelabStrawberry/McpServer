from pydantic import BaseModel

class ChatPayload(BaseModel):
    prompt: str

class RagPayload(BaseModel):
    question: str

class DocPayload(BaseModel):
    id: str
    text: str

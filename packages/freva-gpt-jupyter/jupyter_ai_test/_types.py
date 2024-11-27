from typing import Literal
from pydantic import BaseModel

class Message(BaseModel):
    variant: Literal["Prompt", "User", "Assistant", "Code", "CodeOutput", "Image", "ServerError", "OpenAIError", "CodeError", "StreamEnd", "ServerHint"]
    content: str


from typing import Literal, Union, Sequence
from pydantic import BaseModel

class Message(BaseModel):
    variant: Literal["Prompt", "User", "Assistant", "Code", "CodeOutput", "Image", "ServerError", "OpenAIError", "CodeError", "StreamEnd", "ServerHint"]
    content: Union[str, Sequence[str]]


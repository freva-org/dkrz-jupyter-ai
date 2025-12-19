from typing import Literal, Union, Sequence
from pydantic import BaseModel
from langchain_core.messages import BaseMessage

class Message(BaseModel):
    variant: Literal["Prompt", "User", "Assistant", "Code", "CodeOutput", "Image", "ServerError", "OpenAIError", "CodeError", "StreamEnd", "ServerHint"]
    content: Union[str, Sequence[str]]

class BasePrompt(BaseModel):
    messages: Sequence[BaseMessage]

    def _format_messages_for_chat(self) -> str:
        format_str = ""
        for message in self.messages:
            format_str+=f"{message.type}: {message.content}\n\n"
        return format_str






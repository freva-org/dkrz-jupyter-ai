from typing import Literal, Sequence, Union

from langchain_core.messages import BaseMessage
from pydantic import BaseModel


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






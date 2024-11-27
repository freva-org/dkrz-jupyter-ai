import json
from typing import Any, Dict, List, Optional, Iterator

from pydantic import Field, model_validator

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.llms import LLM
from langchain_core.messages import BaseMessage, ChatMessageChunk, ChatMessage

from ._client import Client
from ._types import Message

class FrevaLLM(LLM):
    model_id: str
    client: Client = Client(host="https://freva.dkrz.de/api/chatbot/")
    base_url:str = Field(default="https://freva.dkrz.de/api/chatbot/")
    auth_key:str = Field(default="***REMOVED***")
    client_kwargs : Optional[Dict]

    @property
    def _llm_type(self) -> str:
        return "Freva-GPT"
    
    @model_validator(mode="after")
    def _set_clients(self):
        """Set clients to use for ollama."""
        self.client = Client(host=self.base_url, **self.client_kwargs)
        return self
    
    def _translate_to_chat_message_chunk(
            self,
            message: Message
    ) -> ChatMessageChunk:
        return ChatMessageChunk(content=message.content, role=message.variant)
    
    def _translate_to_chat_message(
            self,
            message: Message
    ) -> ChatMessage:
        return ChatMessage(content=message.content, role=message.variant)
    
    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatMessageChunk]:
        
        r = self._client.request(method="GET", url="/streamresponse", stream=True, params={"input":prompt, "auth_key":self.auth_key})
        return json.dumps(r)
        
        
    def _stream(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatMessageChunk]:
        
        for part in self.client.request(method="GET", url="/streamresponse", stream=True, params={"input":prompt, "auth_key":self.auth_key}):
            message = Message(**part)
            yield self._translate_to_chat_message_chunk(message)

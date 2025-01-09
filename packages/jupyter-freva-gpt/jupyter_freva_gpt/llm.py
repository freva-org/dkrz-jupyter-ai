import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Iterator
from traitlets.config import Application

from langchain_core.pydantic_v1 import (
    Field,
    root_validator,
    SecretStr
)
from langchain_core.utils import convert_to_secret_str, get_from_dict_or_env
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import generate_from_stream
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, ChatMessageChunk, ChatMessage, AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatGeneration, ChatResult

from ._client import Client
from ._types import Message, BasePrompt

log = logging.getLogger(__name__)
handler = logging.StreamHandler()  # Logs to the console
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
log.addHandler(handler)

class FrevaChat(BaseChatModel):

    model_id: str
    base_url:str = Field(default="https://freva.dkrz.de/api/chatbot")
    auth_key:Optional[SecretStr] = Field(default=None)
    client_kwargs : Optional[Dict] = {}
    _client: Client = Field(default=None)
    stop: str = Field(default="Generation complete")
    thread_id: str = Field(default=None)

    logger = Application.instance().log
    logger.info("Log message using JupyterLab's logging configuration")

    debug: bool = False

    @property
    def _llm_type(self) -> str:
        return "Freva-GPT"
    
    @root_validator(pre=False, skip_on_failure=True)
    @classmethod
    def _validate_env(cls, values:Dict) -> Dict:
        values["_client"] = Client(host=values["base_url"], **values["client_kwargs"])
        values["auth_key"] = convert_to_secret_str(
            get_from_dict_or_env(values, "freva_gpt_api_key", "FREVAGPT_API_KEY")
        )
        return values
        
    def _translate_to_chat_generation_chunk(
            self,
            message: Message
    ) -> ChatGenerationChunk:
        return ChatGenerationChunk(
            message=AIMessageChunk(content=message.content)
            )
    
    def _translate_to_chat_generation(
            self,
            message: Message
    ) -> ChatGeneration:
        return ChatGeneration(
            message=AIMessage(content=message.content)
        )
    
    def _generate(
    self,
    prompt: str,
    stop: Optional[List[str]] = None,
    run_manager: Optional[CallbackManagerForLLMRun] = None,
    **kwargs: Any,
    ) -> ChatResult:
        self.logger.info("Called _generate")
        try:
            stream = self._stream(prompt, stop, run_manager, **kwargs)
            chat_result: ChatResult = generate_from_stream(stream)
        except ConnectionError as e:
            if e.errno == 409:
                self.logger.warning(
                        (
                        f"Encountered 409 Connection Conflict Error: {e.strerror}. ",
                        "Creating a new thread and trying again..."
                        )
                )
                self.thread_id=None
                stream = self._stream(prompt, stop, run_manager, **kwargs)
                chat_result: ChatResult = generate_from_stream(stream)
            else:
                raise
        return chat_result
    
    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatMessage:
        
        self.logger.info("Called _call")
        try:
            stream = self._stream(prompt, stop, run_manager, **kwargs)
            chat_result: ChatResult = generate_from_stream(stream)
        except ConnectionError as e:
            if e.errno == 409:
                self.logger.warning(
                        (
                        f"Encountered 409 Connection Conflict Error: {e.strerror}. ",
                        "Creating a new thread and trying again..."
                        )
                )
                self.thread_id=None
                stream = self._stream(prompt, stop, run_manager, **kwargs)
                chat_result: ChatResult = generate_from_stream(stream)
            else:
                raise
        return chat_result.generations[0].text
        
        
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatMessageChunk]:
        
        if stop is None:
            stop=self.stop
        prompt = BasePrompt(messages=[BaseMessage(content=message.content, type=message.type) for message in messages])._format_messages_for_chat()
        self.logger.info(f"thread id : {self.thread_id}")
        self.logger.info(f"Calling _stream with prompt: {prompt}")

        if self.debug:
            with open(
                file=f"{Path(__file__).parent}/example_conversation.json") as fo:
                    stream=json.load(fo)
        else:
            stream=self._client.request(
                method="GET", 
                url="/streamresponse", 
                stream=True, 
                params={"input":prompt, 
                        "auth_key":self.auth_key.get_secret_value(), 
                        "chatbot":self.model_id or None,
                        "thread_id":self.thread_id or None}
            )
        first_part=True
        code_started=False
        code_content=""
        for part in stream:
            content = part["content"]
            variant = part["variant"]
            if variant=="ServerHint":
                if stop in content:
                    break
                if first_part:
                    if not self.thread_id: 
                        self.thread_id = json.loads(content)["thread_id"]
                        self.logger.info(f"Started new thread with ID {self.thread_id}")
                    first_part=False
                    message=Message(
                        variant="ServerHint",
                        content=''
                    )
                else:
                    continue
            elif variant=="Code":
                code_content+=content[0]
                if code_content=='{"code":"':
                    code_started=True
                    code_content="\n```python\n"
                    message=Message(
                            variant="Code",
                            content=code_content
                        )
                    code_content=""
                elif code_started:
                    if code_content[-2:]=='\\n':
                        code_content=code_content.replace('\\n', '\n')
                        message=Message(
                            variant="Code",
                            content=code_content
                        )
                        code_content=""
                    elif content[0]=='"}':
                        code_content="\n```\n\n"
                        code_started=False
                        message=Message(
                            variant="Code",
                            content=code_content
                        )
                        code_content=""
                    elif '\\' not in code_content:
                        message= Message(
                            variant="Code",
                            content=code_content
                        )
                        code_content=""
                    else:
                        continue
                else:
                    continue
            elif variant=="CodeOutput":
                message=Message(
                        variant="CodeOutput",
                        content="\n```\n" +content[0]+"\n```\n"
                )
            elif variant=="Image":
                self.logger.info("Returning image")
                base64_string=content
                message=Message(
                    variant="Image", 
                    content=f'\n\n ![alt text](data:image/png;base64,{base64_string})\n\n'
                )
            elif variant=="Assistant":
                message=Message(**part)
            else:
                continue
            yield self._translate_to_chat_generation_chunk(message)

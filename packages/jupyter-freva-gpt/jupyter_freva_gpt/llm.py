
import json
import logging
import os
import tempfile
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Iterator
from traitlets.config import Application

from pydantic import Field, model_validator, SecretStr
from langchain_core.utils import convert_to_secret_str, get_from_env
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import generate_from_stream
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, ChatMessageChunk, ChatMessage, AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatGeneration, ChatResult

import freva_client

from ._client import Client
from ._types import Message, BasePrompt

default_user = os.environ["USER"] if "USER" in os.environ.keys() else "test-user"
class FrevaChat(BaseChatModel):

    model_id: str
    base_url:str = Field(default="https://nextgems.dkrz.de")
    user_id:str = Field(default=default_user)
    client_kwargs : Optional[Dict] = {}
    client: Client = Field(default=None)
    stop: str = Field(default="Generation complete")
    thread_id: str = Field(default=None)
    freva_token_file: str = Field(default=None)
    freva_token_dict: dict = Field(default=None)
    freva_auth_token: SecretStr = Field(default=None)
    logger: logging.Logger = Application.instance().log
    debug: bool = False

    @property
    def _llm_type(self) -> str:
        return "Freva-GPT"
    
    @classmethod
    def _update_token_file(cls, values:dict) -> dict:
        freva_token_file = values["freva_token_file"]
        freva_token_dict = values["freva_token_dict"]
        with open(freva_token_file, mode='r') as fr:
            freva_file_dict = json.load(fr)
        file_expires_at = datetime.fromtimestamp(freva_file_dict["expires"])
        dict_expires_at = datetime.fromtimestamp(freva_token_dict["expires"])
        if file_expires_at > dict_expires_at:
            values["freva_token_dict"] = freva_file_dict
        elif dict_expires_at > file_expires_at:
            with open(freva_token_file, mode="w") as fw:
                json.dump(freva_token_dict, fw)
        return values
    
    @model_validator(mode="before")
    def _validate_secrets(cls, values: Any) -> Any:
        values["freva_token_file"] = get_from_env(
            key="freva_token_file",
            env_key="FREVA_TOKEN_FILE",
            default=f"{os.path.join(os.path.expanduser('~'), '.freva_token.json')}"
        ).strip('\"')
        values["freva_token_json"] = values["freva_token_json"] if "freva_token_json" in values.keys() else None
        # if token file exists but token json is not defined, load it from file
        if os.path.exists(values["freva_token_file"]) and not values["freva_token_json"]:
            with open(values["freva_token_file"], mode="r") as fr:
                values["freva_token_dict"] = json.load(fr)
            values["freva_token_json"] = json.dumps(values["freva_token_dict"])
        # if freva token file  does not exist but token json does, write json string to file
        elif not os.path.exists(values["freva_token_file"]) and values["freva_token_json"]:
            values["freva_token_dict"] = json.loads(values["freva_token_json"])
            with open(values["freva_token_file"], mode="w") as fw:
                json.dump(values["freva_token_dict"], fw)
        elif not os.path.exists(values["freva_token_file"]) and not values["freva_token_json"]:
            raise ValueError(f"Neither the Freva token file {values['freva_token_file']} nor the Freva Token JSON-String could be found.")
        values["freva_token_dict"] = json.loads(values["freva_token_json"])
        values = cls._update_token_file(values)
        values["freva_auth_token"] = values["freva_token_dict"]["access_token"]
        return values
    
    @model_validator(mode="after")
    def _validate_env(self) -> Dict:
        token_expires_at = datetime.fromtimestamp(self.freva_token_dict["expires"])
        token_refresh_expires_at = datetime.fromtimestamp(self.freva_token_dict["refresh_expires"])
        now = datetime.now()
        if now > token_refresh_expires_at:
            raise ValueError(
                (
                    "(Refresh) token in json-encoded token string has expired. "
                    f"Please generate a new token using the Freva instance website at: {self.base_url}"
                )
            ) 
        if now > token_expires_at:
            self.logger.warning(f"Freva auth token expired. Using refresh token to generate new token and writing it to file {self.freva_token_file}.")
            try:
                Auth = freva_client.auth.Auth(token_file=self.freva_token_file or None)
                self.freva_token_dict=Auth.authenticate(
                    host=self.base_url,
                    force=False,
                )
                self.freva_auth_token = convert_to_secret_str(self.freva_token_dict["access_token"])
                with open(self.freva_token_file, mode="w") as fw:
                    json.dump(self.freva_token_dict, fw)
            except:
                raise 
        self.client_kwargs = {
            "headers": {
                "Authorization": f"Bearer {self.freva_auth_token.get_secret_value()}"
            }
        }
        self.client = Client(host=f"{self.base_url}/api/chatbot", **self.client_kwargs)
        return self
        
    def _reset(self) -> None:
        self.thread_id = None

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
        self.logger.debug("Called _generate")
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
        
        stop = stop or self.stop
        prompt = BasePrompt(messages=[BaseMessage(content=message.content, type=message.type) for message in messages])._format_messages_for_chat()
        self.logger.info(f"thread id : {self.thread_id}")
        # remove any image strings from the prompt to reduce number of tokens drastically
        prompt = re.sub(
                        r"\(data:image/png.*",
                        "('an image was successfully generated')",
                        prompt
        )
        self.logger.debug(f"Calling _stream with prompt: {prompt}")

        if self.debug:
            with open(
                file=f"{Path(__file__).parent}/example_conversation.json") as fo:
                    stream=json.load(fo)
        else:
            self.logger.debug(f"Sending request to /streamresponse with following params input={prompt}, chatbot={self.model_id}, thread_id={self.thread_id}, user={self.user_id}")
            stream=self.client.request(
                method="GET", 
                url="/streamresponse", 
                stream=True, 
                params={
                    "input":prompt,  
                    "chatbot":self.model_id or None,
                    "thread_id":self.thread_id or None,
                    "user_id": self.user_id or None,
                },
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
                    continue
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
                self.logger.debug("Returning image")
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


import aiofiles
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Iterator, AsyncIterator
from traitlets.config import Application

from pydantic import Field, model_validator, SecretStr
from langchain_core.utils import convert_to_secret_str, get_from_env
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import agenerate_from_stream, generate_from_stream
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, ChatMessageChunk, AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatGeneration, ChatResult

import urllib.parse
import freva_client

from ._client import Client, AsyncClient
from ._types import Message, BasePrompt

class AuthError(Exception):
    pass 

default_user = os.environ["USER"] if "USER" in os.environ.keys() else "test-user"
class FrevaChat(BaseChatModel):

    model_id: str
    base_url:str = Field(default="https://nextgems.dkrz.de")
    user_id:str = Field(default=default_user)
    client_kwargs : Optional[Dict] = {}
    client: Client = Field(default=None)
    aclient: AsyncClient = Field(default=None)
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
    @classmethod
    def _validate_secrets(cls, values: Any) -> Any:
        """Validate freva token file"""
        values["freva_token_file"] = get_from_env(
                                        key="freva_token_file",
                                        env_key="FREVA_TOKEN_FILE",
                                        default=f"{os.path.join(os.path.expanduser('~'), '.freva_token.json')}"
        )
        # if token file exists but token json is not defined, load it from file
        values["freva_token_json"] = values.get("freva_token_json", None)
        if os.path.exists(values["freva_token_file"]) and not values["freva_token_json"]:
            with open(values["freva_token_file"], mode="r") as fr:
                values["freva_token_dict"] = json.load(fr)
        # if freva token file  does not exist but token json does, write json string to file
        elif not os.path.exists(values["freva_token_file"]) and values["freva_token_json"]:
            values["freva_token_dict"] = json.loads(values["freva_token_json"])
            with open(values["freva_token_file"], mode="w") as fw:
                json.dump(values["freva_token_dict"], fw)
        else:
               raise AuthError("Freva token file does not exist and no freva token json string provided. Please login via the /login slash command first.") from None
        values = cls._update_token_file(values)
        values["freva_auth_token"] = values["freva_token_dict"]["access_token"]
        return values
    
    @model_validator(mode="after")
    def _validate_env(self) -> Dict:
        self.client = Client(host=f"{self.base_url}/api/chatbot", **self.client_kwargs)
        self.aclient = AsyncClient(host=f"{self.base_url}/api/chatbot", **self.client_kwargs)
        token_expires_at = datetime.fromtimestamp(self.freva_token_dict["expires"])
        token_refresh_expires_at = datetime.fromtimestamp(self.freva_token_dict["refresh_expires"])
        now = datetime.now()
        if now > token_refresh_expires_at:
            raise AuthError("Refresh token has expired. Please login again using the /login dash command.") from None
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
                raise AuthError("Could not generate a new token from the token file. Please try again or reauthenticate.") from None
        self.client_kwargs = {
            "headers": {
                "Authorization": f"Bearer {self.freva_auth_token.get_secret_value()}"
            }
        }
        return self
        
    def _reset(self) -> None:
        self.thread_id = None

    @classmethod
    def _translate_to_chat_generation_chunk(
            cls,
            message: Message
    ) -> ChatGenerationChunk:
        return ChatGenerationChunk(
            message=AIMessageChunk(content=message.content)
            )
    
    @classmethod
    def _translate_to_chat_generation(
            cls,
            message: Message
    ) -> ChatGeneration:
        return ChatGeneration(
            message=AIMessage(content=message.content)
        )
    
    @classmethod
    def _process_code_chunk(
            cls,
            content: str,
            code_content="",
            code_started=False
    ) -> tuple[Message, str, bool]:
        
        code_content+=content
        if code_started:
            if code_content[-2:]=='\\n':
                code_content=code_content.replace('\\n', '\n')
            elif content=='"}':
                code_content="\n```\n\n"
                code_started=False
            elif '\\' in code_content:
                return None, code_content, code_started
            else:
                return None, code_content, code_started
        else:
            if code_content=='{"code":"':
                code_started=True
                code_content="\n```python\n"
            else:
                return None, code_content, code_started
        message = Message(
            variant="Code",
            content=code_content
        )
        return message, "", code_started
    
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
                raise e from None
        return chat_result 
        
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatMessageChunk]:
        
        # check that auth token is still valid (refresh otherwise)
        self._validate_env()
        
        prompt = BasePrompt(messages=[BaseMessage(content=message.content, type=message.type) for message in messages])._format_messages_for_chat()
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
            params = {
                    "input":prompt,  
                    "chatbot":self.model_id or "",
                    "thread_id":self.thread_id or "",
                    "user_id": self.user_id or "",
            }
            url = f"streamresponse?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"
            stream=self.client.request(
                method="GET", 
                url=url, 
                stream=True, 
            )
        code_started=False
        image_started=False
        code_content=""
        for part in stream:
            content = part["content"][0] if isinstance(part["content"], list) else part["content"]
            variant = part["variant"]
            if variant!="Image" and image_started:
                message=Message(
                    variant="Image", 
                    content=f'\n\n ![alt text](data:image/png;base64,{base64_string})\n\n'
                )
                image_started=False
                base64_string=""
                yield self._translate_to_chat_generation_chunk(message)
            if variant=="ServerHint":
                if not self.thread_id and "thread_id" in content.keys(): 
                    self.thread_id = content["thread_id"]
                    self.logger.info(f"Started new thread with ID {self.thread_id}")
                continue
            elif variant=="Code":
                message, code_content, code_started=self._process_code_chunk(content, code_content, code_started)
                if not message:
                    continue
            elif variant=="CodeOutput":
                message=Message(
                        variant="CodeOutput",
                        content="\n```\n" +content+"\n```\n"
                )
            elif variant=="Image":
                if not image_started:
                    base64_string=content
                    image_started=True
                    continue
                base64_string+=content
            elif variant=="Assistant":
                message=Message(**part)
            elif variant=="StreamEnd":
                break
            else:
                continue
            yield self._translate_to_chat_generation_chunk(message)

    async def _agenerate(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
        ) -> ChatResult:
                # check that auth token is still valid (refresh otherwise)
                self._validate_env()
                try:
                    stream = self._astream(prompt, stop, run_manager, thread_id=None, **kwargs)
                    result = await agenerate_from_stream(stream)
                except ConnectionError as e:
                    raise e from None
                return result

    async def _astream(
            self,
            messages: List[BaseMessage],
            stop: Optional[List[str]] = None,
            run_manager: Optional[CallbackManagerForLLMRun] = None,
            **kwargs: Any,
        ) -> AsyncIterator[ChatGenerationChunk]:
            
            # check that auth token is still valid (refresh otherwise)
            self._validate_env()
            
            prompt = BasePrompt(messages=[BaseMessage(content=message.content, type=message.type) for message in messages])._format_messages_for_chat()
            # remove any image strings from the prompt to reduce number of tokens drastically
            prompt = re.sub(
                            r"\(data:image/png.*",
                            "('an image was successfully generated')",
                            prompt
            )
            self.logger.debug(f"Calling _stream with prompt: {prompt}")

            if self.debug:
                    class AsyncList(list):
                        async def __aiter__(self):
                            for item in self:
                                time.sleep(0.01)
                                yield item

                    async with aiofiles.open(
                        file=f"{Path(__file__).parent}/example_conversation.json") as fo:
                            stream=AsyncList(json.loads(await fo.read()))
            else:
                thread_id = kwargs.get("thread_id", self.thread_id)
                self.logger.debug(f"Sending request to /streamresponse with following params input={prompt}, chatbot={self.model_id}, thread_id={thread_id}, user={self.user_id}")
                params = {
                        "input":prompt,  
                        "chatbot":self.model_id or "",
                        "thread_id":thread_id or "",
                        "user_id": self.user_id or "",
                }
                url = f"streamresponse?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"
                stream = await self.aclient.request(
                    method="GET", 
                    url=url, 
                    stream=True, 
                )
            code_started=False
            image_started=False
            code_content=""
            async for part in stream:
                content = part["content"][0] if isinstance(part["content"], list) else part["content"]
                variant = part["variant"]
                if variant!="Image" and image_started:
                    message=Message(
                        variant="Image", 
                        content=f'\n\n ![alt text](data:image/png;base64,{base64_string})\n\n'
                    )
                    image_started=False
                    base64_string=""
                    yield self._translate_to_chat_generation_chunk(message)
                if variant=="ServerHint":
                    if not self.thread_id and "thread_id" in content.keys(): 
                        self.thread_id = content["thread_id"]
                        self.logger.info(f"Started new thread with ID {self.thread_id}")
                    continue
                elif variant=="Code":
                    message, code_content, code_started=self._process_code_chunk(content, code_content, code_started)
                    if not message:
                        continue
                    else:
                        code_content=""
                elif variant=="CodeOutput":
                    message=Message(
                            variant="CodeOutput",
                            content="\n```\n" +content+"\n```\n"
                    )
                elif variant=="Image":
                    if not image_started:
                        base64_string=content
                        image_started=True
                        continue
                    base64_string+=content
                elif variant=="Assistant":
                    message=Message(**part)
                elif variant=="StreamEnd":
                    break
                else:
                    continue
                yield self._translate_to_chat_generation_chunk(message)


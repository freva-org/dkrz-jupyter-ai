import asyncio
import json
import logging
import os
import re
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, ClassVar, Optional

import aiofiles
import nest_asyncio
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel, agenerate_from_stream
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.utils import get_from_env
from py_oidc_auth_client import authenticate, TokenStore, Token
from py_oidc_auth_client.exceptions import AuthError
from pydantic import Field, model_validator
from traitlets.config import Application

from ._client import AsyncClient
from ._types import BasePrompt, Message

nest_asyncio.apply()

default_user = os.environ["USER"] if "USER" in os.environ.keys() else "test-user"
default_host = "https://nextgems.dkrz.de"

class FrevaChat(BaseChatModel):

    model_id: str
    host: str = Field(default=default_host)
    user_id: str = Field(default=default_user)
    client_kwargs: dict = {}
    client: AsyncClient = Field(default=None)
    stop: str = Field(default="Generation complete")
    thread_id: str = Field(default=None)
    freva_token_store: TokenStore = Field(default=TokenStore())
    freva_auth_token: Token = Field(default=None)
    logger: logging.Logger = Application.instance().log
    disable_auth: ClassVar[bool] = False
    debug: bool = False

    @property
    def _llm_type(self) -> str:
        return "Freva-GPT"

    @classmethod
    def _update_token_or_store(cls, values: dict) -> dict:
        freva_token_store: TokenStore = values["freva_token_store"]
        current_token: Token = values["freva_auth_token"] 
        stored_token = freva_token_store.get(values["host"])
        if stored_token:
            values["freva_auth_token"] = stored_token
        else:
            freva_token_store.put(host=values["host"], token=current_token)
        return values

    @model_validator(mode="before")
    @classmethod
    def _validate_token_store(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Validate freva token file"""
        # skip if disable_auth setting is set
        values["disable_auth"] = values.get("disable_auth", cls.disable_auth)
        if values["disable_auth"]:
            cls.disable_auth = values["disable_auth"]
            return values
        # check if env var pointing to token store is set
        token_store_path = get_from_env(
            key="freva_token_store",
            env_key="FREVA_TOKEN_STORE",
            default="",
        )
        # load host or set it to default if not part of values
        values["host"] = values.get("host", default_host)
        # load token store
        token_store = TokenStore(token_store_path)
        values["freva_token_store"] = token_store
        auth_token = values.get("freva_auth_token")
        # if freva token store does not exist but token does, write token to store
        if not os.path.exists(token_store._path) and auth_token:
            token_store.put(host=values["host"], token=auth_token)
        elif not auth_token and token_store.get(values["host"]):
            values["freva_auth_token"] = token_store.get(values["host"])
        else:
            raise AuthError(
                "Freva token is not set and token store does not contain it. Please login via the /login slash command first."
            ) from None
        values = cls._update_token_or_store(values)
        return values

    @model_validator(mode="after")
    def _validate_token(self):
        if self.disable_auth:
            self.client = AsyncClient(host=f"{self.host}/api/chatbot", **self.client_kwargs)
            return self
        token_expires_at = datetime.fromtimestamp(self.freva_auth_token["expires"])
        token_refresh_expires_at = datetime.fromtimestamp(self.freva_auth_token["refresh_expires"])
        now = datetime.now()
        if now > token_refresh_expires_at:
            raise AuthError(
                "Refresh token has expired. Please login again using the /login dash command."
            ) from None
        elif now > token_expires_at:
            self.logger.warning(
                "Freva auth token expired. Using refresh token to generate new token and updating token store."
            )
            try:
                self.freva_auth_token = authenticate(
                    host=f"{self.host}/api/freva-nextgen", 
                    store=self.freva_token_store
                )
                self.freva_token_store.put(host=self.host, token=self.freva_auth_token)
            except Exception as e:
                raise AuthError(
                    f"Could not generate a new token from the token file. Please try again or reauthenticate. {e}"
                ) 
        self.client_kwargs = {
            "headers": self.freva_auth_token["headers"]
        }
        self.client = AsyncClient(host=f"{self.host}/api/chatbot", **self.client_kwargs)
        return self

    def _reset(self) -> None:
        self.thread_id = None

    @classmethod
    def _translate_to_chat_generation_chunk(cls, message: Message) -> ChatGenerationChunk:
        return ChatGenerationChunk(message=AIMessageChunk(content=message.content))

    @classmethod
    def _translate_to_chat_generation(cls, message: Message) -> ChatGeneration:
        return ChatGeneration(message=AIMessage(content=message.content))

    @classmethod
    def _process_code_chunk(
        cls, content: str, code_content="", code_started=False
    ) -> tuple[Message | None, str, bool]:

        code_content += content
        if code_started:
            if code_content[-2:] == "\\n":
                code_content = code_content.replace("\\n", "\n")
            elif content == '"}':
                code_content = "\n```\n\n"
                code_started = False
            elif "\\" in code_content:
                return None, code_content, code_started
            else:
                return None, code_content, code_started
        else:
            if code_content == '{"code":"':
                code_started = True
                code_content = "\n```python\n"
            else:
                return None, code_content, code_started
        message = Message(variant="Code", content=code_content)
        return message, "", code_started

    def _generate(
        self,
        prompt: str,
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.logger.debug("Called _generate")
        return asyncio.run(self._agenerate(prompt, stop, run_manager, **kwargs))

    async def _agenerate(
        self,
        prompt: str,
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        # check that auth token is still valid (refresh otherwise)
        self._validate_token()
        try:
            stream = self._astream(prompt, stop, run_manager, thread_id=None, **kwargs)
            result = await agenerate_from_stream(stream)
        except ConnectionError as e:
            raise e from None
        return result

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:

        # check that auth token is still valid (refresh otherwise)
        self._validate_token()

        prompt = BasePrompt(
            messages=[
                BaseMessage(content=message.content, type=message.type) for message in messages
            ]
        )._format_messages_for_chat()
        # remove any image strings from the prompt to reduce number of tokens drastically
        prompt = re.sub(r"\(data:image/png.*", "('an image was successfully generated')", prompt)
        self.logger.debug(f"Calling _stream with prompt: {prompt}")

        if self.debug:
            class AsyncList(list):
                async def __aiter__(self):
                    for item in self:
                        time.sleep(0.01)
                        yield item

            async with aiofiles.open(
                file=f"{Path(__file__).parent}/example_conversation.json"
            ) as fo:
                stream = AsyncList(json.loads(await fo.read()))
        else:
            thread_id = kwargs.get("thread_id", self.thread_id)
            if not thread_id:
                thread_id = await self.client.request(method="GET", url="newthread", stream=False)
            self.logger.debug(
                f"Sending request to /streamresponse with following params input={prompt}, chatbot={self.model_id}, thread_id={thread_id}, user={self.user_id}"
            )
            params = {
                "input": prompt,
                "chatbot": self.model_id or "",
                "thread_id": thread_id or "",
                "user_id": self.user_id or "",
                "store_thread": False,
            }
            url = f"streamresponse?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"
            stream = await self.client.request(
                method="GET",
                url=url,
                stream=True,
            )
        code_started = False
        image_started = False
        code_content = ""
        base64_string = ""
        async for part in stream:
            content = part["content"][0] if isinstance(part["content"], list) else part["content"]
            variant = part["variant"]
            if variant != "Image" and image_started:
                message = Message(
                    variant="Image",
                    content=f"\n\n ![alt text](data:image/png;base64,{base64_string})\n\n",
                )
                image_started = False
                base64_string = ""
                yield self._translate_to_chat_generation_chunk(message)
            if variant == "ServerHint":
                if not self.thread_id and "thread_id" in content.keys():
                    self.thread_id = content["thread_id"]
                    self.logger.info(f"Started new thread with ID {self.thread_id}.")
                continue
            elif variant == "Code":
                message, code_content, code_started = self._process_code_chunk(
                    content, code_content, code_started
                )
                if not message:
                    continue
                else:
                    code_content = ""
            elif variant == "CodeOutput":
                message = Message(variant="CodeOutput", content="\n```\n" + content + "\n```\n")
            elif variant == "Image":
                base64_string += content
                image_started = True
                continue
            elif variant == "Assistant":
                message = Message(**part)
            elif variant == "StreamEnd":
                break
            else:
                continue
            message.content = message.content.replace('\\"', '"')
            yield self._translate_to_chat_generation_chunk(message)

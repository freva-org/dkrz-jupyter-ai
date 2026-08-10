import asyncio
from functools import cached_property
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, AsyncIterator, ClassVar, Optional

import aiofiles
import nest_asyncio
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel, agenerate_from_stream
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field, computed_field
from traitlets.config import Application

from climateclaw_client import AsyncClimateClaw
from ._types import BasePrompt, Message

nest_asyncio.apply()

default_user = os.environ["USER"] if "USER" in os.environ.keys() else "test-user"
default_host = "https://nextgems.dkrz.de"

class ClimateClaw(BaseChatModel):

    model_id: str
    host: str = Field(default=default_host)
    user_id: str = Field(default=default_user)
    stop: str = Field(default="Generation complete")
    thread_id: str = Field(default=None)
    logger: logging.Logger = Application.instance().log
    disable_auth: ClassVar[bool] = False
    debug: bool = False

    @computed_field
    @cached_property
    def client(self) -> AsyncClimateClaw:
        return AsyncClimateClaw(
            base_url=self.host,
            thread_id=self.thread_id,
            interactive_auth=False,
        )

    @property
    def _llm_type(self) -> str:
        return "ClimateClaw"

    def _reset(self) -> None:
        self.client.thread_id = None

    @classmethod
    def _translate_to_chat_generation_chunk(cls, message: Message) -> ChatGenerationChunk:
        return ChatGenerationChunk(message=AIMessageChunk(content=message.content))

    @classmethod
    def _translate_to_chat_generation(cls, message: Message) -> ChatGeneration:
        return ChatGeneration(message=AIMessage(content=message.content))

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
            thread_id = self.client.thread_id
            if not thread_id: 
                thread_id = await self.client.newthread()
            params = {
                "input": prompt,
                "model": self.model_id,
                "thread_id": thread_id,
                "store_thread": False,
            }
            self.logger.debug(
                "Sending request to /streamresponse with following params: " \
                    + ", ".join(f"{key}={value}" for key,value in params.items())
            )
            stream = await self.client.prompt(
                stream = True,
                **params
            )
        async for variant, content in stream.aiter_for_markdown():
            message = Message(variant=variant, content = content)
            yield self._translate_to_chat_generation_chunk(message)

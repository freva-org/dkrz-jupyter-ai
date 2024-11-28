import json
from typing import Any, Dict, List, Optional, Iterator

from PIL import Image
import base64
import io

from langchain_core.pydantic_v1 import (
    BaseModel,
    Field,
    root_validator,
    SecretStr
)
from langchain_core.utils import (
    convert_to_secret_str,
    get_from_dict_or_env,
)

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.llms import LLM
from langchain_core.messages import ChatMessageChunk, ChatMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from ._client import Client
from ._types import Message

class FrevaChat(LLM):

    model_id: str
    base_url:str = Field(default="https://freva.dkrz.de/api/chatbot/")
    auth_key:Optional[SecretStr] = Field(default=None)
    client_kwargs : Optional[Dict] = {}
    _client: Client = Field(default=None)
    stop: str = Field(default="Generation complete")
    thread_id: str = Field(default=None)

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
    ) -> ChatMessage:
        
        r = self._client.request(method="GET", url="/streamresponse", stream=True, params={"input":prompt, "auth_key":self.auth_key})
        return "this is a test!"
        
        
    def _stream(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatMessageChunk]:
        
        if stop is None:
            stop=self.stop

        first_part=True
        code_started=False
        code_content=""
        for part in self._client.request(method="GET", url="/streamresponse", stream=True, params={"input":prompt, "auth_key":self.auth_key.get_secret_value(), "thread_id":self.thread_id or None}):
            content = part["content"]
            print("content:", content)
            if part["variant"]=="ServerHint":
                if stop in content:
                    break
                if first_part:
                    if not self.thread_id: self.thread_id = json.loads(content)["thread_id"]
                    first_part=False
                    continue
                elif code_started:
                    finished_code=json.loads(code_content)
                    print("finished code:", finished_code)
                    message=Message(
                        variant="Code", 
                        content="\n\n```python\n" + finished_code["code"] + "\n```\n\n"
                    )
                    code_started=False
                    code_content=""
                else:
                    continue
            elif part["variant"]=="Code":
                code_content+=content[0]
                code_started=True
                continue
            elif part["variant"]=="Image":
                image_string=part["content"]
                image_bytes=io.BytesIO(base64.b64decode(image_string))
                img=Image.open(image_bytes)
                print("saving image and trying to display it in the chat!")
                img.save("output.png")
                message=Message(variant="Image", content='\n\n ![alt text](output.png "Title")\n\n')
            elif part["variant"]=="Assistant":
                message=Message(**part)
            else:
                continue
            print("message:", message)
            yield self._translate_to_chat_generation_chunk(message)

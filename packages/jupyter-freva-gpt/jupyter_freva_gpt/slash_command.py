import json
import os

from freva_client.utils.auth_utils import DeviceAuthClient
from jupyter_ai.chat_handlers.base import (BaseChatHandler,
                                           SlashCommandRoutingType)
from jupyter_ai.models import HumanChatMessage
from langchain_core.utils import get_from_env

from ._client import Client

fallback_base_url = "https://nextgems.dkrz.de/"

class DocsSlashCommand(BaseChatHandler):
    """
    A slash command implementation that prints out some documentation on the backend.
    """

    id = "docs"
    name = "Docs"
    help = "A command that prints out some documentation on the backend"
    routing_type = SlashCommandRoutingType(slash_id="docs")

    uses_llm = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lm_provider_params=self.config_manager.lm_provider_params
        if lm_provider_params is None:
            base_url = fallback_base_url
        else:
            base_url = self.config_manager.lm_provider_params.get(
                                                "base_url",
                                                fallback_base_url
        )
        api_url = f"{base_url}/api/chatbot"
        self.client : Client = Client(host=api_url, timeout=5)

    async def process_message(self, message: HumanChatMessage):
        self.reply(response=self.client.request(method="GET", url="/docs"),
                   human_msg=message)
        
class LoginSlashCommand(BaseChatHandler):
    """
    A slash command implementation that lets the user login via OAuth2 Device flow.
    """

    id = "login"
    name = "Login"
    help = "A command that lets the user login via OAuth2"
    routing_type = SlashCommandRoutingType(slash_id="login")
    uses_llm = False
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lm_provider_params=self.config_manager.lm_provider_params
        if lm_provider_params is None:
            base_url = fallback_base_url
        else:
            base_url = self.config_manager.lm_provider_params.get(
                                                "base_url",
                                                fallback_base_url
        )
        auth_url = f"{base_url}/api/freva-nextgen/auth/v2"
        device_endpoint = f"{auth_url}/device?offline_access=True"
        token_endpoint = f"{auth_url}/token"
        self.device_auth_client = DeviceAuthClient(token_endpoint=token_endpoint,
                                                   device_endpoint=device_endpoint,
        )
        self.freva_token_file = get_from_env(
            key="freva_token_file",
            env_key="FREVA_TOKEN_FILE",
            default=f"{os.path.join(os.path.expanduser('~'), '.freva_token.json')}"
        )

    async def process_message(self, message: HumanChatMessage):
        init=self.device_auth_client._authorize()
        uri = init.get("verification_uri_complete") or init["verification_uri"]
        self.reply(response=f"Click [here]({uri}) to log in.", human_msg=message)
        with self.pending("Waiting for login to complete", message) as pending_message:
            try:
                token_dict: dict = self.device_auth_client._poll_for_token(
                                                        device_code=init["device_code"], 
                                                        base_interval=int(init.get("interval", 5))
                )
                with open(self.freva_token_file, "w") as f:
                    json.dump(token_dict, f)
                response = "Login successful! You can now use the FrevaGPT provider."
                
            except Exception:
                response = "Error encountered during login. Please try again later."
            self.reply(response=response, human_msg=message)

    async def handle_exc(self, e: Exception, message: HumanChatMessage):
        """
        Handles an exception raised by `self.process_message()`. A default
        implementation is provided, however chat handlers (subclasses) should
        implement this method to provide a more helpful error response.
        """
        await self._default_handle_exc(e, message)
import json
import os

from jupyter_ai.chat_handlers.base import BaseChatHandler, SlashCommandRoutingType
from jupyter_ai.models import HumanChatMessage
from langchain_core.utils import get_from_env
from py_oidc_auth_client import DeviceFlow, TokenStore, Token
from traitlets.config import Application

from climateclaw_client import AsyncClimateClaw

fallback_host = "https://nextgems.dkrz.de/"
logger = Application.instance().log


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
        lm_provider_params = self.config_manager.lm_provider_params
        host = fallback_host
        if lm_provider_params:
            host = self.config_manager.lm_provider_params.get("host", fallback_host)
        api_url = f"{host}"
        self.client: AsyncClimateClaw = AsyncClimateClaw(base_url=api_url, timeout=5)

    async def process_message(self, message: HumanChatMessage):
        self.reply(
            response=await self.client.request(method="GET", url="/docs"), human_msg=message
        )


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
        lm_provider_params = self.config_manager.lm_provider_params
        self.host = fallback_host
        if lm_provider_params:
            self.host = lm_provider_params.get("host", fallback_host)
        auth_url = f"{self.host}/api/freva-nextgen"
        self.device_flow = DeviceFlow(host=auth_url, interactive=False, timeout=120)
        token_store_path = get_from_env(
            key="freva_token_file",
            env_key="FREVA_TOKEN_FILE",
            default="",
        )
        self.freva_token_store = TokenStore(
                                    path=token_store_path,
                                    app_name="climateclaw-client"
        )

    async def process_message(self, message: HumanChatMessage):
        code = await self.device_flow.get_device_code()
        uri = code["uri"]
        self.reply(response=f"Click [here]({uri}) to log in.", human_msg=message)
        with self.pending("Waiting for login to complete", message) as pending_message:
            try:
                token: Token = await self.device_flow.poll(
                    device_code=code["device_code"], interval=code["interval"]
                )
                self.freva_token_store.put(host=self.host, token=token)
                response = "Login successful! You can now use the FrevaGPT provider."

            except Exception as e:
                response = "Error encountered during login. Please try again later."
                logger.error(f"Error encountered during login: {e}")
            self.reply(response=response, human_msg=message)

    async def handle_exc(self, e: Exception, message: HumanChatMessage):
        """
        Handles an exception raised by `self.process_message()`. A default
        implementation is provided, however chat handlers (subclasses) should
        implement this method to provide a more helpful error response.
        """
        await self._default_handle_exc(e, message)

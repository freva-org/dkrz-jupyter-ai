from jupyter_ai.chat_handlers.base import BaseChatHandler, SlashCommandRoutingType
from jupyter_ai.models import HumanChatMessage
from ._client import Client
import json


class PingSlashCommand(BaseChatHandler):
    """
    A test slash command implementation that developers should build from. The
    string used to invoke this command is set by the `slash_id` keyword argument
    in the `routing_type` attribute. The command is mainly implemented in the
    `process_message()` method. See built-in implementations under
    `jupyter_ai/handlers` for further reference.

    The provider is made available to Jupyter AI by the entry point declared in
    `pyproject.toml`. If this class or parent module is renamed, make sure the
    update the entry point there as well.
    """

    id = "ping"
    name = "Ping"
    help = "A command to get the chat backends capabilities"
    routing_type = SlashCommandRoutingType(slash_id="ping")
    base_url = "https://freva.dkrz.de/api/chatbot/"
    client : Client = Client(host=base_url)

    uses_llm = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def process_message(self, message: HumanChatMessage):
        self.reply(response=json.dumps(self.client.request(method="GET", url="/ping"), indent=2))

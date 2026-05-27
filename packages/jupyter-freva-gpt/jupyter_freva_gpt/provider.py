from typing import ClassVar, Dict, List

from jupyter_ai_magics import BaseProvider, Persona
from jupyter_ai_magics.base_provider import CHAT_SYSTEM_PROMPT, HUMAN_MESSAGE_TEMPLATE
from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    PromptTemplate,
    SystemMessagePromptTemplate,
)

from .available_backends import available_backends
from .llm import AuthError, FrevaChat

# path to freva avatar on the jupyter server
FREVAGPT_AVATAR_ROUTE = "api/ai/static/freva_avatar.svg"
# Persona instance for the provider
FrevaGPTPersona = Persona(name="FrevaGPT", avatar_route=FREVAGPT_AVATAR_ROUTE)

# option to force default model
force_default = False


class FrevaGPTProvider(BaseProvider, FrevaChat):
    """
    Implementation of the Freva-GPT provider interface to the Freva-GPT backend for Jupyter AI.
    """

    id: ClassVar[str] = "FrevaGPT"
    """ID for this provider class."""

    name: ClassVar[str] = "Freva GPT Provider"
    """User-facing name of this provider."""

    models: ClassVar[List[str]] = [available_backends[0]] if force_default else available_backends
    """List of supported models by their IDs. """

    model_id_key: ClassVar[str] = "model_id"
    """Kwarg expected by the upstream LangChain provider."""

    model_id_label: ClassVar[str] = "Model ID"
    """Human-readable label of the model ID."""

    manages_history: ClassVar[bool] = True
    """Whether this provider manages its own conversation history upstream. """

    persona: ClassVar[Persona] = FrevaGPTPersona
    """The **persona** of this provider."""

    unsupported_slash_commands: ClassVar[set] = set(("/learn", "/ask"))
    """
    A set of slash commands unsupported by this provider. Unsupported slash
    commands are not shown in the help message, and cannot be used while this
    provider is selected.
    """

    pypi_package_deps: ClassVar[List[str]] = []
    """List of PyPi package dependencies."""

    custom_prompt_templates: Dict[str, str] = {
        "code": "{prompt}\n\nProduce output as source code only, "
        "with no text or explanation before or after it. "
        "Strictly under no circumstances execute the code."
        "Repeat, do NOT execute or run the code."
    }

    @property
    def allows_concurrency(self):
        # supports concurrent messages
        return True

    @classmethod
    def is_not_auth_exc(cls, e: Exception):
        # indicates if a given exception falls within authentication scope
        if isinstance(e, AuthError):
            return True
        return False

    def get_prompt_template(self, format) -> PromptTemplate:
        # overrides some of the default prompt templates
        if format in self.custom_prompt_templates:
            template = self.custom_prompt_templates[format]
            super().update_prompt_template(format, template)
        return super().get_prompt_template(format)

    def get_chat_prompt_template(self):
        name = self.__class__.name
        return ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(CHAT_SYSTEM_PROMPT).format(
                    provider_name=name, local_model_id=self.model_id
                ),
                HumanMessagePromptTemplate.from_template(
                    HUMAN_MESSAGE_TEMPLATE,
                    template_format="jinja2",
                ),
            ]
        )

from typing import ClassVar, List, Dict

from jupyter_ai_magics import BaseProvider, Persona
from jupyter_ai_magics.providers import CHAT_SYSTEM_PROMPT, HUMAN_MESSAGE_TEMPLATE, Field, TextField, MultilineTextField
from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
    PromptTemplate,
    SystemMessagePromptTemplate,
)

from .llm import FrevaChat
from .available_backends import available_backends


FREVAGPT_AVATAR_ROUTE = "api/ai/static/freva_avatar.svg" 
FrevaGPTPersona = Persona(name="FrevaGPT", avatar_route=FREVAGPT_AVATAR_ROUTE)

CHAT_DEFAULT_TEMPLATE = """
{% if context %}
Context:
{{context}}

{% endif %}
Human: {{input}}
AI:"""

force_default = False

class FrevaGPTProvider(BaseProvider, FrevaChat):
    """
    A test model provider implementation for developers to build from. A model
    provider inherits from 2 classes: 1) the `BaseProvider` class from
    `jupyter_ai`, and 2) an LLM class from `langchain`, i.e. a class inheriting
    from `LLM` or `BaseChatModel`.

    Any custom model first requires a `langchain` LLM class implementation.
    Please import one from `langchain`, or refer to the `langchain` docs for
    instructions on how to write your own. We offer an example in `./llm.py` for
    testing.

    To create a custom model provider from an existing `langchain`
    implementation, developers should edit this class' declaration to

    ```
    class TestModelProvider(BaseProvider, <langchain-llm-class>):
        ...
    ```

    Developers should fill in each of the below required class attributes.
    As the implementation is provided by the inherited LLM class, developers
    generally don't need to implement any methods. See the built-in
    implementations in `jupyter_ai_magics.providers.py` for further reference.

    The provider is made available to Jupyter AI by the entry point declared in
    `pyproject.toml`. If this class or parent module is renamed, make sure the
    update the entry point there as well.
    """

    id: ClassVar[str] = "FrevaGPT"
    """ID for this provider class."""

    name: ClassVar[str] = "Freva GPT Provider"
    """User-facing name of this provider."""

    models: ClassVar[List[str]] = [available_backends[0]] if force_default else available_backends
    """List of supported models by their IDs. For registry providers, this will
    be just ["*"]."""

    fields: ClassVar[List[Field]] = []
    """User inputs expected by this provider when initializing it. Each `Field` `f`
    should be passed in the constructor as a keyword argument, keyed by `f.key`."""

    help: ClassVar[str] = None
    """Text to display in lieu of a model list for a registry provider that does
    not provide a list of models."""

    model_id_key: ClassVar[str] = "model_id"
    """Kwarg expected by the upstream LangChain provider."""

    model_id_label: ClassVar[str] = "Model ID"
    """Human-readable label of the model ID."""

    manages_history: ClassVar[bool] = True 
    """Whether this provider manages its own conversation history upstream. If
    set to `True`, Jupyter AI will not pass the chat history to this provider
    when invoked."""

    persona: ClassVar[Persona] = FrevaGPTPersona
    """
    The **persona** of this provider, a struct that defines the name and avatar
    shown on agent replies in the chat UI. When set to `None`, `jupyter-ai` will
    choose a default persona when rendering agent messages by this provider.
    """

    unsupported_slash_commands: ClassVar[set] = set(("/learn", "/ask", "/test"))
    """
    A set of slash commands unsupported by this provider. Unsupported slash
    commands are not shown in the help message, and cannot be used while this
    provider is selected.
    """

    pypi_package_deps: ClassVar[List[str]] = []
    """List of PyPi package dependencies."""

    registry: ClassVar[bool] = False
    """Whether this provider is a registry provider."""

    custom_prompt_templates: Dict[str, PromptTemplate] = {
        "code": PromptTemplate.from_template(
                "{prompt}\n\nProduce output as source code only, "
                "with no text or explanation before or after it. "
                "Strictly under no circumstances execute the code."
                "Repeat, do NOT execute or run the code."
            )
    }

    @property
    def allows_concurrency(self):
        # At present, FrevaGPT providers fail with concurrent messages.
        return False
    
    def get_prompt_template(self, format) -> PromptTemplate:
        # override parent class method to ensure custom prompt templates are used
        if format in self.custom_prompt_templates.keys():
            return self.custom_prompt_templates[format]
        return super().get_prompt_template(format)

    def get_chat_prompt_template(self) -> PromptTemplate:
        """
        Produce a prompt template optimised for chat conversation.
        The template should take two variables: history and input.
        """
        name = self.__class__.name
        if self.is_chat_provider:
            return ChatPromptTemplate.from_messages(
                [
                    SystemMessagePromptTemplate.from_template(
                        CHAT_SYSTEM_PROMPT
                    ).format(provider_name=name, local_model_id=self.model_id),
                    HumanMessagePromptTemplate.from_template(
                        HUMAN_MESSAGE_TEMPLATE,
                        template_format="jinja2",
                    ),
                ]
            )
        else:
            return PromptTemplate(
                input_variables=["input", "context"],
                template=CHAT_SYSTEM_PROMPT.format(
                    provider_name=name, local_model_id=self.model_id
                )
                + "\n\n"
                + CHAT_DEFAULT_TEMPLATE,
                template_format="jinja2",
            )

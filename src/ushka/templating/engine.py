"""This module provides advanced templating functionality using Jinja2.

It allows registering custom filters, global variables, and context processors.
Signature style: Django-like (request, template_name, context).
"""

import asyncio
import typing
from pathlib import Path

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

from ushka.utils.flash import get_flashed_messages

if typing.TYPE_CHECKING:
    from ushka.http.request import Request

ContextProcessor = typing.Callable[
    ["Request"], typing.Awaitable[typing.Dict[str, typing.Any]]
]


class UshkaTemplates:
    """Manages Jinja2 templating for the Ushka framework.

    This class provides a centralized system for rendering templates,
    supporting custom filters, global variables, and context processors.
    It automatically loads templates from both the project's `templates`
    directory and Ushka's internal default templates.
    """

    def __init__(self, context_processors: typing.List[ContextProcessor] = None):
        """Initializes the UshkaTemplates engine.

        Sets up the Jinja2 environment with a `ChoiceLoader` to prioritize
        project-specific templates over framework defaults.

        Parameters
        ----------
        context_processors : list of ContextProcessor, optional
            A list of callable context processors. Each processor will be
            executed before rendering to inject additional variables into
            the template context. Defaults to an empty list.
        """
        project_templates = Path.cwd() / "templates"
        framework_templates = (
            Path(__file__).parent.parent / "internal/default_templates"
        )

        self.loader = ChoiceLoader(
            [
                FileSystemLoader(str(project_templates)),
                FileSystemLoader(str(framework_templates)),
            ]
        )

        self.env = Environment(
            loader=self.loader,
            autoescape=select_autoescape(["html", "xml"]),
            enable_async=True,
        )

        self.context_processors = context_processors or []

    def add_filter(self, name: str, func: typing.Callable) -> None:
        """Adds a custom filter to the Jinja2 environment.

        Parameters
        ----------
        name : str
            The name of the filter as it will be used in templates.
        func : Callable
            The Python callable (function) that implements the filter logic.
        """
        self.env.filters[name] = func

    def add_global(self, name: str, value: typing.Any) -> None:
        """Adds a global variable to the Jinja2 environment.

        This variable will be accessible in all templates.

        Parameters
        ----------
        name : str
            The name of the global variable.
        value : Any
            The value to assign to the global variable.
        """
        self.env.globals[name] = value

    def add_context_processor(self, func: ContextProcessor) -> None:
        """Adds a context processor to the templating engine.

        Context processors are callables that return a dictionary of variables.
        These variables are automatically added to the context of every template
        rendered by this engine.

        Parameters
        ----------
        func : ContextProcessor
            A callable that takes a `Request` object and returns a dictionary
            (or an awaitable that returns a dictionary) of context variables.
        """
        self.context_processors.append(func)

    async def render(
        self,
        request: "Request",
        template_name: str,
        context: typing.Dict[str, typing.Any] = None,
    ) -> str:
        """Renders a Jinja2 template with the given context and request data.

        This method processes all registered context processors before rendering
        to enrich the template context.

        Parameters
        ----------
        request : Request
            The incoming HTTP request object, which is also added to the template context.
        template_name : str
            The path to the template file relative to the configured template loaders.
        context : Dict[str, Any], optional
            A dictionary of variables to pass to the template. Defaults to an empty dictionary.

        Returns
        -------
        str
            The rendered template as a string.
        """
        if context is None:
            context = {}

        context["request"] = request

        # Context Processors
        for processor in self.context_processors:
            if asyncio.iscoroutinefunction(processor):
                extra = await processor(request)
            else:
                extra = processor(request)

            if extra:
                context.update(extra)

        template = self.env.get_template(template_name)
        return await template.render_async(**context)


async def flash_processor(request: "Request") -> dict:
    """A context processor that injects flashed messages into the template context.

    Parameters
    ----------
    request : Request
        The incoming HTTP request object, from which flashed messages are retrieved.

    Returns
    -------
    dict
        A dictionary containing "messages" key, whose value is a list of
        (category, message) tuples retrieved from the session.
    """
    return {"messages": get_flashed_messages(request, with_categories=True)}


_engine = UshkaTemplates(context_processors=[flash_processor])
engine = _engine


async def render(
    request: "Request", template_name: str, context: typing.Dict[str, typing.Any] = None
) -> str:
    """Renders an HTML template using the global templating engine instance.

    This is a convenience function that delegates to `UshkaTemplates.render()`.

    Parameters
    ----------
    request : Request
        The incoming HTTP request object.
    template_name : str
        The path to the template file (e.g., "index.html").
    context : Dict[str, Any], optional
        A dictionary of variables to pass to the template. Defaults to an empty dictionary.

    Returns
    -------
    str
        The rendered template as a string.
    """
    return await _engine.render(request, template_name, context)

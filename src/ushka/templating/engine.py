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
    def __init__(self, context_processors: typing.List[ContextProcessor] = None):
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
        self.env.filters[name] = func

    def add_global(self, name: str, value: typing.Any) -> None:
        self.env.globals[name] = value

    def add_context_processor(self, func: ContextProcessor) -> None:
        self.context_processors.append(func)

    async def render(
        self,
        request: "Request",
        template_name: str,
        context: typing.Dict[str, typing.Any] = None,
    ) -> str:
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
    return {"messages": get_flashed_messages(request, with_categories=True)}


_engine = UshkaTemplates(context_processors=[flash_processor])
engine = _engine


async def render(
    request: "Request", template_name: str, context: typing.Dict[str, typing.Any] = None
) -> str:
    """
    Renders an HTML template.
    Usage: return await render(request, "index.html", {"foo": "bar"})
    """
    return await _engine.render(request, template_name, context)

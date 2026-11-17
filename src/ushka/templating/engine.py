"""This module provides advanced templating functionality using Jinja2.

It allows registering custom filters, global variables, and context processors.
Signature style: Django-like (request, template_name, context).
"""

import inspect
import typing
from pathlib import Path

from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    StrictUndefined,
    Undefined,
    select_autoescape,
)

import ushka.i18n as i18n

from ushka.guard import check_markup
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

        self._project_loader = FileSystemLoader(str(project_templates))
        self.loader = ChoiceLoader(
            [self._project_loader, FileSystemLoader(str(framework_templates))]
        )

        self.env = Environment(
            loader=self.loader,
            autoescape=select_autoescape(["html", "xml"]),
            enable_async=True,
            extensions=["jinja2.ext.i18n"],
        )
        # `_()`, `gettext`, `ngettext` and `{% trans %}` follow the language of
        # the request being served (a contextvar), never a global one.
        self.env.install_gettext_callables(
            i18n.template_gettext,
            i18n.template_ngettext,
            newstyle=True,
            pgettext=i18n.template_pgettext,
            npgettext=i18n.template_npgettext,
        )
        #: Whether a missing variable raises (see `configure`).
        self.strict = False
        self._configured_for: typing.Any = None

        # Ushka Guard: `{{ value|safe }}` on client data is the classic way to
        # reintroduce XSS into an autoescaped template; refuse it.
        builtin_safe = self.env.filters["safe"]

        def guarded_safe(value):
            check_markup(value)
            return builtin_safe(value)

        self.env.filters["safe"] = guarded_safe

        self.context_processors = context_processors or []

    def configure(self, config: typing.Any) -> None:
        """Applies the settings that belong to the engine.

        A variable that does not exist raises ``UndefinedError`` (with the
        template and line in the traceback) when ``[app] strict_templates`` is
        on or the app runs in debug mode; otherwise it renders as empty, as
        Jinja does by default. The app calls this when it starts, and `render`
        repeats it when a different app renders, so the mode never leaks from
        one app (or test) to the next.
        """
        self.strict = bool(config.get("app_strict_templates") or config.get("app_debug"))
        self.env.undefined = StrictUndefined if self.strict else Undefined
        self._configured_for = config

    def set_project_dir(self, path: typing.Union[str, Path]) -> None:
        """Points the project loader at `path` (the app calls this with
        ``<app dir>/templates``). Framework templates stay as the fallback."""
        self._project_loader.searchpath = [str(path)]
        if self.env.cache is not None:
            self.env.cache.clear()

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
        config = getattr(getattr(request, "app", None), "config", None)
        if config is not None and config is not self._configured_for:
            self.configure(config)
        for name, value in i18n.template_variables().items():
            context.setdefault(name, value)

        # Context Processors
        for processor in self.context_processors:
            if inspect.iscoroutinefunction(processor):
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

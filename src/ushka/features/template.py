"""This module provides templating functionality using Jinja2.

It configures a Jinja2 environment that searches for templates first in the
project's 'templates' directory and then falls back to the framework's
internal default templates. Auto-escaping is enabled for HTML and XML files
to prevent XSS vulnerabilities.
"""

from pathlib import Path
from typing import Any, Dict

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

# Set up template loaders
project_templates = Path.cwd() / "templates"
framework_templates = Path(__file__).parent.parent / "internal/default_templates"

# Configure Jinja2 environment
env = Environment(
    loader=ChoiceLoader(
        [
            FileSystemLoader(str(project_templates)),
            FileSystemLoader(str(framework_templates)),
        ]
    ),
    autoescape=select_autoescape(["html", "xml"]),
)


def render(template_name: str, context: Dict[str, Any] = None) -> str:
    """Renders a Jinja2 template with the given context.

    Args:
        template_name: The name of the template file to render.
        context: A dictionary of variables to pass to the template.

    Returns:
        The rendered template as an HTML string.
    """
    if context is None:
        context = {}
    template = env.get_template(template_name)
    return template.render(context)

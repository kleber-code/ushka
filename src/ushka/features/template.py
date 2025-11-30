# template.py
from pathlib import Path

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

project_templates = Path.cwd() / "templates"
framework_templates = Path(__file__).parent.parent / "internal/default_templates"
print(framework_templates)
env = Environment(
    loader=ChoiceLoader(
        [
            FileSystemLoader(str(project_templates)),
            FileSystemLoader(str(framework_templates)),
        ]
    ),
    autoescape=select_autoescape(["html", "xml"]),
)


def render(template_name: str, context: dict) -> str:
    template = env.get_template(template_name)
    return template.render(context)

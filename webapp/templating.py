"""Shared Jinja2 templates instance (kept separate to avoid circular imports)."""
import os

from fastapi.templating import Jinja2Templates

from webapp.auth import is_admin

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Expose a couple of helpers to every template.
templates.env.globals["is_admin"] = is_admin


def render(name: str, context: dict, **kwargs):
    """Render a template using the current Starlette signature
    ``TemplateResponse(request, name, context, ...)`` while letting callers keep passing
    ``request`` inside ``context`` (the style used throughout the routers)."""
    request = context["request"]
    return templates.TemplateResponse(request, name, context, **kwargs)

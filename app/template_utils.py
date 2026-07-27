"""Custom Jinja2 template utilities.

Avoids Starlette's Jinja2Templates wrapper which has LRU cache
compatibility issues on Python 3.14.
"""

from pathlib import Path
from decimal import Decimal
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
AISEARCH_TEMPLATE_DIR = Path(__file__).resolve().parent / "aisearch" / "templates"
PLMASSISTANT_TEMPLATE_DIR = Path(__file__).resolve().parent / "plmassistant" / "templates"

# Single shared environment with cache disabled.
# Loads templates from app/templates/, aisearch/templates/, and plmassistant/templates/
_env = Environment(
    loader=FileSystemLoader([str(TEMPLATE_DIR), str(AISEARCH_TEMPLATE_DIR), str(PLMASSISTANT_TEMPLATE_DIR)]),
    autoescape=True,
    cache_size=0,  # Disable cache to avoid unhashable type issues
)


def fmt_currency(value):
    """Format a number as currency string (e.g. $1,234.56)."""
    if value is None:
        return "-"
    try:
        v = float(value)
        return f"${v:,.2f}"
    except (ValueError, TypeError):
        return str(value)


def fmt_number(value):
    """Format a number as a clean string."""
    if value is None:
        return "-"
    try:
        v = float(value)
        return f"{v:,.2f}"
    except (ValueError, TypeError):
        return str(value)


_env.filters["currency"] = fmt_currency
_env.filters["fmtnum"] = fmt_number


def render(template_name: str, **context) -> str:
    """Render a template and return HTML string."""
    template = _env.get_template(template_name)
    return template.render(**context)

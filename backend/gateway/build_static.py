"""Render the gateway pages into a static bundle for external web hosting.

The gateway templates are server-rendered; static hosts need plain HTML.
This script renders every page for every edition WITHOUT duplicating
markup: edition folders are generated from the shared templates, and an
edition package (gateway/<edition>/templates) overrides any page simply by
defining it.

Output layout:
    <out>/
      index.html                 gateway default info page (entry point)
      404.html                   branded not-found page
      style/style.css            single stylesheet
      <edition>/index.html       workspace landing per edition
      signin.html                one neutral sign-in page

Editions come from configuration (EDITIONS in .env, see gateway/settings.py);
adding one there renders its pages automatically.

Bundle: <out>.tar.gz next to the output folder (upload to hosting).

Usage:
    python -m gateway.build_static [--out setup/public_html]   (from backend/)
    python backend/gateway/build_static.py [--out setup/public_html]
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import jinja2
from jinja2 import ChoiceLoader, FileSystemLoader

if __package__ in (None, ""):  # executed as a plain script
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from gateway import settings
else:
    from . import settings

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]
COMMON_TEMPLATES = GATEWAY_DIR / "templates"
STATIC_DIR = GATEWAY_DIR / "static"

EDITIONS = settings.EDITIONS
DEFAULT_TENANT = "plm-iq"

NOT_FOUND_MESSAGE = (
    "The address you opened could not be matched to a PLM-IQ workspace. "
    "Please contact your system administrator."
)


def make_env(edition: str | None = None) -> jinja2.Environment:
    loaders = []
    if edition:
        edition_dir = GATEWAY_DIR / edition / "templates"
        if edition_dir.is_dir():
            loaders.append(FileSystemLoader(edition_dir))
    loaders.append(FileSystemLoader(COMMON_TEMPLATES))
    return jinja2.Environment(loader=ChoiceLoader(loaders), autoescape=True)


def workspace_ctx(edition: str) -> SimpleNamespace:
    return SimpleNamespace(
        tenant=DEFAULT_TENANT,
        edition=edition,
        edition_label=settings.edition_label(edition),
        host=f"{DEFAULT_TENANT}.{edition}.example.com",
        valid=True,
    )


INVALID_CTX = SimpleNamespace(valid=False, host="", tenant="", edition="", edition_label="")


def write(env: jinja2.Environment, template_name: str, out_path: Path, context: dict, out_dir: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = env.get_template(template_name).render(**context)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"  + {out_path.relative_to(out_dir)}")


def build(out_dir: Path) -> Path:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    common_env = make_env()
    nav = [{"name": e, "label": settings.edition_label(e), "url": f"{e}/"} for e in EDITIONS]

    print(f"Rendering static site -> {out_dir}")
    write(
        common_env,
        "default.html",
        out_dir / "index.html",
        {"ctx": INVALID_CTX, "editions_nav": nav, "links": {"brand": "index.html", "css": "style/style.css"}},
        out_dir,
    )
    write(
        common_env,
        "not_found.html",
        out_dir / "404.html",
        {
            "ctx": INVALID_CTX,
            "message": NOT_FOUND_MESSAGE,
            "path": "",
            "links": {"brand": "index.html", "css": "style/style.css"},
        },
        out_dir,
    )

    for edition in EDITIONS:
        env = make_env(edition)
        ctx = workspace_ctx(edition)
        links = {
            "brand": "../",
            "signin": "../signin.html",
            "dashboard": "../signin.html",  # static site has no app dashboard yet
            "css": "../style/style.css",
        }
        write(env, "home.html", out_dir / edition / "index.html", {"ctx": ctx, "links": links}, out_dir)

    # One neutral sign-in page for all editions: no edition branding, the
    # tenant box starts empty so visitors identify their own organization.
    write(
        common_env,
        "signin.html",
        out_dir / "signin.html",
        {"ctx": INVALID_CTX, "links": {"brand": "index.html", "css": "style/style.css"}},
        out_dir,
    )

    write(
        common_env,
        "help.html",
        out_dir / "help.html",
        {"ctx": INVALID_CTX, "links": {"brand": "index.html", "css": "style/style.css"}},
        out_dir,
    )

    static_out = out_dir / "style"
    static_out.mkdir()
    shutil.copy2(STATIC_DIR / "style.css", static_out / "style.css")
    print(f"  + {static_out.relative_to(out_dir) / 'style.css'}")
    return out_dir


def bundle(out_dir: Path) -> Path:
    tar_path = out_dir.with_suffix(".tar.gz")
    with tarfile.open(tar_path, "w:gz") as tar:
        for item in sorted(out_dir.rglob("*")):
            if item.is_file():  # dirs are created implicitly by their file paths
                tar.add(item, arcname=item.relative_to(out_dir))
    size_kb = tar_path.stat().st_size / 1024
    print(f"\nBundle ready: {tar_path} ({size_kb:.1f} KB)")
    return tar_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="setup/public_html", help="output directory")
    args = parser.parse_args()

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir

    build(out_dir)
    bundle(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

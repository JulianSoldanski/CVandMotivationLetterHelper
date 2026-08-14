"""Prompt texts, kept out of the Python source.

Every prompt lives next to this file as a .md file; Python only fills in the
placeholders and sends the result. Placeholders are `$name` / `${name}`
(string.Template) rather than str.format, so the JSON examples inside the
prompts keep their literal braces and stay readable as prompts.

Files are read on every call on purpose — a prompt can be edited and retried
without restarting the server, and the read is nothing next to the Gemini call
that follows.
"""
from pathlib import Path
from string import Template

_DIR = Path(__file__).parent


def render(name: str, **values) -> str:
    """The prompt in `<name>.md`, placeholders filled in.

    Raises KeyError if the .md file expects a placeholder the caller did not
    pass, so a renamed variable fails loudly instead of shipping a prompt with
    a literal `$foo` in it.
    """
    text = (_DIR / f"{name}.md").read_text(encoding="utf-8")
    return Template(text).substitute(**values)

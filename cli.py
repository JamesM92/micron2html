"""
CLI tool: convert a .mu Micron file to HTML or plain text.

Usage:
    python -m micron2html.cli input.mu > output.html
    python -m micron2html.cli input.mu -o output.html
    cat page.mu | python -m micron2html.cli -
    python -m micron2html.cli input.mu --format text
"""

import argparse
import os
import sys
from .converter import MicronConverter

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
{css}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def _bundled_css() -> str:
    """Read the bundled dark-terminal stylesheet that ships with the package."""
    css_path = os.path.join(os.path.dirname(__file__), "micron-meshchat.css")
    try:
        with open(css_path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert Micron (.mu) markup to HTML or plain text"
    )
    parser.add_argument(
        "input",
        metavar="FILE",
        help="Input .mu file (use - for stdin)",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="FILE",
        default=None,
        help="Output file (default: stdout)",
    )
    parser.add_argument(
        "-f", "--format",
        choices=["html", "text"],
        default="html",
        help="Output format (default: html)",
    )
    parser.add_argument(
        "--fragment",
        action="store_true",
        help="HTML mode only: emit a fragment instead of a full <html> page",
    )
    parser.add_argument(
        "--node-hash",
        default="",
        metavar="HASH",
        help="Node destination hash (used to build internal link hrefs)",
    )
    args = parser.parse_args(argv)

    if args.input == "-":
        text = sys.stdin.read()
        title = "Micron Page"
    else:
        with open(args.input, "r", encoding="utf-8") as fh:
            text = fh.read()
        title = os.path.basename(args.input)

    converter = MicronConverter()

    if args.format == "text":
        output = converter.to_text(text)
        if not output.endswith("\n"):
            output += "\n"
    else:
        body = converter.convert(text, node_hash=args.node_hash)
        if args.fragment:
            output = body
        else:
            output = _HTML_TEMPLATE.format(title=title, css=_bundled_css(), body=body)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(output)
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()

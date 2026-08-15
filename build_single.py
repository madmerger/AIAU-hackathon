"""Bundle the dashboard into one self-contained HTML file.

CSS, JS, Chart.js, the logo and a data snapshot are inlined so the file can be
opened directly (file://) and edited by hand. When served from the dashboard
server it still refreshes from /api/data.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
DEFAULT_SOURCE = "http://localhost:8787/api/data"
DEFAULT_OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")


def read_static(name: str) -> str:
    with open(os.path.join(STATIC_DIR, name), encoding="utf-8") as handle:
        return handle.read()


def logo_data_uri() -> str:
    with open(os.path.join(STATIC_DIR, "logo.png"), "rb") as handle:
        return "data:image/png;base64," + base64.b64encode(handle.read()).decode("ascii")


def fetch_snapshot(url: str) -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except OSError as error:
        print(f"warning: snapshot fetch failed ({error})", file=sys.stderr)
        return None


def build(snapshot_url: str, output_path: str) -> None:
    html = read_static("index.html")
    styles = read_static("styles.css")
    chart_js = read_static("chart.umd.min.js")
    app_js = read_static("app.js")
    snapshot = fetch_snapshot(snapshot_url)

    html = html.replace('<link rel="icon" href="/static/logo.png" />', f'<link rel="icon" href="{logo_data_uri()}" />')
    html = html.replace('src="/static/logo.png"', f'src="{logo_data_uri()}"')
    html = html.replace(
        '<link rel="stylesheet" href="/static/styles.css" />',
        f"<style>\n{styles}\n</style>",
    )
    html = html.replace(
        '<script src="/static/chart.umd.min.js"></script>\n<script src="/static/app.js"></script>',
        "<script>\n{chart}\n</script>\n<script>\nwindow.EMBEDDED_DATA = {data};\n</script>\n<script>\n{app}\n</script>".format(
            chart=chart_js,
            data=json.dumps(snapshot, ensure_ascii=False) if snapshot else "null",
            app=app_js,
        ),
    )

    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(html)
    print(f"wrote {output_path} ({os.path.getsize(output_path) / 1024:.0f} KB)")


if __name__ == "__main__":
    build(
        sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SOURCE,
        sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT,
    )

"""Web 层：先只有健康检查与只读设置接口。"""

from __future__ import annotations

import time
from string import Template

from aiohttp import web

from .. import APP_NAME, UPSTREAM, VERSION
from ..config import Config

CONFIG_KEY: web.AppKey[Config] = web.AppKey("config", Config)

INDEX_HTML = Template("""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$app</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 14px/1.6 system-ui, sans-serif; margin: 2rem auto; max-width: 46rem; padding: 0 1rem; }
  h1 { font-size: 1.4rem; margin-bottom: .2rem; }
  .muted { opacity: .65; }
  table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
  th, td { text-align: left; padding: .3rem .5rem; border-bottom: 1px solid rgba(128,128,128,.25); }
  code { font-family: ui-monospace, monospace; }
</style>
</head>
<body>
<h1>$app</h1>
<p class="muted">版本 $version · 基线 $upstream</p>
<table>
  <tr><th>键</th><th>值</th><th>来源</th></tr>
  $rows
</table>
<p class="muted">接口：<code>/api/health</code> · <code>/api/settings</code></p>
</body>
</html>
""")


def create_app(config: Config) -> web.Application:
    started = time.time()

    async def index(_: web.Request) -> web.Response:
        rows = "\n".join(
            f"<tr><td><code>{item['key']}</code></td>"
            f"<td>{_fmt(item['value'])}</td><td>{item['source']}</td></tr>"
            for item in config.as_public()
            if not item["key"].startswith("auth.password")
        )
        return web.Response(
            text=INDEX_HTML.substitute(
                app=APP_NAME,
                version=VERSION,
                upstream=UPSTREAM,
                rows=rows,
            ),
            content_type="text/html",
        )

    async def health(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "ok": True,
                "app": APP_NAME,
                "version": VERSION,
                "upstream": UPSTREAM,
                "uptime_s": round(time.time() - started, 1),
                "config_path": str(config.path) if config.path else None,
            }
        )

    async def settings(_: web.Request) -> web.Response:
        return web.json_response({"items": config.as_public(), "errors": config.validate()})

    async def not_found(_: web.Request) -> web.Response:
        return web.json_response({"ok": False, "error": "not found"}, status=404)

    app = web.Application()
    app[CONFIG_KEY] = config
    app.router.add_get("/", index)
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/settings", settings)
    app.router.add_route("*", "/{tail:.*}", not_found)
    return app


def _fmt(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "(空)"
    text = str(value)
    if len(text) > 60:
        text = text[:57] + "..."
    return text

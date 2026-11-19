"""Web 层：登录、实例管理、控制台 WebSocket。

单人使用，一条会话一条控制台连接就够用，不做多用户与房间。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web

from .. import APP_NAME, UPSTREAM, VERSION
from ..auth import COOKIE_NAME, SessionStore, verify_password
from ..config import Config
from ..instances import InstanceNotFound, InstanceProcess, InstanceRegistry, probe, scan

CONFIG_KEY: web.AppKey[Config] = web.AppKey("config", Config)
REGISTRY_KEY: web.AppKey[InstanceRegistry] = web.AppKey("registry", InstanceRegistry)
SESSIONS_KEY: web.AppKey[SessionStore] = web.AppKey("sessions", SessionStore)
PROCESSES_KEY: web.AppKey[dict[str, InstanceProcess]] = web.AppKey("processes", dict)
LOG_DIR_KEY: web.AppKey[Path] = web.AppKey("log_dir", Path)

SESSION_KEY: web.RequestKey = web.RequestKey("session", object)

PUBLIC_PATHS = {"/login", "/api/login", "/api/health", "/favicon.ico"}

LOGIN_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>登录 · {{app}}</title>
<style>
 body{font:14px/1.6 system-ui,sans-serif;display:grid;place-items:center;height:100vh;margin:0;background:#0f1115;color:#e6e6e6}
 form{background:#171a21;padding:28px;border-radius:10px;width:300px;box-shadow:0 8px 30px #0006}
 h1{font-size:1.1rem;margin:0 0 16px}
 label{display:block;margin:10px 0 4px;font-size:.85rem;opacity:.75}
 input{width:100%;box-sizing:border-box;padding:8px;border-radius:6px;border:1px solid #333;background:#0f1115;color:#e6e6e6}
 button{margin-top:16px;width:100%;padding:9px;border:0;border-radius:6px;background:#2f6fed;color:#fff;font-size:.95rem;cursor:pointer}
 .err{color:#ff6b6b;margin-top:10px;font-size:.85rem;min-height:1em}
</style></head>
<body>
<form method="post" action="/api/login">
  <h1>{{app}} 登录</h1>
  <label for="u">账号</label><input id="u" name="username" value="{{user}}name" autocomplete="username">
  <label for="p">密码</label><input id="p" name="password" type="password" autocomplete="current-password" autofocus>
  <button type="submit">登录</button>
  <div class="err">{{error}}</div>
</form>
</body></html>
"""

INDEX_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{app}}</title>
<style>
 :root{color-scheme:dark}
 body{margin:0;font:14px/1.55 system-ui,sans-serif;background:#0f1115;color:#e6e6e6}
 header{display:flex;justify-content:space-between;align-items:center;padding:12px 18px;border-bottom:1px solid #23262d}
 header h1{font-size:1rem;margin:0;font-weight:600}
 main{display:grid;grid-template-columns:300px 1fr;height:calc(100vh - 49px)}
 aside{border-right:1px solid #23262d;overflow:auto;padding:10px}
 .inst{padding:10px;border:1px solid #23262d;border-radius:8px;margin-bottom:8px;cursor:pointer}
 .inst.active{border-color:#2f6fed}
 .row{display:flex;justify-content:space-between;align-items:center;gap:8px}
 .state{font-size:.78rem;padding:1px 7px;border-radius:99px;background:#2a2f3a}
 .state.running{background:#17543b;color:#8ff0c0}
 .state.crashed{background:#5a1d1d;color:#ffb4b4}
 button{padding:4px 9px;border-radius:6px;border:1px solid #333;background:#1b1f27;color:#e6e6e6;cursor:pointer}
 button:hover{border-color:#2f6fed}
 section{display:flex;flex-direction:column;min-width:0}
 #console{flex:1;margin:0;padding:12px;overflow:auto;white-space:pre-wrap;word-break:break-all;font:12px/1.5 ui-monospace,monospace;background:#0b0d11}
 #cmd{display:flex;gap:8px;padding:10px;border-top:1px solid #23262d}
 #cmd input{flex:1;padding:8px;border-radius:6px;border:1px solid #333;background:#141821;color:#e6e6e6}
 .muted{opacity:.6}
</style></head>
<body>
<header><h1>{{app}} <span class="muted">{{version}}</span></h1>
<div><span class="muted">{{user}}</span> <button id="logout">退出</button></div></header>
<main>
 <aside id="list"><p class="muted">加载中…</p></aside>
 <section>
  <pre id="console"></pre>
  <div id="cmd"><input id="text" placeholder="输入命令后回车（R1 阶段不做白名单）" disabled>
  <button id="send" disabled>发送</button></div>
 </section>
</main>
<script>
const state={current:null, ws:null};
const $=id=>document.getElementById(id);
function badge(s){return `<span class="state ${s}">${s}</span>`}
async function refresh(){
  const r=await fetch('/api/instances'); if(!r.ok) return;
  const data=await r.json(); const box=$('list'); box.innerHTML='';
  if(!data.instances.length){box.innerHTML='<p class="muted">还没有实例。用命令行 hoshi instances add 添加。</p>';return}
  for(const it of data.instances){
    const div=document.createElement('div');
    div.className='inst'+(state.current===it.id?' active':'');
    div.innerHTML=`<div class="row"><b>${it.name}</b>${badge(it.state)}</div>
      <div class="muted" style="font-size:.78rem">${it.directory}</div>
      <div class="row" style="margin-top:6px">
        <button data-act="start">启动</button><button data-act="stop">停止</button><button data-act="kill">强杀</button>
      </div>`;
    div.onclick=e=>{if(e.target.dataset.act)return;select(it.id)};
    div.querySelectorAll('button').forEach(b=>b.onclick=async ev=>{
      ev.stopPropagation();
      await fetch(`/api/instances/${it.id}/${b.dataset.act}`,{method:'POST'});
      setTimeout(refresh,300);
    });
    box.appendChild(div);
  }
}
async function select(id){
  state.current=id; await refresh();
  if(state.ws){state.ws.close();state.ws=null}
  const r=await fetch(`/api/instances/${id}/log?lines=300`); const data=await r.json();
  $('console').textContent=(data.lines||[]).join('\n')+'\n';
  const proto=location.protocol==='https:'?'wss:':'ws:';
  const ws=new WebSocket(`${proto}//${location.host}/ws/console/${id}`);
  state.ws=ws;
  ws.onmessage=ev=>{
    const m=JSON.parse(ev.data);
    if(m.type==='snapshot'){$('console').textContent=m.lines.join('\n')+'\n'}
    else if(m.type==='log'){$('console').textContent+=m.line+'\n';$('console').scrollTop=$('console').scrollHeight}
    else if(m.type==='state'||m.type==='exit'){refresh()}
  };
  ws.onopen=()=>{$('text').disabled=false;$('send').disabled=false};
  ws.onclose=()=>{$('text').disabled=true;$('send').disabled=true};
}
async function send(){
  const text=$('text').value.trim(); if(!text||!state.ws)return;
  state.ws.send(JSON.stringify({type:'command',text})); $('text').value='';
}
$('send').onclick=send;
$('text').addEventListener('keydown',e=>{if(e.key==='Enter')send()});
$('logout').onclick=async()=>{await fetch('/api/logout',{method:'POST'});location.href='/login'};
refresh(); setInterval(refresh,4000);
</script>
</body></html>
"""


def create_app(
    config: Config,
    registry: InstanceRegistry | None = None,
    sessions: SessionStore | None = None,
) -> web.Application:
    started = time.time()
    data_dir = Path(str(config.get("app.data_dir")))
    log_dir = data_dir / "logs" / "instances"
    registry = registry or InstanceRegistry(data_dir / "instances.json")
    sessions = sessions or SessionStore(
        idle_minutes=int(config.get("auth.session_idle_minutes")),
        absolute_hours=int(config.get("auth.session_absolute_hours")),
    )

    @web.middleware
    async def require_session(request: web.Request, handler: Any) -> web.StreamResponse:
        path = request.path
        if request.method in ("GET", "POST") and path in PUBLIC_PATHS:
            return await handler(request)
        token = request.cookies.get(COOKIE_NAME)
        session = sessions.get(token)
        if session is None:
            if path.startswith("/api/") or path.startswith("/ws/"):
                return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
            raise web.HTTPFound("/login")
        request[SESSION_KEY] = session
        return await handler(request)

    # ---------- 页面 ----------

    async def login_page(request: web.Request) -> web.Response:
        if sessions.get(request.cookies.get(COOKIE_NAME)):
            raise web.HTTPFound("/")
        text = (
            LOGIN_HTML.replace("{{app}}", APP_NAME)
            .replace("{{username}}", str(config.get("auth.username")))
            .replace("{{error}}", request.query.get("error", ""))
        )
        return web.Response(text=text, content_type="text/html")

    async def login_submit(request: web.Request) -> web.Response:
        form = await _read_payload(request)
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))
        if username != config.get("auth.username") or not verify_password(
            password, str(config.get("auth.password_hash"))
        ):
            if request.headers.get("Accept", "").startswith("application/json"):
                return web.json_response({"ok": False, "error": "账号或密码错误"}, status=401)
            raise web.HTTPFound("/login?error=%E8%B4%A6%E5%8F%B7%E6%88%96%E5%AF%86%E7%A0%81%E9%94%99%E8%AF%AF")
        session = sessions.create(username, {"ip": request.remote or ""})
        response = web.Response(status=303, headers={"Location": "/"})
        response.set_cookie(
            COOKIE_NAME,
            session.token,
            httponly=True,
            samesite="Lax",
            max_age=session.idle_seconds,
            path="/",
        )
        return response

    async def logout(request: web.Request) -> web.Response:
        sessions.revoke(request.cookies.get(COOKIE_NAME))
        response = web.json_response({"ok": True})
        response.del_cookie(COOKIE_NAME, path="/")
        return response

    async def index(request: web.Request) -> web.Response:
        session = request[SESSION_KEY]
        text = (
            INDEX_HTML.replace("{{app}}", APP_NAME)
            .replace("{{version}}", VERSION)
            .replace("{{user}}", session.username)
        )
        return web.Response(text=text, content_type="text/html")

    # ---------- 实例 ----------

    def process_for(instance_id: str) -> InstanceProcess:
        processes: dict[str, InstanceProcess] = current_app[PROCESSES_KEY]
        if instance_id not in processes:
            instance = registry.get(instance_id)
            processes[instance_id] = InstanceProcess(instance, log_dir)
        return processes[instance_id]

    async def list_instances(_: web.Request) -> web.Response:
        processes: dict[str, InstanceProcess] = current_app[PROCESSES_KEY]
        items = []
        for instance in registry.all():
            proc = processes.get(instance.id)
            items.append(
                {
                    "id": instance.id,
                    "name": instance.name,
                    "directory": str(instance.root),
                    "launch_mode": instance.launch_mode,
                    "state": proc.state if proc else "stopped",
                    "pid": proc.pid if proc else None,
                }
            )
        return web.json_response({"instances": items})

    async def instance_action(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        action = request.match_info["action"]
        try:
            proc = process_for(instance_id)
        except InstanceNotFound:
            return web.json_response({"ok": False, "error": "实例不存在"}, status=404)
        if action == "start":
            result = await proc.start()
        elif action == "stop":
            result = await proc.stop()
        elif action == "kill":
            result = await proc.kill()
        else:
            return web.json_response({"ok": False, "error": "未知动作"}, status=400)
        return web.json_response(result, status=200 if result.get("ok") else 409)

    async def instance_log(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        try:
            proc = process_for(instance_id)
        except InstanceNotFound:
            return web.json_response({"ok": False, "error": "实例不存在"}, status=404)
        lines = int(request.query.get("lines", 200))
        return web.json_response({"lines": proc.snapshot(lines)})

    async def instance_command(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        try:
            proc = process_for(instance_id)
        except InstanceNotFound:
            return web.json_response({"ok": False, "error": "实例不存在"}, status=404)
        payload = await _read_payload(request)
        result = await proc.send(str(payload.get("text", "")))
        return web.json_response(result, status=200 if result.get("ok") else 409)

    async def ws_console(request: web.Request) -> web.WebSocketResponse:
        instance_id = request.match_info["id"]
        try:
            proc = process_for(instance_id)
        except InstanceNotFound:
            return web.json_response({"ok": False, "error": "实例不存在"}, status=404)
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        await ws.send_json({"type": "snapshot", "lines": proc.snapshot(300), "state": proc.state})
        queue = proc.subscribe()

        async def pump() -> None:
            while True:
                message = await queue.get()
                await ws.send_json(message)

        pump_task = asyncio.create_task(pump())
        try:
            async for message in ws:
                if message.type == WSMsgType.TEXT:
                    with contextlib.suppress(json.JSONDecodeError):
                        payload = json.loads(message.data)
                        if payload.get("type") == "command":
                            await proc.send(str(payload.get("text", "")))
                elif message.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        finally:
            pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pump_task
            proc.unsubscribe(queue)
        return ws

    # ---------- 其它 ----------

    async def health(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "ok": True,
                "app": APP_NAME,
                "version": VERSION,
                "upstream": UPSTREAM,
                "uptime_s": round(time.time() - started, 1),
                "instances": len(registry.all()),
            }
        )

    async def settings(_: web.Request) -> web.Response:
        return web.json_response({"items": config.as_public(), "errors": config.validate()})

    async def java_list(request: web.Request) -> web.Response:
        if request.query.get("scan") != "1":
            return web.json_response({"java": []})
        found = await asyncio.get_running_loop().run_in_executor(None, scan)
        return web.json_response({"java": [j.to_dict() for j in found]})

    async def java_probe(request: web.Request) -> web.Response:
        path = request.query.get("path", "")
        info = await asyncio.get_running_loop().run_in_executor(None, probe, path)
        if info is None:
            return web.json_response({"ok": False, "error": "不是可用的 Java"}, status=400)
        return web.json_response({"ok": True, "java": info.to_dict()})

    async def not_found(_: web.Request) -> web.Response:
        return web.json_response({"ok": False, "error": "not found"}, status=404)

    app = web.Application(middlewares=[require_session])
    app[CONFIG_KEY] = config
    app[REGISTRY_KEY] = registry
    app[SESSIONS_KEY] = sessions
    app[PROCESSES_KEY] = {}
    app[LOG_DIR_KEY] = log_dir
    current_app = app

    app.router.add_get("/login", login_page)
    app.router.add_post("/api/login", login_submit)
    app.router.add_post("/api/logout", logout)
    app.router.add_get("/", index)
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/settings", settings)
    app.router.add_get("/api/instances", list_instances)
    app.router.add_post("/api/instances/{id}/{action:start|stop|kill}", instance_action)
    app.router.add_get("/api/instances/{id}/log", instance_log)
    app.router.add_post("/api/instances/{id}/command", instance_command)
    app.router.add_get("/api/java", java_list)
    app.router.add_get("/api/java/probe", java_probe)
    app.router.add_get("/ws/console/{id}", ws_console)
    app.router.add_route("*", "/{tail:.*}", not_found)

    async def close_processes(_: web.Application) -> None:
        processes: dict[str, InstanceProcess] = app[PROCESSES_KEY]
        for proc in processes.values():
            await proc.shutdown()

    app.on_shutdown.append(close_processes)
    return app


async def _read_payload(request: web.Request) -> dict[str, Any]:
    if request.content_type.startswith("application/json"):
        try:
            return await request.json()
        except json.JSONDecodeError:
            return {}
    if request.can_read_body:
        post = await request.post()
        return dict(post)
    return {}


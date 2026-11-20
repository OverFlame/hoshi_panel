"""Web 层：登录（含两步验证）、实例管理、控制台、设置。

所有写操作要求会话 Cookie + CSRF 头。启动暴露档由 security.exposure 判定，CLI 负责拦截。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
import time
import uuid
from pathlib import Path
from typing import Any

import segno
from aiohttp import WSMsgType, web

from .. import APP_NAME, UPSTREAM, VERSION
from ..auth import (
    COOKIE_NAME,
    LoginThrottle,
    SessionStore,
    consume_recovery,
    generate_recovery_codes,
    generate_secret,
    hash_password,
    hash_recovery_codes,
    provisioning_uri,
    verify_password,
    verify_totp,
)
from ..config import Config, save
from ..db import log_setting, recent_audit, recent_settings, record
from ..files import INCLUDE_SETS, UnsafePath, resolve_within, safe_extract, stream_zip
from ..instances import (
    Instance,
    InstanceNotFound,
    InstanceProcess,
    InstanceRegistry,
    detect,
    probe,
    scan,
)
from ..instances.backup import BackupManager
from ..security import commands, exposure, jvmargs
from .audit_page import AUDIT_HTML
from .index_page import INDEX_HTML

CONFIG_KEY: web.AppKey[Config] = web.AppKey("config", Config)
REGISTRY_KEY: web.AppKey[InstanceRegistry] = web.AppKey("registry", InstanceRegistry)
SESSIONS_KEY: web.AppKey[SessionStore] = web.AppKey("sessions", SessionStore)
PROCESSES_KEY: web.AppKey[dict[str, InstanceProcess]] = web.AppKey("processes", dict)
LOG_DIR_KEY: web.AppKey[Path] = web.AppKey("log_dir", Path)
THROTTLE_KEY: web.AppKey[LoginThrottle] = web.AppKey("throttle", LoginThrottle)
DB_KEY: web.AppKey[Any] = web.AppKey("db", object)
PENDING_KEY: web.AppKey[dict[str, str]] = web.AppKey("pending_totp", dict)
SESSION_KEY: web.RequestKey = web.RequestKey("session", object)

CSRF_COOKIE = "hoshi_csrf"
CSRF_HEADER = "X-CSRF-Token"
PUBLIC_PATHS = {"/login", "/api/login", "/api/health", "/favicon.ico"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

LOGIN_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>登录 · {{app}}</title>
<style>
 body{font:14px/1.6 system-ui,sans-serif;display:grid;place-items:center;height:100vh;margin:0;background:#0f1115;color:#e6e6e6}
 form{background:#171a21;padding:28px;border-radius:10px;width:320px;box-shadow:0 8px 30px #0006}
 h1{font-size:1.1rem;margin:0 0 16px}
 label{display:block;margin:10px 0 4px;font-size:.85rem;opacity:.75}
 input{width:100%;box-sizing:border-box;padding:8px;border-radius:6px;border:1px solid #333;background:#0f1115;color:#e6e6e6}
 button{margin-top:16px;width:100%;padding:9px;border:0;border-radius:6px;background:#2f6fed;color:#fff;font-size:.95rem;cursor:pointer}
 .err{color:#ff6b6b;margin-top:10px;font-size:.85rem;min-height:1em}
 .hint{opacity:.55;font-size:.78rem;margin-top:8px}
</style></head>
<body>
<form method="post" action="/api/login">
  <h1>{{app}} 登录</h1>
  <label for="u">账号</label><input id="u" name="username" value="{{username}}" autocomplete="username">
  <label for="p">密码</label><input id="p" name="password" type="password" autocomplete="current-password" autofocus>
  <label for="c">动态码（如已开启两步验证）</label><input id="c" name="code" inputmode="numeric" autocomplete="one-time-code">
  <button type="submit">登录</button>
  <div class="err">{{error}}</div>
  <div class="hint">忘记密码：在服务器上运行 hoshi reset-password</div>
</form>
</body></html>
"""


SETTINGS_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>设置 · {{app}}</title>
<style>
 :root{color-scheme:dark}
 body{margin:0;font:14px/1.6 system-ui,sans-serif;background:#0f1115;color:#e6e6e6}
 header{display:flex;justify-content:space-between;padding:12px 18px;border-bottom:1px solid #23262d}
 h2{font-size:.95rem;margin:24px 0 8px;color:#9db4d0}
 main{max-width:900px;padding:0 18px 60px}
 .item{border:1px solid #23262d;border-radius:8px;padding:12px;margin-bottom:10px}
 .item .top{display:flex;justify-content:space-between;gap:10px}
 .key{font-family:ui-monospace,monospace;font-size:.78rem;opacity:.6}
 .why{font-size:.8rem;opacity:.7;margin-top:2px}
 .row{display:flex;gap:10px;align-items:center;margin-top:8px}
 input,select{background:#141821;color:#e6e6e6;border:1px solid #333;border-radius:6px;padding:6px 8px;min-width:220px}
 .tag{font-size:.72rem;padding:1px 6px;border-radius:99px;background:#2a2f3a}
 .tag.high{background:#5a1d1d;color:#ffb8b8}
 .tag.medium{background:#4a3a12;color:#ffd28a}
 button{padding:7px 14px;border-radius:6px;border:1px solid #333;background:#1b1f27;color:#e6e6e6;cursor:pointer}
 button.primary{background:#2f6fed;border-color:#2f6fed}
 .muted{opacity:.6}
 #msg{margin-top:12px;font-size:.85rem}
 a{color:#8ab4ff}
</style></head>
<body>
<header><h1 style="font-size:1rem;margin:0">{{app}} 设置</h1><div><a href="/">返回</a> <a href="/audit">审计</a></div></header>
<main>
<h2>改密码</h2>
<div class="item">
  <div class="top"><div><b>管理员密码</b> <span class="key">auth.password_hash</span></div></div>
  <div class="why">改完会踢掉其它设备上的会话，当前这个保留。</div>
  <div class="row"><input id="pw-old" type="password" placeholder="当前密码">
  <input id="pw-new" type="password" placeholder="新密码，至少 8 位">
  <button id="pw-save">保存</button></div>
  <div id="pw-msg" class="muted"></div>
</div>
<h2>两步验证</h2>
<div class="item">
  <div class="top"><div><b>登录动态码</b> <span class="key">auth.totp_enabled</span></div><div id="totp-state" class="tag">读取中</div></div>
  <div class="why">没有验证器 App 也能用：保存生成的一次性恢复码，或在服务器上运行 hoshi totp 出码。</div>
  <div class="row">
    <button id="totp-setup">生成密钥并显示二维码</button>
    <button id="totp-rotate">重新生成恢复码</button>
    <button id="totp-disable">关闭两步验证</button>
  </div>
  <div id="totp-enroll" style="display:none;margin-top:12px">
    <div class="row"><img id="totp-qr" width="200" height="200" alt="二维码"></div>
    <div class="why">扫不出就用密钥手动输入（验证器里选「输入设置密钥」）：<code id="totp-secret"></code></div>
    <div class="row"><input id="totp-code" inputmode="numeric" placeholder="输入 App 上的 6 位数字">
    <button class="primary" id="totp-enable">启用</button></div>
  </div>
  <div id="totp-codes" class="why" style="display:none"></div>
</div>
<p class="muted">改动立即写入配置文件；标「重启生效」的需要重启面板。来源列显示这个值现在来自哪里。</p>
<div id="items"></div>
<div class="row"><button class="primary" id="save">保存改动</button><span class="muted">危险项保存后可能要求重启</span></div>
<div id="msg"></div>
</main>
<script>
const csrf=document.cookie.split('; ').find(c=>c.startsWith('hoshi_csrf='))?.split('=')[1]||'';
let items=[];
function render(){
  const box=document.getElementById('items'); box.innerHTML='';
  let group='';
  for(const it of items){
    if(it.group!==group){group=it.group;const h=document.createElement('h2');h.textContent=group;box.appendChild(h)}
    const div=document.createElement('div'); div.className='item';
    const risk=it.risk==='low'?'':'<span class="tag '+it.risk+'">'+it.risk+'</span>';
    const restart=it.restart?'<span class="tag">重启生效</span>':'';
    div.innerHTML=`<div class="top"><div><b>${it.label}</b> <span class="key">${it.key}</span></div>
      <div>${risk} ${restart} <span class="tag">${it.source}</span></div></div>
      <div class="why">${it.summary} ${it.why||''}</div>`;
    const row=document.createElement('div'); row.className='row';
    let input;
    if(it.kind==='bool'){input=document.createElement('select');input.innerHTML='<option value="true">开启</option><option value="false">关闭</option>';input.value=String(it.value)}
    else if(it.kind==='list'){input=document.createElement('input');input.value=(it.value||[]).join(',');input.dataset.list='1'}
    else {input=document.createElement('input');input.value=it.value??'';input.type=it.secret?'password':'text'}
    input.dataset.key=it.key; input.dataset.kind=it.kind;
    row.appendChild(input); div.appendChild(row); box.appendChild(div);
  }
}
async function load(){
  const r=await fetch('/api/settings'); const data=await r.json(); items=data.items; render();
  if(data.errors&&data.errors.length){document.getElementById('msg').textContent='当前配置有问题：'+data.errors.join('；')}
}
document.getElementById('save').onclick=async()=>{
  const values={};
  document.querySelectorAll('#items input,#items select').forEach(el=>{
    const key=el.dataset.key; if(!key)return;
    values[key]=el.dataset.list?el.value.split(',').map(s=>s.trim()).filter(Boolean):el.value;
  });
  const r=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({values})});
  const data=await r.json();
  const msg=document.getElementById('msg');
  msg.textContent=r.ok?('已保存'+(data.restart_required.length?'，需重启：'+data.restart_required.join('、'):'')):('失败：'+(data.errors||[]).join('；'));
  if(r.ok) await load();
};
async function authStatus(){
  const r=await fetch('/api/auth/status'); if(!r.ok) return;
  const d=await r.json();
  document.getElementById('totp-state').textContent=d.totp_enabled?('已开启 · 恢复码 '+d.recovery_left):'未开启';
}
function showCodes(codes){
  const el=document.getElementById('totp-codes'); el.style.display='block';
  el.innerHTML='恢复码只显示这一次，存好：<br><code>'+codes.join('  ')+'</code>';
}
document.getElementById('totp-setup').onclick=async()=>{
  const r=await fetch('/api/auth/totp/setup',{method:'POST',headers:{'X-CSRF-Token':csrf}});
  const d=await r.json();
  if(!d.ok){alert(d.error||'生成失败');return}
  document.getElementById('totp-secret').textContent=d.secret;
  document.getElementById('totp-qr').src='/api/auth/totp/qr?t='+Date.now();
  document.getElementById('totp-enroll').style.display='block';
};
document.getElementById('totp-enable').onclick=async()=>{
  const code=document.getElementById('totp-code').value.trim();
  const r=await fetch('/api/auth/totp/enable',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({code})});
  const d=await r.json();
  if(!d.ok){alert(d.error||'启用失败');return}
  document.getElementById('totp-enroll').style.display='none';
  showCodes(d.recovery_codes); authStatus();
};
document.getElementById('totp-rotate').onclick=async()=>{
  const password=prompt('输入当前密码，用于重新生成恢复码'); if(!password)return;
  const r=await fetch('/api/auth/recovery/rotate',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({password})});
  const d=await r.json();
  if(!d.ok){alert(d.error||'失败');return}
  showCodes(d.recovery_codes); authStatus();
};
document.getElementById('totp-disable').onclick=async()=>{
  const password=prompt('输入当前密码，关闭两步验证'); if(!password)return;
  const r=await fetch('/api/auth/totp/disable',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({password})});
  const d=await r.json();
  if(!d.ok){alert(d.error||'失败');return}
  authStatus();
};
document.getElementById('pw-save').onclick=async()=>{
  const old=document.getElementById('pw-old').value;
  const nw=document.getElementById('pw-new').value;
  const r=await fetch('/api/auth/password',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({old,new:nw})});
  const d=await r.json();
  const msg=document.getElementById('pw-msg');
  msg.textContent=r.ok?('已更新密码，踢掉其它会话 '+d.sessions_revoked+' 个'):('失败：'+(d.error||''));
  if(r.ok){document.getElementById('pw-old').value='';document.getElementById('pw-new').value=''}
};
authStatus();
load();
</script>
</body></html>
"""


def create_app(
    config: Config,
    registry: InstanceRegistry | None = None,
    sessions: SessionStore | None = None,
    db: Any = None,
    throttle: LoginThrottle | None = None,
) -> web.Application:
    started = time.time()
    data_dir = Path(str(config.get("app.data_dir")))
    log_dir = data_dir / "logs" / "instances"
    registry = registry or InstanceRegistry(data_dir / "instances.json")
    sessions = sessions or SessionStore(
        idle_minutes=int(config.get("auth.session_idle_minutes")),
        absolute_hours=int(config.get("auth.session_absolute_hours")),
    )
    throttle = throttle or LoginThrottle(
        limit=int(config.get("security.login_fail_limit")),
        lock_seconds=int(config.get("security.login_lock_minutes")) * 60,
    )

    def persist() -> None:
        if config.path is not None:
            with contextlib.suppress(OSError):
                save(config, config.path)

    def audit(actor: str, action: str, target: str = "", result: str = "ok", detail: str = "") -> None:
        if db is not None:
            with contextlib.suppress(Exception):
                record(db, actor=actor, action=action, target=target, result=result, detail=detail)

    def client_ip(request: web.Request) -> str:
        if bool(config.get("web.behind_proxy")):
            forwarded = request.headers.get("X-Forwarded-For", "")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.remote or "unknown"

    # ---------- 中间件 ----------

    @web.middleware
    async def require_session(request: web.Request, handler: Any) -> web.StreamResponse:
        path = request.path
        if request.method in ("GET", "POST") and path in PUBLIC_PATHS:
            return await handler(request)
        session = sessions.get(request.cookies.get(COOKIE_NAME))
        if session is None:
            if path.startswith("/api/") or path.startswith("/ws/"):
                return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
            raise web.HTTPFound("/login")
        request[SESSION_KEY] = session

        if request.method not in SAFE_METHODS:
            token = request.headers.get(CSRF_HEADER) or str(
                (await _read_payload(request)).get("csrf", "")
            )
            expected = session.meta.get("csrf", "")
            if not expected or not secrets.compare_digest(str(token), expected):
                return web.json_response({"ok": False, "error": "csrf"}, status=403)
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
        code = str(form.get("code", ""))
        ip = client_ip(request)
        keys = (f"ip:{ip}", f"user:{username}")

        wait = throttle.check(*keys)
        if wait:
            audit(username or "unknown", "login", target=ip, result="locked", detail=f"{wait}s")
            return web.json_response(
                {"ok": False, "error": f"尝试过多，{wait} 秒后再试"},
                status=429,
                headers={"Retry-After": str(wait)},
            )

        ok = username == config.get("auth.username") and verify_password(
            password, str(config.get("auth.password_hash"))
        )
        if ok and bool(config.get("auth.totp_enabled")):
            ok = _check_second_factor(config, code)

        if not ok:
            locked = throttle.fail(*keys)
            audit(username or "unknown", "login", target=ip, result="fail")
            if locked:
                audit(username or "unknown", "login", target=ip, result="locked", detail=f"{locked}s")
            if request.headers.get("Accept", "").startswith("application/json"):
                return web.json_response({"ok": False, "error": "账号、密码或动态码错误"}, status=401)
            raise web.HTTPFound("/login?error=%E8%B4%A6%E5%8F%B7%E6%88%96%E5%AF%86%E7%A0%81%E9%94%99%E8%AF%AF")

        throttle.reset(*keys)
        session = sessions.create(username, {"ip": ip, "csrf": secrets.token_urlsafe(24)})
        audit(username, "login", target=ip, result="ok")
        response = web.Response(status=303, headers={"Location": "/"})
        response.set_cookie(
            COOKIE_NAME, session.token, httponly=True, samesite="Lax", max_age=session.idle_seconds, path="/"
        )
        response.set_cookie(
            CSRF_COOKIE,
            session.meta["csrf"],
            httponly=False,
            samesite="Lax",
            max_age=session.idle_seconds,
            path="/",
        )
        return response

    async def logout(request: web.Request) -> web.Response:
        sessions.revoke(request.cookies.get(COOKIE_NAME))
        response = web.json_response({"ok": True})
        response.del_cookie(COOKIE_NAME, path="/")
        response.del_cookie(CSRF_COOKIE, path="/")
        return response

    async def index(request: web.Request) -> web.Response:
        session = request[SESSION_KEY]
        text = (
            INDEX_HTML.replace("{{app}}", APP_NAME)
            .replace("{{version}}", VERSION)
            .replace("{{user}}", session.username)
            .replace("{{banner}}", exposure.banner(config))
            .replace("{{banner_class}}", "local" if str(config.get("web.exposure")) == "local" else "")
        )
        return web.Response(text=text, content_type="text/html")

    async def audit_page(request: web.Request) -> web.Response:
        return web.Response(text=AUDIT_HTML.replace("{{app}}", APP_NAME), content_type="text/html")

    async def audit_list(request: web.Request) -> web.Response:
        if db is None:
            return web.json_response({"items": []})
        limit = min(500, max(1, int(request.query.get("limit", 100))))
        items = recent_audit(db, limit=limit, action=request.query.get("action", ""))
        return web.json_response({"items": items})

    async def change_password(request: web.Request) -> web.Response:
        session = request[SESSION_KEY]
        payload = await _read_payload(request)
        old = str(payload.get("old", ""))
        new = str(payload.get("new", ""))
        if not verify_password(old, str(config.get("auth.password_hash"))):
            audit(session.username, "password", result="fail", detail="旧密码不正确")
            return web.json_response({"ok": False, "error": "旧密码不正确"}, status=400)
        if len(new) < 8:
            return web.json_response({"ok": False, "error": "新密码至少 8 位"}, status=400)
        if new == old:
            return web.json_response({"ok": False, "error": "新密码不能与旧密码相同"}, status=400)
        config.set("auth.password_hash", hash_password(new), "file")
        persist()
        dropped = sessions.revoke_others(request.cookies.get(COOKIE_NAME))
        audit(session.username, "password", result="ok", detail=f"踢掉其它会话 {dropped} 个")
        return web.json_response({"ok": True, "sessions_revoked": dropped})

    async def settings_page(request: web.Request) -> web.Response:
        text = SETTINGS_HTML.replace("{{app}}", APP_NAME)
        return web.Response(text=text, content_type="text/html")

    # ---------- 设置 ----------

    async def get_settings(_: web.Request) -> web.Response:
        errors, warnings = exposure.evaluate(config)
        return web.json_response(
            {
                "items": config.as_public(),
                "errors": config.validate() + errors,
                "warnings": warnings,
                "banner": exposure.banner(config),
            }
        )

    async def post_settings(request: web.Request) -> web.Response:
        session = request[SESSION_KEY]
        payload = await _read_payload(request)
        values = payload.get("values") or {}
        if not isinstance(values, dict):
            return web.json_response({"ok": False, "errors": ["values 需要是对象"]}, status=400)

        changed: list[str] = []
        restart_required: list[str] = []
        errors: list[str] = []
        for key, raw in values.items():
            item = config_item(key)
            if item is None:
                errors.append(f"未知配置项: {key}")
                continue
            try:
                value = item.coerce(raw)
                item.validate(value)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if config.get(key) != value:
                old = config.get(key)
                config.set(key, value, "file")
                changed.append(key)
                if db is not None:
                    log_setting(db, session.username, key, old, value)
                if item.restart:
                    restart_required.append(key)

        if errors:
            return web.json_response({"ok": False, "errors": errors}, status=400)

        persist()
        problems = config.validate() + exposure.evaluate(config)[0]
        if problems:
            return web.json_response(
                {"ok": False, "errors": problems, "restart_required": restart_required}, status=400
            )
        if changed:
            audit(session.username, "settings", detail=", ".join(changed))
        return web.json_response({"ok": True, "changed": changed, "restart_required": restart_required})

    async def settings_history(_: web.Request) -> web.Response:
        if db is None:
            return web.json_response({"items": []})
        return web.json_response({"items": recent_settings(db, 50)})

    # ---------- 两步验证 ----------

    async def auth_status(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "totp_enabled": bool(config.get("auth.totp_enabled")),
                "recovery_left": len(config.get("auth.recovery_hashes") or []),
                "exposure": config.get("web.exposure"),
                "banner": exposure.banner(config),
            }
        )

    async def totp_setup(request: web.Request) -> web.Response:
        session = request[SESSION_KEY]
        secret = generate_secret()
        pending = current_app[PENDING_KEY]
        pending.clear()
        pending.update({"secret": secret, "actor": session.username})
        return web.json_response(
            {
                "ok": True,
                "secret": secret,
                "uri": provisioning_uri(secret, str(config.get("auth.username")), APP_NAME),
            }
        )

    async def totp_qr(request: web.Request) -> web.Response:
        """返回 otpauth 地址的二维码；有待绑定密钥时优先用它。"""
        secret = str(current_app[PENDING_KEY].get("secret") or config.get("auth.totp_secret") or "")
        if not secret:
            return web.json_response({"ok": False, "error": "还没有密钥，先调用 setup"}, status=400)
        uri = provisioning_uri(secret, str(config.get("auth.username")), APP_NAME)
        svg = segno.make(uri, error="m").svg_inline(scale=4, border=2)
        return web.Response(text=svg, content_type="image/svg+xml", headers={"Cache-Control": "no-store"})

    async def recovery_rotate(request: web.Request) -> web.Response:
        """重新生成恢复码；旧的一次性码立即失效。"""
        session = request[SESSION_KEY]
        payload = await _read_payload(request)
        if not verify_password(str(payload.get("password", "")), str(config.get("auth.password_hash"))):
            return web.json_response({"ok": False, "error": "密码不正确"}, status=400)
        codes = generate_recovery_codes()
        config.set("auth.recovery_hashes", hash_recovery_codes(codes), "file")
        persist()
        audit(session.username, "recovery", result="rotated")
        return web.json_response({"ok": True, "recovery_codes": codes})

    async def totp_enable(request: web.Request) -> web.Response:
        session = request[SESSION_KEY]
        pending = current_app[PENDING_KEY]
        payload = await _read_payload(request)
        secret = str(pending.get("secret", ""))
        if not secret:
            return web.json_response({"ok": False, "error": "先调用 setup"}, status=400)
        passed, step = verify_totp(secret, str(payload.get("code", "")), last_step=0)
        if not passed:
            return web.json_response({"ok": False, "error": "动态码不正确"}, status=400)
        codes = generate_recovery_codes()
        config.set("auth.totp_secret", secret, "file")
        config.set("auth.totp_enabled", True, "file")
        config.set("auth.totp_last_step", step, "file")
        config.set("auth.recovery_hashes", hash_recovery_codes(codes), "file")
        persist()
        current_app[PENDING_KEY].clear()
        audit(session.username, "totp", result="enabled")
        return web.json_response({"ok": True, "recovery_codes": codes})

    async def totp_disable(request: web.Request) -> web.Response:
        session = request[SESSION_KEY]
        payload = await _read_payload(request)
        if not verify_password(str(payload.get("password", "")), str(config.get("auth.password_hash"))):
            return web.json_response({"ok": False, "error": "密码不正确"}, status=400)
        config.set("auth.totp_enabled", False, "file")
        config.set("auth.totp_secret", "", "file")
        config.set("auth.recovery_hashes", [], "file")
        config.set("web.exposure", "local", "file") if str(config.get("web.exposure")) == "public" else None
        persist()
        audit(session.username, "totp", result="disabled")
        return web.json_response({"ok": True})

    # ---------- 实例 ----------

    def process_for(instance_id: str) -> InstanceProcess:
        processes: dict[str, InstanceProcess] = current_app[PROCESSES_KEY]
        if instance_id not in processes:
            instance = registry.get(instance_id)
            problems = jvmargs.validate(instance.jvm_args)
            if problems:
                raise ValueError("; ".join(problems))
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
        except ValueError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        if action == "start":
            result = await proc.start()
        elif action == "stop":
            result = await proc.stop()
        elif action == "kill":
            result = await proc.kill()
        else:
            return web.json_response({"ok": False, "error": "未知动作"}, status=400)
        audit(request[SESSION_KEY].username, f"instance.{action}", target=instance_id,
              result="ok" if result.get("ok") else "fail")
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
        text = str(payload.get("text", ""))
        allowed, reason = commands.check(
            text,
            mode=str(config.get("console.command_mode")),
            extra=list(config.get("console.extra_commands") or []),
        )
        if not allowed:
            audit(request[SESSION_KEY].username, "command", target=instance_id, result="denied", detail=reason)
            return web.json_response({"ok": False, "error": reason}, status=403)
        result = await proc.send(text)
        audit(request[SESSION_KEY].username, "command", target=instance_id,
              result="ok" if result.get("ok") else "fail", detail=commands.normalize(text)[:60])
        return web.json_response(result, status=200 if result.get("ok") else 409)


    # ---------- 文件 ----------

    def instance_root(instance_id: str) -> Path:
        return registry.get(instance_id).root

    async def list_files(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        try:
            root = instance_root(instance_id)
        except InstanceNotFound:
            return web.json_response({"ok": False, "error": "实例不存在"}, status=404)
        rel = request.query.get("path", "")
        try:
            target = resolve_within(root, rel)
        except UnsafePath as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        if not target.is_dir():
            return web.json_response({"ok": False, "error": "不是目录"}, status=400)
        entries = []
        for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            try:
                stat = item.stat()
            except OSError:
                continue
            entries.append(
                {
                    "name": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "size": stat.st_size,
                    "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
                }
            )
        return web.json_response({"path": rel, "entries": entries, "parent": str(Path(rel).parent) if rel else ""})

    async def read_file(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        root = instance_root(instance_id)
        rel = request.query.get("path", "")
        try:
            target = resolve_within(root, rel)
        except UnsafePath as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        if not target.is_file():
            return web.json_response({"ok": False, "error": "文件不存在"}, status=404)
        if target.stat().st_size > 1024 * 1024:
            return web.json_response({"ok": False, "error": "文件过大，超过 1 MB"}, status=400)
        raw = target.read_bytes()
        if b"\x00" in raw[:4096]:
            return web.json_response({"ok": False, "error": "二进制文件不可编辑"}, status=400)
        return web.json_response({"path": rel, "content": raw.decode("utf-8", "replace"), "size": len(raw)})

    async def write_file(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        root = instance_root(instance_id)
        payload = await _read_payload(request)
        rel = str(payload.get("path", ""))
        content = str(payload.get("content", ""))
        try:
            target = resolve_within(root, rel)
        except UnsafePath as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        if target.is_dir():
            return web.json_response({"ok": False, "error": "目标是目录"}, status=400)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        audit(request[SESSION_KEY].username, "file.write", target=rel, result="ok")
        return web.json_response({"ok": True, "size": len(content)})

    async def delete_file(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        root = instance_root(instance_id)
        rel = request.query.get("path", "")
        if not rel:
            return web.json_response({"ok": False, "error": "不能删除实例根目录"}, status=400)
        try:
            target = resolve_within(root, rel)
        except UnsafePath as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        if not target.exists():
            return web.json_response({"ok": False, "error": "不存在"}, status=404)
        if target.is_dir():
            if any(target.iterdir()):
                return web.json_response({"ok": False, "error": "目录非空，先删里面的文件"}, status=400)
            target.rmdir()
        else:
            target.unlink()
        audit(request[SESSION_KEY].username, "file.delete", target=rel, result="ok")
        return web.json_response({"ok": True})

    # ---------- 导出与导入 ----------

    async def export_zip(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        try:
            instance = registry.get(instance_id)
        except InstanceNotFound:
            return web.json_response({"ok": False, "error": "实例不存在"}, status=404)
        raw = request.query.get("include", "world,config,mods")
        includes: list[str] = []
        for part in raw.split(","):
            key = part.strip()
            if key in INCLUDE_SETS:
                includes.extend(INCLUDE_SETS[key])
            elif key:
                includes.append(key)
        filename = f"{instance.name}-{time.strftime('%Y%m%d-%H%M')}.zip"
        response = web.StreamResponse(
            headers={
                "Content-Type": "application/zip",
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            }
        )
        await response.prepare(request)
        total = 0
        for chunk in stream_zip(instance.root, includes):
            if chunk:
                total += len(chunk)
                await response.write(chunk)
        await response.write_eof()
        audit(request[SESSION_KEY].username, "export", target=instance_id, result="ok", detail=f"{total} bytes")
        return response

    async def import_zip(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        try:
            instance = registry.get(instance_id)
        except InstanceNotFound:
            return web.json_response({"ok": False, "error": "实例不存在"}, status=404)
        reader = await request.multipart()
        field = await reader.next()
        if field is None or field.name != "file":
            return web.json_response({"ok": False, "error": "缺少 file 字段"}, status=400)
        upload_dir = data_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        temp = upload_dir / f"{uuid.uuid4().hex}.zip"
        with temp.open("wb") as fh:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                fh.write(chunk)
        try:
            skipped = safe_extract(temp, instance.root)
        finally:
            temp.unlink(missing_ok=True)
        audit(request[SESSION_KEY].username, "import", target=instance_id, result="ok", detail=f"跳过 {len(skipped)}")
        return web.json_response({"ok": True, "skipped": skipped})

    # ---------- 备份 ----------

    async def backups_create(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        instance = registry.get(instance_id)
        payload = await _read_payload(request)
        includes = payload.get("include") or ["world", "config", "mods"]
        try:
            entry = await asyncio.get_running_loop().run_in_executor(
                None, backup_manager.create, instance, list(includes)
            )
        except ValueError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        audit(request[SESSION_KEY].username, "backup", target=instance_id, result="ok", detail=entry.name)
        return web.json_response({"ok": True, "backup": entry.to_dict()})

    async def backups_list(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        instance = registry.get(instance_id)
        items = [entry.to_dict() for entry in backup_manager.list(instance)]
        return web.json_response({"backups": items, "retention": backup_manager.retention})

    async def backups_restore(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        instance = registry.get(instance_id)
        proc = current_app[PROCESSES_KEY].get(instance_id)
        if proc is not None and proc.running:
            return web.json_response({"ok": False, "error": "请先停止服务器再恢复"}, status=409)
        name = request.match_info["name"]
        try:
            archive = backup_manager.restore(instance, name)
        except FileNotFoundError:
            return web.json_response({"ok": False, "error": "备份不存在"}, status=404)
        skipped = await asyncio.get_running_loop().run_in_executor(
            None, safe_extract, archive, instance.root
        )
        archive.unlink(missing_ok=True)
        audit(request[SESSION_KEY].username, "restore", target=instance_id, result="ok", detail=name)
        return web.json_response({"ok": True, "skipped": skipped})

    async def backups_delete(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        instance = registry.get(instance_id)
        name = request.match_info["name"]
        try:
            backup_manager.delete(instance, name)
        except FileNotFoundError:
            return web.json_response({"ok": False, "error": "备份不存在"}, status=404)
        audit(request[SESSION_KEY].username, "backup.delete", target=instance_id, result="ok", detail=name)
        return web.json_response({"ok": True})

    # ---------- 整合包导入 ----------

    async def import_pack(request: web.Request) -> web.Response:
        reader = await request.multipart()
        upload_dir = data_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        temp = upload_dir / f"{uuid.uuid4().hex}.zip"
        name_field = ""
        uploaded = False
        while True:
            field = await reader.next()
            if field is None:
                break
            if field.name == "name":
                name_field = await field.text()
            elif field.name == "file":
                # multipart 的字段必须就地读完，留着稍后再读会拿到空内容
                with temp.open("wb") as fh:
                    while True:
                        chunk = await field.read_chunk()
                        if not chunk:
                            break
                        fh.write(chunk)
                uploaded = True
        if not uploaded:
            return web.json_response({"ok": False, "error": "缺少 file 字段"}, status=400)

        pack_name = (name_field or "").strip() or f"pack-{int(time.time())}"
        servers_dir = Path(str(config.get("app.servers_dir"))).expanduser().resolve()
        target = servers_dir / pack_name
        if target.exists():
            temp.unlink(missing_ok=True)
            return web.json_response({"ok": False, "error": "目标目录已存在"}, status=409)

        target.mkdir(parents=True, exist_ok=True)
        skipped = await asyncio.get_running_loop().run_in_executor(None, safe_extract, temp, target)
        temp.unlink(missing_ok=True)

        detected = detect(target)
        if not detected.ok:
            return web.json_response(
                {"ok": False, "error": "识别失败，需要手动添加实例", "path": str(target), "skipped": skipped},
                status=422,
            )
        java = ""
        found = await asyncio.get_running_loop().run_in_executor(None, scan)
        if found:
            java = found[0].path
        instance = Instance.new(
            name=pack_name,
            directory=str(target),
            launch_mode=detected.launch_mode,
            jar=detected.jar,
            args_file=detected.args_file,
            user_jvm_args=detected.user_jvm_args,
            java=java,
            min_memory_mb=2048,
            max_memory_mb=8192,
        )
        registry.add(instance)
        audit(request[SESSION_KEY].username, "pack.import", target=instance.id, result="ok", detail=pack_name)
        return web.json_response({"ok": True, "instance": instance.to_dict(), "skipped": skipped})

    async def ws_console(request: web.Request) -> web.WebSocketResponse:
        origin = request.headers.get("Origin")
        if origin and not _same_origin(origin, request):
            return web.json_response({"ok": False, "error": "origin"}, status=403)
        instance_id = request.match_info["id"]
        try:
            proc = process_for(instance_id)
        except InstanceNotFound:
            return web.json_response({"ok": False, "error": "实例不存在"}, status=404)
        except ValueError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

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
                        if payload.get("type") != "command":
                            continue
                        allowed, reason = commands.check(
                            str(payload.get("text", "")),
                            mode=str(config.get("console.command_mode")),
                            extra=list(config.get("console.extra_commands") or []),
                        )
                        if allowed:
                            await proc.send(str(payload.get("text", "")))
                        else:
                            await ws.send_json({"type": "log", "line": f"[面板] 拒绝：{reason}"})
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
                "exposure": config.get("web.exposure"),
            }
        )

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
    app[THROTTLE_KEY] = throttle
    app[DB_KEY] = db
    app[PENDING_KEY] = {}
    current_app = app
    backup_manager = BackupManager(data_dir / "backups", retention=10)

    app.router.add_get("/login", login_page)
    app.router.add_post("/api/login", login_submit)
    app.router.add_post("/api/logout", logout)
    app.router.add_get("/", index)
    app.router.add_get("/settings", settings_page)
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/settings", get_settings)
    app.router.add_post("/api/settings", post_settings)
    app.router.add_get("/api/settings/history", settings_history)
    app.router.add_get("/api/auth/status", auth_status)
    app.router.add_post("/api/auth/totp/setup", totp_setup)
    app.router.add_get("/api/auth/totp/qr", totp_qr)
    app.router.add_post("/api/auth/recovery/rotate", recovery_rotate)
    app.router.add_post("/api/auth/totp/enable", totp_enable)
    app.router.add_post("/api/auth/totp/disable", totp_disable)
    app.router.add_post("/api/auth/password", change_password)
    app.router.add_get("/audit", audit_page)
    app.router.add_get("/api/audit", audit_list)
    app.router.add_get("/api/instances", list_instances)
    app.router.add_post("/api/instances/{id}/{action:start|stop|kill}", instance_action)
    app.router.add_get("/api/instances/{id}/log", instance_log)
    app.router.add_post("/api/instances/{id}/command", instance_command)
    app.router.add_get("/api/instances/{id}/files", list_files)
    app.router.add_get("/api/instances/{id}/file", read_file)
    app.router.add_put("/api/instances/{id}/file", write_file)
    app.router.add_delete("/api/instances/{id}/file", delete_file)
    app.router.add_get("/api/instances/{id}/export", export_zip)
    app.router.add_post("/api/instances/{id}/import", import_zip)
    app.router.add_post("/api/instances/{id}/backup", backups_create)
    app.router.add_get("/api/instances/{id}/backups", backups_list)
    app.router.add_post("/api/instances/{id}/backups/{name}/restore", backups_restore)
    app.router.add_delete("/api/instances/{id}/backups/{name}", backups_delete)
    app.router.add_post("/api/packs/import", import_pack)
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


def config_item(key: str):
    from ..config.schema import BY_KEY

    return BY_KEY.get(key)


def _check_second_factor(config: Config, code: str) -> bool:
    """先试 TOTP，再试恢复码。TOTP 通过后写回最后步长，防重放。"""
    secret = str(config.get("auth.totp_secret") or "")
    passed, step = verify_totp(secret, code, last_step=int(config.get("auth.totp_last_step") or 0))
    if passed:
        config.set("auth.totp_last_step", step, "file")
        return True
    hashes = list(config.get("auth.recovery_hashes") or [])
    used, rest = consume_recovery(hashes, code)
    if used:
        config.set("auth.recovery_hashes", rest, "file")
        return True
    return False


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


def _same_origin(origin: str, request: web.Request) -> bool:
    host = request.host
    return origin.rstrip("/").endswith(host)

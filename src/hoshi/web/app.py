"""Web 层：登录（含两步验证）、实例管理、控制台、设置。

所有写操作要求会话 Cookie + CSRF 头。启动暴露档由 security.exposure 判定，CLI 负责拦截。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import secrets
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

import aiohttp
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
from ..bot import TokenLimiter, render_text, status_payload
from ..compat import install_for_running_loop
from ..config import Config, save
from ..db import (
    create_bot_token,
    find_bot_token,
    list_bot_tokens,
    log_setting,
    recent_audit,
    recent_settings,
    record,
    revoke_bot_token,
)
from ..files import INCLUDE_SETS, UnsafePath, resolve_within, safe_extract, write_zip
from ..files.ziptool import ZipCancelled
from ..instances import (
    Instance,
    InstanceError,
    InstanceNotFound,
    InstanceProcess,
    InstanceRegistry,
    detect,
    probe,
    scan,
)
from ..instances.backup import BackupManager
from ..instances.diagnose import diagnose
from ..instances.java import pick_for
from ..instances.migrate import execute_migration, plan_migration
from ..instances.properties import Properties
from ..instances.settings import PER_INSTANCE_KEYS, coerce_value, effective, resolve
from ..jobs import JobStore
from ..map import (
    MarkerStore,
    PlayerPoller,
    find_cached,
    install_jar,
    is_installed,
    load_secret,
)
from ..map import installer as bluemap_installer
from ..map import (
    issue as issue_share,
)
from ..map import (
    plan as bluemap_plan,
)
from ..map import (
    verify as verify_share,
)
from ..map import (
    write_config as write_bluemap_config,
)
from ..map import (
    write_markers as write_bluemap_markers,
)
from ..map.configgen import MapOptions
from ..metrics import MetricsSampler
from ..mods import ModrinthClient, apply_lookup, scan_mods
from ..mods import toggle as toggle_mod
from ..security import commands, exposure, jvmargs
from .audit_page import AUDIT_HTML
from .font_css import FONT_FACE_CSS
from .index_page import INDEX_HTML
from .overview_page import OVERVIEW_HTML
from .tabler_css import TABLER_CSS

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
<html lang="zh-CN" data-bs-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>登录 · {{app}}</title>
<style>
 :root{color-scheme:dark}
 body{font:14px/1.6 system-ui,sans-serif;display:grid;place-items:center;min-height:100vh;min-height:100dvh;margin:0;background:#0f1115;color:#e6e6e6}
 input{font:inherit;-webkit-text-fill-color:#e6e6e6}
 input:-webkit-autofill,input:-webkit-autofill:hover,input:-webkit-autofill:focus{
   -webkit-text-fill-color:#e6e6e6;
   box-shadow:0 0 0 1000px #0f1115 inset;
   transition:background-color 99999s ease-in-out 0s}
 input:focus{outline:2px solid #2f6fed;outline-offset:1px}
 form{background:#171a21;padding:28px;border-radius:10px;width:320px;box-shadow:0 8px 30px #0006}
 h1{font-size:1.1rem;margin:0 0 16px}
 label{display:block;margin:10px 0 4px;font-size:.85rem;opacity:.75}
 input{width:100%;box-sizing:border-box;padding:8px;border-radius:6px;border:1px solid #333;background:#0f1115;color:#e6e6e6}
 button{margin-top:16px;width:100%;padding:9px;border:0;border-radius:6px;background:#2f6fed;color:#fff;font-size:.95rem;cursor:pointer}
 .err{color:#ff6b6b;margin-top:10px;font-size:.85rem;min-height:1em}
 .hint{opacity:.55;font-size:.78rem;margin-top:8px}
</style><style>
:root{
  --tblr-body-font-size:.85rem;--tblr-body-font-size-xs:.78rem;
  --hoshi-accent:#2f6fed;--hoshi-radius:10px;
  --tblr-font-sans-serif:"JetBrainsMono Nerd Font","JetBrains Mono Web","JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
body{font-size:.85rem;font-family:var(--tblr-font-sans-serif)}
.btn-sm{padding:.22rem .55rem;font-size:.78rem;line-height:1.2}
.card-body{padding:12px 14px}
</style>
<link rel="stylesheet" href="/assets/tabler.css">
<link rel="stylesheet" href="/assets/custom.css">
</head>
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
<style>
body{background:#0b0e13;color:#e6e6e6;display:grid;place-items:center;min-height:100vh;min-height:100dvh;margin:0}
form{background:#151a22;border:1px solid #232a35;padding:26px;border-radius:12px;width:320px;box-shadow:0 12px 40px #0008}
h1{font-size:1.05rem;margin:0 0 14px;color:#e6e6e6}
label{display:block;margin:10px 0 4px;font-size:.82rem;color:#c9d1d9;opacity:1}
input{width:100%;box-sizing:border-box;padding:8px;border-radius:6px;border:1px solid #2a3140;background:#0b0e13;color:#e6e6e6;font:inherit}
button{margin-top:16px;width:100%;padding:9px;border:0;border-radius:6px;background:#2f6fed;color:#fff;font-size:.92rem;cursor:pointer}
.err{color:#ff8a8a;margin-top:10px;font-size:.82rem;min-height:1em}
.hint{color:#7d8695;font-size:.76rem;margin-top:8px}
</style>
"""


SETTINGS_HTML = """<!doctype html>
<html lang="zh-CN" data-bs-theme="{{theme}}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>设置 · {{app}}</title>
<style>
 :root{color-scheme:dark}
 body{margin:0;font:14px/1.6 system-ui,sans-serif;background:#0f1115;color:#e6e6e6}
 header{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:12px 18px;border-bottom:1px solid #23262d}
 h2{font-size:.95rem;margin:24px 0 8px;color:#9db4d0}
 main{max-width:900px;padding:0 18px 60px}
 .item{border:1px solid #23262d;border-radius:8px;padding:12px;margin-bottom:10px}
 .item .top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
 .item .top>.meta{display:flex;align-items:center;gap:8px;flex:0 0 auto}
 .key{font-family:ui-monospace,monospace;font-size:.78rem;opacity:.6}
 .why{font-size:.8rem;opacity:.7;margin-top:2px}
 .row{display:flex;gap:10px;align-items:center;margin-top:8px}
 input,select{background:#141821;color:#e6e6e6;border:1px solid #333;border-radius:6px;padding:6px 8px;min-width:220px}
 .tag{font-size:.72rem;line-height:1.6;padding:2px 8px;border-radius:99px;background:#232a35;color:#a9b3c2;border:1px solid #2a3140;white-space:nowrap}
 .tag.high{background:#3d1616;color:#ffb4b4;border-color:#5a2020}
 .tag.medium{background:#3a2f10;color:#ffd28a;border-color:#4d3d16}
 .tag.source{background:#1a2230;color:#9db4d0}
 .tag.high{background:#5a1d1d;color:#ffb8b8}
 .tag.medium{background:#4a3a12;color:#ffd28a}
 button{padding:7px 14px;border-radius:6px;border:1px solid #333;background:#1b1f27;color:#e6e6e6;cursor:pointer}
 button.primary{background:#2f6fed;border-color:#2f6fed}
 .muted{opacity:.6}
 #msg{margin-top:12px;font-size:.85rem}
 a{color:#8ab4ff}
</style><style>
:root{
  --tblr-body-font-size:.85rem;--tblr-body-font-size-xs:.78rem;
  --hoshi-accent:#2f6fed;--hoshi-radius:10px;
  --tblr-font-sans-serif:"JetBrainsMono Nerd Font","JetBrains Mono Web","JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
body{font-size:.85rem;font-family:var(--tblr-font-sans-serif)}
.btn-sm{padding:.22rem .55rem;font-size:.78rem;line-height:1.2}
.card-body{padding:12px 14px}
</style>
<link rel="stylesheet" href="/assets/tabler.css">
<link rel="stylesheet" href="/assets/custom.css">
</head>
<body>
<header class="topbar"><h1 style="font-size:1rem;margin:0">{{app}} 设置</h1>
<div style="display:flex;gap:14px;align-items:center"><a href="/">返回</a><a href="/audit">审计</a></div></header>
<main>
<h2>bot 令牌</h2>
<div class="item">
  <div class="top"><div><b>只读查询令牌</b> <span class="key">bot_tokens</span></div></div>
  <div class="why">给 QQ bot 用。绑定群号，按群每分钟 {{group_limit}} 次限速。令牌只显示一次。</div>
  <div class="row"><input id="bot-group" placeholder="群号，例如 123456789">
  <input id="bot-label" placeholder="备注（可选）"><button class="primary" id="bot-create">创建</button></div>
  <div id="bot-token-msg" class="why"></div>
  <div id="bot-token-list" class="why"></div>
</div>
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

<style>
header{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:12px 18px;border-bottom:1px solid #23262d;background:transparent}
main{max-width:960px;margin:0 auto;padding:8px 16px 48px;width:100%;box-sizing:border-box}
h2{font-size:.82rem;color:#8a93a3;letter-spacing:.04em;margin:22px 0 8px}
.item{background:#131820;border:1px solid #1f2530;border-radius:10px;padding:12px 14px;margin-bottom:10px}
.item .top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.item .why{color:#8a93a3;font-size:.8rem;margin-top:4px}
.item .row{display:flex;gap:8px;align-items:center;margin-top:10px}
.item .row input,.item .row select{flex:1;min-width:0;width:auto;margin:0}
.item .row button{flex:0 0 auto;width:auto}
.tag{font-size:.72rem;line-height:1.6;padding:2px 8px;border-radius:99px;background:#232a35;color:#a9b3c2;border:1px solid #2a3140;white-space:nowrap}
.tag.high{background:#3d1616;color:#ffb4b4;border-color:#5a2020}
.tag.medium{background:#3a2f10;color:#ffd28a;border-color:#4d3d16}
.tag.source{background:#1a2230;color:#9db4d0}
.key{font-family:ui-monospace,monospace;font-size:.75rem;color:#6f7a8a}
.topbar{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:12px 18px;border-bottom:1px solid #23262d;background:#0d1015}
.topbar a{color:#9db4d0;text-decoration:none;font-size:.88rem}
.topbar a:hover{color:#8ab4ff}
</style>


<script>
const csrf=document.cookie.split('; ').find(c=>c.startsWith('hoshi_csrf='))?.split('=')[1]||'';
let items=[];
function sourceName(src){
  return {instance:'本实例', global:'全局配置文件', file:'配置文件', default:'默认'}[src]||src;
}
function render(){
  const box=document.getElementById('items'); box.innerHTML='';
  let group='';
  for(const it of items){
    if(it.group!==group){group=it.group;const h=document.createElement('h2');h.textContent=group;box.appendChild(h)}
    const div=document.createElement('div'); div.className='item';
    const risk=it.risk==='low'?'':'<span class="tag '+it.risk+'">'+it.risk+'</span>';
    const restart=it.restart?'<span class="tag">重启生效</span>':'';
    div.innerHTML=`<div class="top"><div><b>${it.label}</b> <span class="key">${it.key}</span></div>
      <div class="meta">${risk}${restart}<span class="tag source">${sourceName(it.source)}</span></div></div>
      <div class="why">${it.summary} ${it.why||''}</div>`;
    const row=document.createElement('div'); row.className='row';
    let input;
    if(it.kind==='bool'){input=document.createElement('select');input.innerHTML='<option value="true">开启</option><option value="false">关闭</option>';input.value=String(it.value)}
    else if(it.kind==='list'){input=document.createElement('input');input.value=(it.value||[]).join(',');input.dataset.list='1'}
    else {input=document.createElement('input');input.value=it.value??'';input.type=it.secret?'password':'text'}
    input.dataset.key=it.key; input.dataset.kind=it.kind;
    row.appendChild(input);
    if(it.kind==='path'){
      const btn=document.createElement('button'); btn.textContent='浏览';
      btn.onclick=()=>{
        const p=document.createElement('div');
        p.style.cssText='position:fixed;inset:10% 25%;background:#12151b;border:1px solid #2c313a;border-radius:10px;padding:12px;z-index:40;display:flex;flex-direction:column';
        p.innerHTML='<div class="row"><b>选择目录（服务器上的路径）</b><span class="muted" id="sp-cwd"></span></div>'
          +'<div id="sp-list" style="flex:1;overflow:auto;margin-top:8px"></div>'
          +'<div class="row" style="justify-content:flex-end;gap:8px;margin-top:8px"><button data-x="cancel">取消</button><button class="primary" data-x="ok">选定</button></div>';
        document.body.appendChild(p);
        let cur='';
        async function load(path){
          const r=await fetch('/api/fs/list?path='+encodeURIComponent(path||'')); const d=await r.json();
          if(!r.ok)return; cur=d.path||''; p.querySelector('#sp-cwd').textContent=cur||'（盘符）';
          const list=p.querySelector('#sp-list'); list.innerHTML='';
          for(const e of d.entries){
            const row=document.createElement('div'); row.className='fitem'; row.textContent=e.name+'/';
            row.onclick=()=>load(e.path); list.appendChild(row);
          }
        }
        p.querySelector('[data-x=cancel]').onclick=()=>p.remove();
        p.querySelector('[data-x=ok]').onclick=()=>{ input.value=cur; p.remove() };
        load(input.value||'');
      };
      row.appendChild(btn);
    }
    div.appendChild(row); box.appendChild(div);
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
async function loadBotTokens(){
  const r=await fetch('/api/bot/tokens'); if(!r.ok)return;
  const d=await r.json();
  const box=document.getElementById('bot-token-list');
  if(!d.tokens.length){box.textContent='还没有令牌';return}
  box.innerHTML=d.tokens.map(t=>`<div>#${t.id} · 群 ${t.group_id} · ${t.label||''} · ${t.created}
    <button data-revoke="${t.id}">吊销</button></div>`).join('');
  box.querySelectorAll('button[data-revoke]').forEach(b=>b.onclick=async()=>{
    await fetch('/api/bot/tokens/'+b.dataset.revoke,{method:'DELETE',headers:{'X-CSRF-Token':csrf}});
    loadBotTokens();
  });
}
document.getElementById('bot-create').onclick=async()=>{
  const group=document.getElementById('bot-group').value.trim();
  const label=document.getElementById('bot-label').value.trim();
  if(!group){alert('先填群号');return}
  const r=await fetch('/api/bot/tokens',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({group,label})});
  const d=await r.json();
  document.getElementById('bot-token-msg').textContent=r.ok?('令牌（只显示这一次）：'+d.token):('失败：'+(d.error||''));
  if(r.ok) loadBotTokens();
};
loadBotTokens();

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
function unifyButtons(){
  document.querySelectorAll('button').forEach(b=>{ if(!b.classList.contains('btn')) b.classList.add('btn','btn-sm') });
}
new MutationObserver(unifyButtons).observe(document.body,{childList:true,subtree:true});
unifyButtons();
load();
</script>
</body></html>
"""



MAP_OVERLAY_JS = """
(() => {
  const panel = document.createElement('div');
  panel.id = 'hoshi-overlay';
  panel.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:9999;background:#0f1115dd;color:#e6e6e6;'
    + 'border:1px solid #2c313a;border-radius:10px;padding:10px 12px;font:12px/1.6 system-ui,sans-serif;'
    + 'max-width:280px;backdrop-filter:blur(4px)';
  panel.innerHTML = '<b>面板 · 在线玩家</b><div id="hoshi-players">读取中…</div>';
  document.body.appendChild(panel);
  const box = panel.querySelector('#hoshi-players');
  async function tick() {
    try {
      const r = await fetch('/api/map/players', { credentials: 'same-origin' });
      if (!r.ok) { box.textContent = '需要登录面板'; return; }
      const d = await r.json();
      if (!d.connected) { box.textContent = 'RCON 未连接'; return; }
      if (!d.players.length) { box.textContent = '无人在线'; return; }
      box.innerHTML = d.players.map(p =>
        `<div>${p.name} · ${p.x}, ${p.z} <span style="opacity:.6">${p.dimension.replace('minecraft:', '')}</span></div>`
      ).join('');
    } catch (e) { box.textContent = '读取失败'; }
  }
  tick();
  setInterval(tick, 5000);
})();
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

    def session_username(request: web.Request) -> str:
        session = request.get(SESSION_KEY)
        return getattr(session, "username", "system")

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
        if path.startswith("/map"):
            return await handler(request)

        if path.startswith("/api/bot/") and not path.startswith("/api/bot/tokens"):
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
            .replace("</style>", FONT_FACE_CSS + "</style>")
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

    async def overview(request: web.Request) -> web.Response:
        session = request[SESSION_KEY]
        text = (
            OVERVIEW_HTML.replace("{{app}}", APP_NAME)
            .replace("{{version}}", VERSION)
            .replace("{{user}}", session.username)
            .replace("</style>", FONT_FACE_CSS + "</style>")
        )
        return web.Response(text=text, content_type="text/html")

    async def instance_page(request: web.Request) -> web.Response:
        session = request[SESSION_KEY]
        try:
            instance = registry.get(request.match_info["id"])
        except InstanceNotFound:
            raise web.HTTPFound("/") from None
        text = (
            INDEX_HTML.replace("{{app}}", APP_NAME)
            .replace("{{version}}", VERSION)
            .replace("{{user}}", session.username)
            .replace("{{banner}}", exposure.banner(config))
            .replace("{{banner_class}}", "local" if str(config.get("web.exposure")) == "local" else "")
            .replace("{{instance_id}}", instance.id)
            .replace("{{instance_name}}", instance.name)
            .replace("{{theme}}", str(config.get("web.theme")))
            .replace("</style>", FONT_FACE_CSS + "</style>")
        )
        return web.Response(text=text, content_type="text/html")

    async def audit_page(request: web.Request) -> web.Response:
        text = (
            AUDIT_HTML.replace("{{app}}", APP_NAME)
            .replace("{{theme}}", str(config.get("web.theme")))
            .replace("</style>", FONT_FACE_CSS + "</style>")
        )
        return web.Response(text=text, content_type="text/html")

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
        text = (
            SETTINGS_HTML.replace("{{app}}", APP_NAME)
            .replace("{{group_limit}}", str(config.get("bot.group_limit")))
            .replace("{{theme}}", str(config.get("web.theme")))
            .replace("</style>", FONT_FACE_CSS + "</style>")
        )
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
                    "players": len(proc.players) if proc else 0,
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
        instance_obj = registry.get(instance_id)
        allowed, reason = commands.check(
            text,
            mode=str(resolve(config, instance_obj, "console.command_mode")[0]),
            extra=list(resolve(config, instance_obj, "console.extra_commands")[0] or []),
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

    def parse_includes(raw: str) -> list[str]:
        includes: list[str] = []
        for part in raw.split(","):
            key = part.strip()
            if key in INCLUDE_SETS:
                includes.extend(INCLUDE_SETS[key])
            elif key:
                includes.append(key)
        return includes

    async def export_zip(request: web.Request) -> web.Response:
        """导出改成后台任务，返回 job，前端可看进度并取消。"""
        instance = registry.get(request.match_info["id"])
        includes = parse_includes(request.query.get("include", "world,config,mods"))
        job = jobs.create("export", total=0)
        target = data_dir / "exports" / f"{job['id']}.zip"
        target.parent.mkdir(parents=True, exist_ok=True)

        def work() -> int:
            return write_zip(
                target,
                instance.root,
                includes,
                progress=lambda done, total: jobs.update(
                    job["id"], done=done, total=total, phase="打包中"
                ),
                cancelled=lambda: jobs.cancel_requested(job["id"]),
            )

        async def run() -> None:
            try:
                await asyncio.get_running_loop().run_in_executor(None, work)
            except ZipCancelled:
                target.unlink(missing_ok=True)
                jobs.mark_cancelled(job["id"])
                return
            except Exception as exc:  # 打包失败不要静默
                target.unlink(missing_ok=True)
                jobs.finish(job["id"], error=str(exc))
                return
            size = target.stat().st_size
            jobs.finish(job["id"], result={"path": str(target), "size": size})

        asyncio.create_task(run())
        audit(request[SESSION_KEY].username, "export.start", target=instance.id, result="ok")
        return web.json_response({"ok": True, "job": jobs.get(job["id"])})

    async def export_download(request: web.Request) -> web.Response:
        job = jobs.get(request.match_info["id"])
        if job is None or not job.get("finished") or job.get("error"):
            return web.json_response({"ok": False, "error": "任务未完成"}, status=404)
        result = job.get("result") or {}
        path = Path(str(result.get("path", "")))
        if not path.is_file():
            return web.json_response({"ok": False, "error": "文件已被清理"}, status=404)
        filename = f"{path.stem}.zip"
        return web.FileResponse(
            path,
            headers={
                "Content-Type": "application/zip",
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )

    async def job_cancel(request: web.Request) -> web.Response:
        ok = jobs.request_cancel(request.match_info["id"])
        return web.json_response({"ok": ok}, status=200 if ok else 404)

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
        limit = int(config.get("files.max_upload_mb")) * 1024 * 1024
        written = 0
        with temp.open("wb") as fh:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    fh.close()
                    temp.unlink(missing_ok=True)
                    return web.json_response(
                        {"ok": False, "error": f"超过上传上限 {limit // (1024 * 1024)} MB"}, status=413
                    )
                fh.write(chunk)
        job = jobs.create("zip-import", total=1)
        try:
            skipped = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: safe_extract(
                    temp,
                    instance.root,
                    progress=lambda done, total: jobs.update(
                        job["id"], done=done, total=total, phase="解压中"
                    ),
                ),
            )
        finally:
            temp.unlink(missing_ok=True)
        jobs.finish(job["id"], result={"skipped": skipped})
        audit(request[SESSION_KEY].username, "import", target=instance_id, result="ok", detail=f"跳过 {len(skipped)}")
        return web.json_response({"ok": True, "skipped": skipped, "job": jobs.get(job["id"])})

    # ---------- 备份 ----------

    async def backups_create(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        instance = registry.get(instance_id)
        payload = await _read_payload(request)
        includes = payload.get("include") or ["world", "config", "mods"]
        job = jobs.create("backup", total=0)
        target = backup_manager.dir_for(instance)
        target.mkdir(parents=True, exist_ok=True)
        from ..files import zip_name as make_zip_name

        name = make_zip_name("backup")
        path = target / name

        def work() -> int:
            return write_zip(
                path,
                instance.root,
                list(includes),
                progress=lambda done, total: jobs.update(
                    job["id"], done=done, total=total, phase="备份中"
                ),
                cancelled=lambda: jobs.cancel_requested(job["id"]),
            )

        async def run() -> None:
            try:
                count = await asyncio.get_running_loop().run_in_executor(None, work)
            except ZipCancelled:
                path.unlink(missing_ok=True)
                jobs.mark_cancelled(job["id"])
                return
            except Exception as exc:
                path.unlink(missing_ok=True)
                jobs.finish(job["id"], error=str(exc))
                return
            if count == 0:
                path.unlink(missing_ok=True)
                jobs.finish(job["id"], error="没有可备份的文件")
                return
            backup_manager.prune(instance)
            jobs.finish(job["id"], result={"name": name, "size": path.stat().st_size})
            audit(instance_id and session_username(request), "backup", target=instance_id, result="ok", detail=name)

        asyncio.create_task(run())
        audit(request[SESSION_KEY].username, "backup.start", target=instance_id, result="ok", detail=name)
        return web.json_response({"ok": True, "job": jobs.get(job["id"]), "name": name})

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
                limit = int(config.get("files.max_upload_mb")) * 1024 * 1024
                written = 0
                with temp.open("wb") as fh:
                    while True:
                        chunk = await field.read_chunk()
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > limit:
                            fh.close()
                            temp.unlink(missing_ok=True)
                            return web.json_response(
                                {"ok": False, "error": f"超过上传上限 {limit // (1024 * 1024)} MB"},
                                status=413,
                            )
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
        job = jobs.create("pack-import", total=1)
        jobs.update(job["id"], phase="解压中")

        def do_extract() -> list[str]:
            return safe_extract(
                temp,
                target,
                progress=lambda done, total: jobs.update(
                    job["id"], done=done, total=total, phase="解压中"
                ),
            )

        skipped = await asyncio.get_running_loop().run_in_executor(None, do_extract)
        temp.unlink(missing_ok=True)
        jobs.update(job["id"], phase="识别中")

        detected = detect(target)
        if not detected.ok:
            jobs.finish(job["id"], error="识别失败，需要手动添加实例")
            return web.json_response(
                {
                    "ok": False,
                    "error": "识别失败，需要手动添加实例",
                    "path": str(target),
                    "skipped": skipped,
                    "job": jobs.get(job["id"]),
                },
                status=422,
            )
        java = ""
        found = await asyncio.get_running_loop().run_in_executor(None, scan)
        chosen = pick_for(detected.mc_version or "1.20.1", found)
        if chosen is None and found:
            chosen = found[0]
        if chosen is not None:
            java = chosen.path
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
        jobs.finish(job["id"], result={"instance": instance.to_dict(), "skipped": skipped})
        audit(request[SESSION_KEY].username, "pack.import", target=instance.id, result="ok", detail=pack_name)
        return web.json_response(
            {"ok": True, "instance": instance.to_dict(), "skipped": skipped, "job": jobs.get(job["id"])}
        )

    async def job_status(request: web.Request) -> web.Response:
        job = jobs.get(request.match_info["id"])
        if job is None:
            return web.json_response({"ok": False, "error": "任务不存在"}, status=404)
        return web.json_response(job)


    # ---------- 模组 ----------

    async def list_mods(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        instance = registry.get(instance_id)
        mods_dir = instance.root / "mods"
        items = await asyncio.get_running_loop().run_in_executor(None, scan_mods, mods_dir)
        if request.query.get("lookup") == "1" and bool(resolve(config, instance, "mods.side_lookup")[0]):
            client = ModrinthClient(data_dir / "cache" / "modrinth.json")
            found = await client.lookup([item.sha1 for item in items if item.sha1])
            apply_lookup(items, found)
        return web.json_response(
            {
                "mods": [item.to_dict() for item in items],
                "summary": {
                    "total": len(items),
                    "enabled": sum(1 for item in items if item.enabled),
                    "client_only": sum(1 for item in items if item.side == "client"),
                    "unknown": sum(1 for item in items if item.side == "unknown"),
                },
            }
        )

    async def upload_mod(request: web.Request) -> web.Response:
        instance = registry.get(request.match_info["id"])
        mods_dir = instance.root / "mods"
        mods_dir.mkdir(parents=True, exist_ok=True)
        limit = int(config.get("files.max_upload_mb")) * 1024 * 1024
        reader = await request.multipart()
        saved: list[str] = []
        skipped: list[str] = []
        while True:
            field = await reader.next()
            if field is None:
                break
            if field.name != "file":
                continue
            filename = Path(str(field.filename or "")).name
            lowered = filename.lower()
            if not (lowered.endswith(".jar") or lowered.endswith(".jar.disabled")):
                skipped.append(f"{filename}: 只接受 jar")
                await field.read()
                continue
            target = mods_dir / filename
            if target.exists():
                skipped.append(f"{filename}: 已存在")
                await field.read()
                continue
            written = 0
            with target.open("wb") as fh:
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > limit:
                        fh.close()
                        target.unlink(missing_ok=True)
                        return web.json_response(
                            {"ok": False, "error": f"超过上传上限 {limit // (1024 * 1024)} MB"}, status=413
                        )
                    fh.write(chunk)
            saved.append(filename)
        if not saved:
            return web.json_response({"ok": False, "error": "没有可用的模组文件", "skipped": skipped}, status=400)
        audit(request[SESSION_KEY].username, "mods.upload", target=instance.id, result="ok",
              detail=", ".join(saved[:8]))
        return web.json_response({"ok": True, "saved": saved, "skipped": skipped})

    async def toggle_mod_handler(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        instance = registry.get(instance_id)
        payload = await _read_payload(request)
        file = str(payload.get("file", ""))
        enabled = bool(payload.get("enabled", True))
        proc = current_app[PROCESSES_KEY].get(instance_id)
        if proc is not None and proc.running:
            return web.json_response({"ok": False, "error": "服务器运行中，先停止再改模组"}, status=409)
        try:
            result = await asyncio.get_running_loop().run_in_executor(
                None, toggle_mod, instance.root / "mods", file, enabled
            )
        except FileNotFoundError:
            return web.json_response({"ok": False, "error": "文件不存在"}, status=404)
        except FileExistsError as exc:
            return web.json_response({"ok": False, "error": f"已存在同名文件: {exc}"}, status=409)
        audit(request[SESSION_KEY].username, "mods.toggle", target=file, result="ok", detail=str(result.name))
        return web.json_response({"ok": True, "file": result.name, "enabled": enabled})

    # ---------- 属性编辑 ----------

    async def get_properties(request: web.Request) -> web.Response:
        instance = registry.get(request.match_info["id"])
        path = instance.root / "server.properties"
        if not path.is_file():
            return web.json_response({"ok": False, "error": "没有 server.properties"}, status=404)
        props = await asyncio.get_running_loop().run_in_executor(None, Properties.load, path)
        proc = current_app[PROCESSES_KEY].get(instance.id)
        return web.json_response(
            {
                "entries": props.as_list(),
                "read_only": bool(proc and proc.running),
                "text": props.to_text(),
            }
        )

    async def put_properties(request: web.Request) -> web.Response:
        instance = registry.get(request.match_info["id"])
        proc = current_app[PROCESSES_KEY].get(instance.id)
        if proc is not None and proc.running:
            return web.json_response({"ok": False, "error": "运行中只读，先停止服务器"}, status=409)
        payload = await _read_payload(request)
        changes = payload.get("values") or {}
        if not isinstance(changes, dict):
            return web.json_response({"ok": False, "error": "values 需要是对象"}, status=400)
        path = instance.root / "server.properties"
        props = await asyncio.get_running_loop().run_in_executor(None, Properties.load, path) if path.is_file() else Properties()
        backup = path.with_suffix(".properties.bak")
        if path.is_file():
            backup.write_bytes(path.read_bytes())
        for key, value in changes.items():
            if not str(key).strip():
                continue
            props.set(str(key).strip(), str(value))
        props.save(path)
        audit(request[SESSION_KEY].username, "properties", target=instance.id, result="ok",
              detail=", ".join(list(changes)[:8]))
        return web.json_response({"ok": True, "changed": list(changes), "backup": str(backup)})

    # ---------- 迁移 ----------

    async def migrate_instance(request: web.Request) -> web.Response:
        instance = registry.get(request.match_info["id"])
        payload = await _read_payload(request)
        target = str(payload.get("target", "")).strip()
        if not target:
            return web.json_response({"ok": False, "error": "缺少 target"}, status=400)
        proc = current_app[PROCESSES_KEY].get(instance.id)
        plan = await asyncio.get_running_loop().run_in_executor(
            None, plan_migration, instance, target, bool(proc and proc.running)
        )
        if not plan.ok:
            return web.json_response({"ok": False, "errors": plan.errors, "warnings": plan.warnings}, status=400)
        try:
            new_path = await asyncio.get_running_loop().run_in_executor(
                None, execute_migration, instance, plan, bool(payload.get("remove_source", True))
            )
        except (OSError, ValueError) as exc:
            return web.json_response({"ok": False, "errors": [str(exc)]}, status=500)
        registry.update(instance)
        audit(request[SESSION_KEY].username, "migrate", target=instance.id, result="ok", detail=str(new_path))
        return web.json_response(
            {"ok": True, "directory": str(new_path), "warnings": plan.warnings, "bytes": plan.total_bytes}
        )

    # ---------- bot ----------

    def _bot_auth(request: web.Request) -> dict[str, object] | None:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        return find_bot_token(db, header[7:].strip()) if db is not None else None

    def _bot_process(instance_name: str) -> tuple[str, InstanceProcess] | tuple[None, None]:
        instances = registry.all()
        if not instances:
            return None, None
        target = instances[0]
        if instance_name:
            for item in instances:
                if instance_name in (item.name, item.id):
                    target = item
                    break
        processes: dict[str, InstanceProcess] = current_app[PROCESSES_KEY]
        if target.id not in processes:
            processes[target.id] = InstanceProcess(target, log_dir)
        return target.name, processes[target.id]

    async def bot_guard(request: web.Request) -> tuple[dict[str, object] | None, web.Response | None]:
        token = _bot_auth(request)
        if token is None:
            return None, web.json_response({"ok": False, "error": "invalid token"}, status=401)
        wait = bot_limiter.check(int(token["id"]), request.headers.get("X-Bot-User", ""))
        if wait:
            message = str(config.get("bot.limit_message") or "查询太频繁，{wait} 秒后再试").replace(
                "{wait}", str(wait)
            )
            return token, web.json_response(
                {"ok": False, "error": message},
                status=429,
                headers={"Retry-After": str(wait)},
            )
        return token, None

    async def bot_status(request: web.Request) -> web.Response:
        token, blocked = await bot_guard(request)
        if blocked is not None:
            return blocked
        name, proc = _bot_process(request.query.get("instance", ""))
        if proc is None:
            return web.json_response({"ok": False, "error": "没有实例"}, status=404)
        data = status_payload(proc, name or "")
        if request.query.get("format") == "text":
            return web.Response(text=render_text(data, config), content_type="text/plain")
        return web.json_response(data)

    async def bot_players(request: web.Request) -> web.Response:
        token, blocked = await bot_guard(request)
        if blocked is not None:
            return blocked
        name, proc = _bot_process(request.query.get("instance", ""))
        if proc is None:
            return web.json_response({"ok": False, "error": "没有实例"}, status=404)
        return web.json_response(
            {"instance": name, "online": len(proc.players), "names": sorted(proc.players)}
        )

    async def bot_events(request: web.Request) -> web.Response:
        token, blocked = await bot_guard(request)
        if blocked is not None:
            return blocked
        name, proc = _bot_process(request.query.get("instance", ""))
        if proc is None:
            return web.json_response({"ok": False, "error": "没有实例"}, status=404)
        since = int(request.query.get("since", 0))
        events = [
            {**event, "instance": name}
            for event in proc.recent_events(since, int(request.query.get("limit", 50)))
        ]
        return web.json_response({"events": events})

    async def bot_tokens_list(_: web.Request) -> web.Response:
        return web.json_response({"tokens": list_bot_tokens(db) if db is not None else []})

    async def bot_tokens_create(request: web.Request) -> web.Response:
        payload = await _read_payload(request)
        group = str(payload.get("group", "")).strip()
        if not group:
            return web.json_response({"ok": False, "error": "缺少 group"}, status=400)
        token_id, token = create_bot_token(db, group, str(payload.get("label", "")))
        audit(request[SESSION_KEY].username, "bot.token", target=group, result="ok", detail=str(token_id))
        return web.json_response({"ok": True, "id": token_id, "token": token})

    async def bot_tokens_revoke(request: web.Request) -> web.Response:
        token_id = int(request.match_info["id"])
        ok = revoke_bot_token(db, token_id)
        if not ok:
            return web.json_response({"ok": False, "error": "不存在"}, status=404)
        audit(request[SESSION_KEY].username, "bot.token.revoke", target=str(token_id), result="ok")
        return web.json_response({"ok": True})


    # ---------- 诊断 ----------

    async def diagnose_instance(request: web.Request) -> web.Response:
        instance_id = request.match_info["id"]
        try:
            proc = process_for(instance_id)
        except InstanceNotFound:
            return web.json_response({"ok": False, "error": "实例不存在"}, status=404)
        lines = proc.snapshot(int(request.query.get("lines", 400)))
        findings = diagnose(lines)
        return web.json_response(
            {
                "instance": instance_id,
                "state": proc.state,
                "exit_code": proc.exit_code,
                "findings": [item.to_dict() for item in findings],
                "lines_scanned": len(lines),
            }
        )

    async def quick_commands(_: web.Request) -> web.Response:
        presets = [
            {"command": "list", "label": "看在线玩家", "confirm": False},
            {"command": "save-all", "label": "立即存盘", "confirm": False},
            {"command": "weather clear", "label": "切晴天", "confirm": False},
            {"command": "time set day", "label": "切白天", "confirm": False},
            {"command": "difficulty normal", "label": "难度调普通", "confirm": False},
            {"command": "whitelist reload", "label": "重载白名单", "confirm": True},
            {"command": "reload", "label": "重载数据包与配置", "confirm": True},
            {"command": "stop", "label": "停止服务器", "confirm": True},
        ]
        return web.json_response({"commands": presets})


    # ---------- 地图 ----------

    def map_secret() -> bytes:
        return load_secret(data_dir)

    def map_allowed(request: web.Request) -> bool:
        if sessions.get(request.cookies.get(COOKIE_NAME)):
            return True
        token = request.cookies.get("hoshi_map_share") or request.query.get("t", "")
        if not token:
            return False
        ok, _ = verify_share(map_secret(), token)
        return ok

    async def map_proxy(request: web.Request) -> web.StreamResponse:
        instances_all = registry.all()
        mapped = None
        for item in instances_all:
            if map_flag(item, "map.enabled"):
                mapped = item
                break
        if mapped is None:
            return web.json_response({"ok": False, "error": "地图未启用"}, status=404)
        token = request.query.get("t", "")
        if token and not sessions.get(request.cookies.get(COOKIE_NAME)):
            ok, instance = verify_share(map_secret(), token)
            if not ok:
                return web.Response(text="链接无效或已过期", status=403)
            response = web.HTTPFound("/map/")
            response.set_cookie("hoshi_map_share", token, httponly=True, samesite="Lax", path="/")
            raise response
        if not map_allowed(request):
            raise web.HTTPFound("/login")

        upstream = str(config.get("map.upstream")).rstrip("/")
        tail = request.match_info.get("tail", "")
        url = f"{upstream}/{tail}" if tail else f"{upstream}/"

        if tail in ("", "index.html"):
            try:
                async with map_http().get(url, allow_redirects=False) as resp:
                    if resp.status == 200:
                        html = await resp.text(errors="replace")
                        html = html.replace(
                            "</body>", '<script src="/map-overlay.js"></script></body>'
                        )
                        return web.Response(text=html, content_type="text/html")
                    return web.Response(text=await resp.text(errors="replace"), status=resp.status)
            except (aiohttp.ClientError, TimeoutError):
                return web.Response(text="地图服务未启动", status=502)
        try:
            async with map_http().get(url, allow_redirects=False) as resp:
                headers = {
                    key: value
                    for key, value in resp.headers.items()
                    if key.lower() in ("content-type", "cache-control", "etag", "last-modified")
                }
                out = web.StreamResponse(status=resp.status, headers=headers)
                await out.prepare(request)
                async for chunk in resp.content.iter_any():
                    await out.write(chunk)
                await out.write_eof()
                return out
        except (TimeoutError, aiohttp.ClientError):
            return web.Response(text="地图服务未启动", status=502)

    async def map_overlay_js(request: web.Request) -> web.Response:
        if not map_allowed(request):
            return web.Response(text="// unauthorized", content_type="application/javascript", status=401)
        return web.Response(text=MAP_OVERLAY_JS, content_type="application/javascript")

    def map_flag(instance: Instance | None, key: str):
        return resolve(config, instance, key)[0]

    def map_options(instance: Instance) -> MapOptions:
        def getter(key: str, default):
            value = resolve(config, instance, key)[0]
            return default if value is None else value

        return MapOptions.from_settings(getter)

    async def map_status(request: web.Request) -> web.Response:
        instance_id = request.query.get("instance", "")
        instances = registry.all()
        target = instances[0] if instances else None
        for item in instances:
            if instance_id and instance_id in (item.id, item.name):
                target = item
        data: dict[str, object] = {
            "enabled": bool(map_flag(target, "map.enabled")),
            "upstream": config.get("map.upstream"),
            "instances": [item.name for item in instances],
        }
        if target is not None:
            data["instance"] = target.name
            data["jar_installed"] = is_installed(target.root)
            data["plan"] = {
                "asset": bluemap_plan(target.root, data_dir).asset,
                "maps": bluemap_plan(target.root, data_dir).maps,
            }
            poller = pollers.get(target.id)
            data["players"] = poller.snapshot() if poller else {"connected": False, "players": []}
        return web.json_response(data)

    async def map_players(request: web.Request) -> web.Response:
        instance_id = request.query.get("instance", "")
        instances = registry.all()
        for item in instances:
            if instance_id in (item.id, item.name):
                poller = pollers.get(item.id)
                return web.json_response(poller.snapshot() if poller else {"connected": False, "players": []})
        if len(instances) == 1:
            poller = pollers.get(instances[0].id)
            return web.json_response(poller.snapshot() if poller else {"connected": False, "players": []})
        return web.json_response({"connected": False, "players": []})

    async def map_poll_start(request: web.Request) -> web.Response:
        instance = registry.get(request.match_info["id"])
        if not bool(map_flag(instance, "map.enabled")):
            return web.json_response({"ok": False, "error": "先给这个实例开启地图"}, status=400)
        props_path = instance.root / "server.properties"
        props = Properties.load(props_path) if props_path.is_file() else Properties()
        if props.get("enable-rcon", "false").lower() != "true":
            return web.json_response({"ok": False, "error": "server.properties 里 enable-rcon 不是 true"}, status=400)
        poller = PlayerPoller(
            host="127.0.0.1",
            port=int(props.get("rcon.port", "25575")),
            password=props.get("rcon.password", ""),
            interval=float(config.get("map.player_poll_seconds")),
        )
        pollers[instance.id] = poller
        await poller.start()
        await poller.poll_once()
        return web.json_response({"ok": True, **poller.snapshot()})

    def apply_markers(instance: Instance) -> dict[str, object]:
        """把标记写进 BlueMap 配置；服端在跑就顺手 reload。"""
        try:
            path = write_bluemap_markers(
                instance.root, data_dir, markers.list(instance.name), options=map_options(instance)
            )
        except FileNotFoundError:
            return {"applied": False, "reason": "先生成地图配置", "path": ""}
        except OSError as exc:
            return {"applied": False, "reason": str(exc), "path": ""}
        reloaded = False
        proc = current_app[PROCESSES_KEY].get(instance.id)
        if proc is not None and proc.running:
            result = await_send(proc, "bluemap reload")
            reloaded = bool(result)
        return {"applied": True, "path": str(path), "reloaded": reloaded}

    def await_send(proc: InstanceProcess, text: str) -> bool:
        """同步上下文里发命令，尽力而为。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        loop.create_task(proc.send(text))
        return True

    async def map_markers(request: web.Request) -> web.Response:
        instance = registry.get(request.query.get("instance", "")) if request.query.get("instance") else registry.all()[0]
        if request.method == "GET":
            return web.json_response({"markers": markers.list(instance.name)})
        payload = await _read_payload(request)
        if request.method == "DELETE":
            ok = markers.remove(instance.name, str(payload.get("id", request.query.get("id", ""))))
            applied = apply_markers(instance) if ok else {"applied": False}
            return web.json_response({"ok": ok, "bluemap": applied}, status=200 if ok else 404)
        try:
            marker = markers.add(
                instance.name,
                str(payload.get("name", "")),
                float(payload.get("x", 0)),
                float(payload.get("z", 0)),
                float(payload.get("y", 64)),
                str(payload.get("color", "red")),
                str(payload.get("note", "")),
            )
        except (TypeError, ValueError):
            return web.json_response({"ok": False, "error": "坐标需要是数字"}, status=400)
        applied = apply_markers(instance)
        audit(request[SESSION_KEY].username, "marker.add", target=instance.name, result="ok", detail=marker["name"])
        return web.json_response({"ok": True, "marker": marker, "bluemap": applied})

    async def map_purge(request: web.Request) -> web.Response:
        """删除已渲染的瓦片与数据，按钮需二次确认。"""
        payload = await _read_payload(request)
        if str(payload.get("confirm", "")) != "清理":
            return web.json_response({"ok": False, "error": "需要确认：确认框里输入「清理」"}, status=400)
        root = data_dir / "bluemap"
        freed = 0
        for sub in ("web/maps", "data"):
            target = root / sub
            if not target.exists():
                continue
            for item in target.rglob("*"):
                try:
                    if item.is_file():
                        freed += item.stat().st_size
                except OSError:
                    continue
            await asyncio.get_running_loop().run_in_executor(None, shutil.rmtree, target, True)
        audit(request[SESSION_KEY].username, "map.purge", target=str(root), result="ok", detail=f"{freed} bytes")
        return web.json_response({"ok": True, "freed_mb": round(freed / (1 << 20), 1)})

    async def map_apply_markers(request: web.Request) -> web.Response:
        instance = registry.get(request.match_info["id"])
        result = apply_markers(instance)
        return web.json_response({"ok": bool(result.get("applied")), **result})

    async def map_config(request: web.Request) -> web.Response:
        if request.method == "GET":
            instances = registry.all()
            if not instances:
                return web.json_response({"ok": False, "error": "没有实例"}, status=404)
            result = bluemap_plan(instances[0].root, data_dir)
            return web.json_response(
                {
                    "asset": result.asset,
                    "version": result.version,
                    "maps": result.maps,
                    "webroot": str(result.webroot),
                    "config_dir": str(result.config_dir),
                }
            )
        instance = registry.get(request.match_info.get("id", "") or registry.all()[0].id)
        payload = await _read_payload(request)
        result = write_bluemap_config(
            instance.root,
            data_dir,
            mc_version=str(payload.get("mc_version", "1.20.1")),
            accept_download=bool(map_flag(instance, "map.accept_download")),
            threads=int(map_flag(instance, "map.render_threads")),
            options=map_options(instance),
        )
        installed = False
        cached = find_cached(data_dir, result.asset)
        if cached is not None:
            install_jar(instance.root, cached)
            installed = True
        audit(request[SESSION_KEY].username, "map.config", target=instance.id, result="ok", detail=result.asset)
        return web.json_response(
            {
                "ok": True,
                "asset": result.asset,
                "config_dir": str(result.config_dir),
                "webroot": str(result.webroot),
                "jar_installed": installed,
                "cached": bool(cached),
            }
        )

    async def map_share(request: web.Request) -> web.Response:
        payload = await _read_payload(request)
        instance_name = str(payload.get("instance") or (registry.all()[0].name if registry.all() else "map"))
        ttl = int(config.get("map.share_ttl_hours")) * 3600
        token = issue_share(map_secret(), instance_name, ttl, str(payload.get("label", "")))
        audit(request[SESSION_KEY].username, "map.share", target=instance_name, result="ok")
        return web.json_response({"ok": True, "url": f"/map/?t={token}", "ttl_hours": ttl // 3600})


    # ---------- 单实例设置 ----------

    UPDATE_FIELDS = (
        "name",
        "java",
        "min_memory_mb",
        "max_memory_mb",
        "jvm_args",
        "encoding",
        "nogui",
        "jar",
        "args_file",
        "user_jvm_args",
    )

    async def get_instance_settings(request: web.Request) -> web.Response:
        instance = registry.get(request.match_info["id"])
        return web.json_response(instance.to_dict())

    async def update_instance(request: web.Request) -> web.Response:
        instance = registry.get(request.match_info["id"])
        proc = current_app[PROCESSES_KEY].get(instance.id)
        if proc is not None and proc.running:
            return web.json_response({"ok": False, "error": "运行中不能改设置，先停止"}, status=409)
        payload = await _read_payload(request)
        changed: list[str] = []
        for key in UPDATE_FIELDS:
            if key not in payload:
                continue
            value = payload[key]
            if key in ("min_memory_mb", "max_memory_mb"):
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    return web.json_response({"ok": False, "error": f"{key} 需要整数"}, status=400)
            elif key == "jvm_args":
                if isinstance(value, str):
                    value = [item for item in value.replace(",", " ").split() if item]
                if not isinstance(value, list):
                    return web.json_response({"ok": False, "error": "jvm_args 需要列表"}, status=400)
                value = [str(item) for item in value]
            elif key == "nogui":
                value = bool(value)
            else:
                value = str(value)
            if getattr(instance, key) != value:
                setattr(instance, key, value)
                changed.append(key)
        try:
            instance.validate()
        except InstanceError as exc:
            registry.load()
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        if changed:
            registry.update(instance)
            audit(request[SESSION_KEY].username, "instance.update", target=instance.id, result="ok",
                  detail=", ".join(changed))
        return web.json_response({"ok": True, "changed": changed, "instance": instance.to_dict()})

    # ---------- 目录浏览 ----------

    async def fs_list(request: web.Request) -> web.Response:
        import string

        raw = request.query.get("path", "")
        if not raw:
            if os.name == "nt":
                drives = [f"{letter}:\\" for letter in string.ascii_uppercase if Path(f"{letter}:\\").exists()]
                return web.json_response({"path": "", "entries": [{"name": d, "path": d} for d in drives], "parent": ""})
            return web.json_response(
                {"path": "/", "entries": [{"name": "/", "path": "/"}], "parent": ""}
            )
        target = Path(raw).expanduser()
        if not target.is_dir():
            return web.json_response({"ok": False, "error": "目录不存在"}, status=404)
        entries = []
        try:
            children = sorted(target.iterdir(), key=lambda p: p.name.lower())
        except OSError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        want_files = request.query.get("files") == "1"
        suffix = request.query.get("suffix", "")
        for child in children:
            try:
                if child.is_dir():
                    entries.append({"name": child.name, "path": str(child), "type": "dir"})
                elif want_files and (not suffix or child.suffix.lower() == suffix.lower()):
                    entries.append({"name": child.name, "path": str(child), "type": "file"})
            except OSError:
                continue
        return web.json_response({"path": str(target), "entries": entries, "parent": str(target.parent)})


    # ---------- 实例级设置 ----------

    async def instance_settings(request: web.Request) -> web.Response:
        instance = registry.get(request.match_info["id"])
        items = effective(config, instance)
        if request.method == "GET":
            return web.json_response(
                {
                    "instance": {"id": instance.id, "name": instance.name},
                    "items": list(items.values()),
                    "overrides": dict(instance.settings),
                }
            )
        payload = await _read_payload(request)
        values = payload.get("values") or {}
        if not isinstance(values, dict):
            return web.json_response({"ok": False, "error": "values 需要是对象"}, status=400)
        changed: list[str] = []
        for key, raw in values.items():
            if key not in PER_INSTANCE_KEYS:
                return web.json_response({"ok": False, "error": f"不支持按实例设置的项: {key}"}, status=400)
            try:
                value = coerce_value(key, raw)
            except (ValueError, TypeError) as exc:
                return web.json_response({"ok": False, "error": str(exc)}, status=400)
            if raw is None:
                instance.settings.pop(key, None)
                changed.append(key)
                continue
            if instance.settings.get(key) != value:
                instance.settings[key] = value
                changed.append(key)
        if changed:
            registry.update(instance)
            audit(request[SESSION_KEY].username, "instance.settings", target=instance.id, result="ok",
                  detail=", ".join(changed))
        return web.json_response({"ok": True, "changed": changed, "items": list(effective(config, instance).values())})

    async def instance_setting_reset(request: web.Request) -> web.Response:
        instance = registry.get(request.match_info["id"])
        key = request.match_info["key"]
        if key not in instance.settings:
            return web.json_response({"ok": False, "error": "没有覆盖"}, status=404)
        instance.settings.pop(key, None)
        registry.update(instance)
        audit(request[SESSION_KEY].username, "instance.settings.reset", target=instance.id, result="ok", detail=key)
        return web.json_response({"ok": True, "items": list(effective(config, instance).values())})

    async def metrics_endpoint(_: web.Request) -> web.Response:
        processes = {
            instance_id: proc.pid
            for instance_id, proc in current_app[PROCESSES_KEY].items()
            if proc.pid
        }
        return web.json_response(sampler.to_dict(processes))


    # ---------- 地图：安装与 RCON ----------

    async def map_install(request: web.Request) -> web.Response:
        instance = registry.get(request.match_info["id"])
        detected = detect(instance.root)
        mc_version = (detected.mc_version or "1.20.1").strip()
        loader = (detected.loader or "forge").strip()
        mirror = str(config.get("map.download_mirror") or "").strip()
        job = jobs.create("bluemap-install")
        jobs.update(job["id"], phase="准备中")

        async def run() -> None:
            try:
                if mirror:
                    filename = mirror.rstrip("/").split("/")[-1] or "bluemap.jar"
                    dl = bluemap_installer.Download(url=mirror, filename=filename, source="mirror")
                else:
                    jobs.update(job["id"], phase="查询 Modrinth")
                    dl = await bluemap_installer.resolve_modrinth(mc_version, loader)
                if dl is None:
                    jobs.finish(job["id"], error=f"Modrinth 上没有匹配的版本（{loader} {mc_version}）")
                    return
                jobs.update(job["id"], phase="下载中")
                jar = await bluemap_installer.download(
                    data_dir / "packages" / "bluemap",
                    dl,
                    progress=lambda done, total: jobs.update(
                        job["id"], done=done, total=total, phase="下载中"
                    ),
                )
                jobs.update(job["id"], phase="安装到实例")
                target = install_jar(instance.root, jar)
                result = write_bluemap_config(
                    instance.root,
                    data_dir,
                    mc_version=mc_version,
                    accept_download=bool(map_flag(instance, "map.accept_download")),
                    threads=int(map_flag(instance, "map.render_threads")),
                    options=map_options(instance),
                )
                jobs.finish(
                    job["id"],
                    result={
                        "jar": str(target),
                        "asset": result.asset,
                        "source": dl.source,
                        "config_dir": str(result.config_dir),
                    },
                )
                audit("system", "map.install", target=instance.id, result="ok", detail=dl.filename)
            except Exception as exc:
                jobs.finish(job["id"], error=str(exc))

        asyncio.create_task(run())
        return web.json_response({"ok": True, "job": jobs.get(job["id"]), "mc": mc_version, "loader": loader})

    async def rcon_settings(request: web.Request) -> web.Response:
        instance = registry.get(request.match_info["id"])
        path = instance.root / "server.properties"
        props = Properties.load(path) if path.is_file() else Properties()
        if request.method == "GET":
            poller = pollers.get(instance.id)
            return web.json_response(
                {
                    "enabled": props.get("enable-rcon", "false").lower() == "true",
                    "port": props.get("rcon.port", "25575"),
                    "password_set": bool(props.get("rcon.password", "")),
                    "poller": poller.snapshot() if poller else None,
                }
            )
        proc = current_app[PROCESSES_KEY].get(instance.id)
        if proc is not None and proc.running:
            return web.json_response({"ok": False, "error": "运行中只读，先停服再改"}, status=409)
        payload = await _read_payload(request)
        enable = bool(payload.get("enabled", True))
        port = int(payload.get("port", 25575) or 25575)
        password = str(payload.get("password", ""))
        if port < 1 or port > 65535:
            return web.json_response({"ok": False, "error": "端口不合法"}, status=400)
        if enable and not password:
            return web.json_response({"ok": False, "error": "开启 RCON 必须设密码"}, status=400)
        props.set("enable-rcon", "true" if enable else "false")
        props.set("rcon.port", str(port))
        if password:
            props.set("rcon.password", password)
        backup = path.with_suffix(".properties.bak")
        if path.is_file():
            backup.write_bytes(path.read_bytes())
        props.save(path)
        audit(request[SESSION_KEY].username, "rcon.settings", target=instance.id, result="ok",
              detail=f"enable={enable} port={port}")
        return web.json_response({"ok": True, "hint": "重启服务器后生效"})


    # ---------- 导入整合包：三种方式 ----------

    def remote_import_state() -> dict[str, object]:
        allowed = bool(config.get("files.allow_remote_download"))
        return {
            "enabled": allowed,
            "reason": "" if allowed else "未允许服务器从网址下载",
            "how": "设置页 →「允许服务器从网址下载 zip」打开，保存后重试。不需要开放公网。",
            "risk": "开启后服务器会按你填的地址主动发起下载，地址由你决定，"
                    "只要确保它指向可信来源（自己的对象存储或官方发布页），不要粘来路不明的链接。",
            "hint": "服务器自己去下载这个地址，下载完就解压。要求该地址是直链，且服务器能上网。",
        }

    async def pack_options(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "adopt": {
                    "enabled": True,
                    "summary": "直接接管服务器上已有的服务端目录，不复制文件",
                    "hint": "只登记目录位置，文件原地不动。选完填个名字即可。",
                },
                "zip": {
                    "enabled": True,
                    "summary": "把你这台电脑上的 zip 传到服务器",
                    "hint": "文件经浏览器上传到面板，再解压到服务器。占用你的上行带宽，"
                            "面板只在本机时请用 SSH 隧道访问。",
                },
                "path": {
                    "enabled": True,
                    "summary": "服务器磁盘上已有的 zip 文件，就地解压",
                    "hint": "不上传任何数据，只把服务器上的 zip 解开。适合先用 scp 传包的情况。",
                },
                "remote": remote_import_state(),
            }
        )

    async def adopt_pack(request: web.Request) -> web.Response:
        payload = await _read_payload(request)
        raw = str(payload.get("directory", "")).strip()
        if not raw:
            return web.json_response({"ok": False, "error": "缺少目录"}, status=400)
        target = Path(raw).expanduser().resolve()
        if not target.is_dir():
            return web.json_response({"ok": False, "error": "目录不存在"}, status=404)
        existing = registry.find_by_directory(str(target))
        if existing is not None:
            return web.json_response({"ok": False, "error": f"已注册：{existing.name}"}, status=409)
        detected = detect(target)
        if not detected.ok:
            return web.json_response(
                {"ok": False, "error": "识别失败：没有找到核心 jar 或 args 文件"}, status=422
            )
        name = str(payload.get("name") or target.name)
        java = str(payload.get("java") or "")
        if not java:
            found = await asyncio.get_running_loop().run_in_executor(None, scan)
            chosen = pick_for(detected.mc_version or "1.20.1", found) or (found[0] if found else None)
            java = chosen.path if chosen else ""
        try:
            instance = Instance.new(
                name=name,
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
        except InstanceError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        audit(request[SESSION_KEY].username, "pack.adopt", target=instance.id, result="ok", detail=name)
        return web.json_response({"ok": True, "instance": instance.to_dict(), "detected": detected.summary()})

    async def import_path(request: web.Request) -> web.Response:
        """服务器磁盘上已有的 zip，就地解压导入。"""
        payload = await _read_payload(request)
        raw = str(payload.get("path", "")).strip()
        if not raw:
            return web.json_response({"ok": False, "error": "缺少 zip 路径"}, status=400)
        source = Path(raw).expanduser()
        if not source.is_file() or source.suffix.lower() != ".zip":
            return web.json_response({"ok": False, "error": "不是一个 zip 文件"}, status=400)
        name = str(payload.get("name", "")).strip() or source.stem
        servers_dir = Path(str(config.get("app.servers_dir"))).expanduser().resolve()
        target = servers_dir / name
        if target.exists():
            return web.json_response({"ok": False, "error": "目标目录已存在"}, status=409)

        job = jobs.create("path-import", total=1)
        jobs.update(job["id"], phase="解压中")
        target.mkdir(parents=True, exist_ok=True)

        def work() -> list[str]:
            return safe_extract(
                source,
                target,
                progress=lambda done, total: jobs.update(
                    job["id"], done=done, total=total, phase="解压中"
                ),
            )

        try:
            skipped = await asyncio.get_running_loop().run_in_executor(None, work)
        except Exception as exc:
            jobs.finish(job["id"], error=str(exc))
            return web.json_response({"ok": False, "error": f"解压失败：{exc}"}, status=500)
        jobs.update(job["id"], phase="识别中")
        detected = detect(target)
        if not detected.ok:
            jobs.finish(job["id"], error="识别失败，需要手动添加实例")
            return web.json_response(
                {"ok": False, "error": "识别失败，需要手动添加实例", "path": str(target)}, status=422
            )
        found = await asyncio.get_running_loop().run_in_executor(None, scan)
        chosen = pick_for(detected.mc_version or "1.20.1", found) or (found[0] if found else None)
        try:
            instance = Instance.new(
                name=name,
                directory=str(target),
                launch_mode=detected.launch_mode,
                jar=detected.jar,
                args_file=detected.args_file,
                user_jvm_args=detected.user_jvm_args,
                java=chosen.path if chosen else "",
                min_memory_mb=2048,
                max_memory_mb=8192,
            )
            registry.add(instance)
        except InstanceError as exc:
            jobs.finish(job["id"], error=str(exc))
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        jobs.finish(job["id"], result={"instance": instance.to_dict(), "skipped": skipped})
        audit(request[SESSION_KEY].username, "pack.import_path", target=instance.id, result="ok", detail=str(source)[:120])
        return web.json_response(
            {"ok": True, "job": jobs.get(job["id"]), "instance": instance.to_dict(), "skipped": skipped}
        )

    async def import_url(request: web.Request) -> web.Response:
        state = remote_import_state()
        if not state["enabled"]:
            return web.json_response(
                {"ok": False, "error": state["reason"], "how": state["how"], "risk": state["risk"]},
                status=403,
            )
        payload = await _read_payload(request)
        url = str(payload.get("url", "")).strip()
        if not url.lower().startswith(("http://", "https://")):
            return web.json_response({"ok": False, "error": "只接受 http 或 https 地址"}, status=400)
        name = str(payload.get("name", "")).strip() or f"pack-{int(time.time())}"
        servers_dir = Path(str(config.get("app.servers_dir"))).expanduser().resolve()
        target = servers_dir / name
        if target.exists():
            return web.json_response({"ok": False, "error": "目标目录已存在"}, status=409)

        limit = int(config.get("files.max_upload_mb")) * 1024 * 1024
        job = jobs.create("remote-import", total=0)
        upload_dir = data_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        temp = upload_dir / f"{uuid.uuid4().hex}.zip"

        async def run() -> None:
            try:
                jobs.update(job["id"], phase="下载中")
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=600, connect=15)
                ) as session:
                    async with session.get(url, headers={"User-Agent": "hoshi-panel/0.1"}) as resp:
                        if resp.status != 200:
                            jobs.finish(job["id"], error=f"下载失败：HTTP {resp.status}")
                            return
                        total = int(resp.headers.get("Content-Length") or 0)
                        written = 0
                        with temp.open("wb") as fh:
                            async for chunk in resp.content.iter_chunked(1 << 16):
                                written += len(chunk)
                                if written > limit:
                                    fh.close()
                                    temp.unlink(missing_ok=True)
                                    jobs.finish(job["id"], error=f"超过上限 {limit // (1024 * 1024)} MB")
                                    return
                                fh.write(chunk)
                                jobs.update(job["id"], done=written, total=total or written, phase="下载中")
                jobs.update(job["id"], phase="解压中")
                target.mkdir(parents=True, exist_ok=True)
                skipped = await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: safe_extract(
                        temp,
                        target,
                        progress=lambda done, total: jobs.update(
                            job["id"], done=done, total=total, phase="解压中"
                        ),
                    ),
                )
                temp.unlink(missing_ok=True)
                jobs.update(job["id"], phase="识别中")
                detected = detect(target)
                if not detected.ok:
                    jobs.finish(job["id"], error="识别失败，需要手动添加实例")
                    return
                found = await asyncio.get_running_loop().run_in_executor(None, scan)
                chosen = pick_for(detected.mc_version or "1.20.1", found) or (found[0] if found else None)
                instance = Instance.new(
                    name=name,
                    directory=str(target),
                    launch_mode=detected.launch_mode,
                    jar=detected.jar,
                    args_file=detected.args_file,
                    user_jvm_args=detected.user_jvm_args,
                    java=chosen.path if chosen else "",
                    min_memory_mb=2048,
                    max_memory_mb=8192,
                )
                registry.add(instance)
                jobs.finish(job["id"], result={"instance": instance.to_dict(), "skipped": skipped})
                audit("system", "pack.import_url", target=instance.id, result="ok", detail=url[:80])
            except Exception as exc:
                temp.unlink(missing_ok=True)
                jobs.finish(job["id"], error=str(exc))

        asyncio.create_task(run())
        return web.json_response({"ok": True, "job": jobs.get(job["id"])})

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
                try:
                    await ws.send_json(message)
                except (ConnectionResetError, ConnectionAbortedError):
                    return

        pump_task = asyncio.create_task(pump())
        try:
            async for message in ws:
                if message.type == WSMsgType.TEXT:
                    with contextlib.suppress(json.JSONDecodeError):
                        payload = json.loads(message.data)
                        if payload.get("type") != "command":
                            continue
                        ws_instance = registry.get(instance_id)
                        allowed, reason = commands.check(
                            str(payload.get("text", "")),
                            mode=str(resolve(config, ws_instance, "console.command_mode")[0]),
                            extra=list(resolve(config, ws_instance, "console.extra_commands")[0] or []),
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

    async def custom_css(_: web.Request) -> web.Response:
        path = data_dir / "theme.css"
        if not path.is_file():
            return web.Response(text="/* 在 data/theme.css 里写自定义样式 */", content_type="text/css")
        return web.Response(
            text=path.read_text(encoding="utf-8", errors="replace"),
            content_type="text/css",
            headers={"Cache-Control": "no-cache"},
        )

    async def theme_info(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "theme": str(config.get("web.theme")),
                "custom_css": "/assets/custom.css",
                "variables": {
                    "--hoshi-accent": "主题强调色",
                    "--hoshi-radius": "卡片圆角",
                    "--tblr-body-font-size": "正文字号",
                    "--tblr-font-sans-serif": "界面字体",
                },
                "howto": "把覆盖样式写到 data/theme.css，刷新页面即生效",
            }
        )

    async def tabler_css(_: web.Request) -> web.Response:
        return web.Response(
            text=TABLER_CSS,
            content_type="text/css",
            headers={"Cache-Control": "public, max-age=86400"},
        )

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

    async def quiet_disconnects(_: web.Application) -> None:
        install_for_running_loop()

    app = web.Application(middlewares=[require_session])
    app.on_startup.append(quiet_disconnects)
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
    jobs = JobStore()
    sampler = MetricsSampler()
    markers = MarkerStore(data_dir / "markers")
    pollers: dict[str, PlayerPoller] = {}
    map_session: aiohttp.ClientSession | None = None

    def map_http() -> aiohttp.ClientSession:
        nonlocal map_session
        if map_session is None or map_session.closed:
            map_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25, connect=3))
        return map_session
    bot_limiter = TokenLimiter(
        group_limit=int(config.get("bot.group_limit")),
        user_limit=int(config.get("bot.user_limit")),
    )

    app.router.add_get("/login", login_page)
    app.router.add_post("/api/login", login_submit)
    app.router.add_post("/api/logout", logout)
    app.router.add_get("/", overview)
    app.router.add_get("/i/{id}", instance_page)
    app.router.add_get("/settings", settings_page)
    app.router.add_get("/api/health", health)
    app.router.add_get("/assets/tabler.css", tabler_css)
    app.router.add_get("/assets/custom.css", custom_css)
    app.router.add_get("/api/theme", theme_info)
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
    app.router.add_get("/api/instances/{id}/settings", get_instance_settings)
    app.router.add_route("*", "/api/instances/{id}/instance-settings", instance_settings)
    app.router.add_post("/api/instances/{id}/instance-settings/{key}/reset", instance_setting_reset)
    app.router.add_get("/api/metrics", metrics_endpoint)
    app.router.add_patch("/api/instances/{id}", update_instance)
    app.router.add_get("/api/fs/list", fs_list)
    app.router.add_get("/api/jobs/{id}", job_status)
    app.router.add_post("/api/jobs/{id}/cancel", job_cancel)
    app.router.add_get("/api/jobs/{id}/download", export_download)
    app.router.add_post("/api/instances/{id}/{action:start|stop|kill}", instance_action)
    app.router.add_get("/api/instances/{id}/log", instance_log)
    app.router.add_post("/api/instances/{id}/command", instance_command)
    app.router.add_get("/api/instances/{id}/files", list_files)
    app.router.add_get("/api/instances/{id}/file", read_file)
    app.router.add_put("/api/instances/{id}/file", write_file)
    app.router.add_delete("/api/instances/{id}/file", delete_file)
    app.router.add_post("/api/instances/{id}/export", export_zip)
    app.router.add_post("/api/instances/{id}/import", import_zip)
    app.router.add_post("/api/instances/{id}/backup", backups_create)
    app.router.add_get("/api/instances/{id}/backups", backups_list)
    app.router.add_post("/api/instances/{id}/backups/{name}/restore", backups_restore)
    app.router.add_delete("/api/instances/{id}/backups/{name}", backups_delete)
    app.router.add_post("/api/packs/import", import_pack)
    app.router.add_get("/api/packs/import-options", pack_options)
    app.router.add_post("/api/packs/adopt", adopt_pack)
    app.router.add_post("/api/packs/import-url", import_url)
    app.router.add_post("/api/packs/import-path", import_path)
    app.router.add_get("/api/instances/{id}/mods", list_mods)
    app.router.add_post("/api/instances/{id}/mods/toggle", toggle_mod_handler)
    app.router.add_post("/api/instances/{id}/mods/upload", upload_mod)
    app.router.add_get("/api/instances/{id}/properties", get_properties)
    app.router.add_put("/api/instances/{id}/properties", put_properties)
    app.router.add_post("/api/instances/{id}/migrate", migrate_instance)
    app.router.add_get("/api/instances/{id}/diagnose", diagnose_instance)
    app.router.add_get("/api/map/status", map_status)
    app.router.add_get("/api/map/players", map_players)
    app.router.add_post("/api/instances/{id}/map/markers/apply", map_apply_markers)
    app.router.add_post("/api/instances/{id}/map/install", map_install)
    app.router.add_post("/api/instances/{id}/map/purge", map_purge)
    app.router.add_route("*", "/api/instances/{id}/rcon", rcon_settings)
    app.router.add_post("/api/instances/{id}/map/poll", map_poll_start)
    app.router.add_route("*", "/api/map/markers", map_markers)
    app.router.add_get("/api/map/config", map_config)
    app.router.add_post("/api/instances/{id}/map/config", map_config)
    app.router.add_post("/api/map/share", map_share)
    app.router.add_get("/map-overlay.js", map_overlay_js)
    app.router.add_get("/map/{tail:.*}", map_proxy)
    app.router.add_get("/api/commands", quick_commands)
    app.router.add_get("/api/bot/status", bot_status)
    app.router.add_get("/api/bot/players", bot_players)
    app.router.add_get("/api/bot/events", bot_events)
    app.router.add_get("/api/bot/tokens", bot_tokens_list)
    app.router.add_post("/api/bot/tokens", bot_tokens_create)
    app.router.add_delete("/api/bot/tokens/{id}", bot_tokens_revoke)
    app.router.add_get("/api/java", java_list)
    app.router.add_get("/api/java/probe", java_probe)
    app.router.add_get("/ws/console/{id}", ws_console)
    app.router.add_route("*", "/{tail:.*}", not_found)

    async def close_map(_: web.Application) -> None:
        for poller in pollers.values():
            await poller.stop()
        if map_session is not None and not map_session.closed:
            await map_session.close()

    async def close_processes(_: web.Application) -> None:
        processes: dict[str, InstanceProcess] = app[PROCESSES_KEY]
        for proc in processes.values():
            await proc.shutdown()

    app.on_shutdown.append(close_processes)
    app.on_shutdown.append(close_map)
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

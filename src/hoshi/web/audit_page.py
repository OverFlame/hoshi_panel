"""审计与改动历史页面。

一条时间线：谁在什么时候做了什么，结果如何。
"""

from __future__ import annotations

AUDIT_HTML = """<!doctype html>
<html lang="zh-CN" data-bs-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>审计 · {{app}}</title>
<style>
 :root{color-scheme:dark}
 body{margin:0;font:14px/1.6 system-ui,sans-serif;background:#0f1115;color:#e6e6e6}
 header{display:flex;justify-content:space-between;align-items:center;padding:12px 18px;border-bottom:1px solid #23262d}
 main{padding:16px 18px 60px;max-width:1100px}
 .tabs{display:flex;gap:8px;margin-bottom:12px}
 .tab{padding:6px 12px;border-radius:6px;border:1px solid #333;background:#1b1f27;color:#e6e6e6;cursor:pointer}
 .tab.active{border-color:#2f6fed;background:#182338}
 table{border-collapse:collapse;width:100%;font-size:.85rem}
 th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #23262d;vertical-align:top}
 th{color:#9db4d0;font-weight:600}
 code{font-family:ui-monospace,monospace;font-size:.8rem}
 .ok{color:#8ff0c0}.fail{color:#ffb4b4}.other{color:#ffd28a}
 .muted{opacity:.6}
 a{color:#8ab4ff}
 input,select{background:#141821;color:#e6e6e6;border:1px solid #333;border-radius:6px;padding:6px 8px}
</style><style>
:root{--tblr-body-font-size:.85rem;--tblr-body-font-size-xs:.78rem}
body{font-size:.85rem}
.btn-sm{padding:.22rem .55rem;font-size:.78rem;line-height:1.2}
.card-body{padding:12px 14px}
</style>
<link rel="stylesheet" href="/assets/tabler.css"></head>
<body>
<header><h1 style="font-size:1rem;margin:0">{{app}} 审计</h1><div><a href="/">返回</a></div></header>
<main>
<div class="tabs">
  <button class="tab active" data-view="audit">操作审计</button>
  <button class="tab" data-view="settings">设置改动</button>
  <input id="filter" placeholder="按动作过滤，例如 login、command（仅审计）">
  <button class="tab" id="reload">刷新</button>
</div>
<table><thead><tr id="head"></tr></thead><tbody id="body"></tbody></table>
<p class="muted" id="empty" style="display:none">没有记录。</p>
</main>
<script>
let view='audit';
const $=id=>document.getElementById(id);
function cls(result){return result==='ok'?'ok':(result==='fail'||result==='denied'||result==='locked')?'fail':'other'}
async function load(){
  const filter=$('filter').value.trim();
  if(view==='audit'){
    const r=await fetch('/api/audit?limit=200&action='+encodeURIComponent(filter));
    const data=await r.json();
    $('head').innerHTML='<th>时间</th><th>操作者</th><th>动作</th><th>对象</th><th>结果</th><th>细节</th>';
    $('body').innerHTML=data.items.map(it=>`<tr><td class="muted">${it.ts}</td><td>${it.actor}</td>
      <td><code>${it.action}</code></td><td><code>${it.target||''}</code></td>
      <td class="${cls(it.result)}">${it.result}</td><td class="muted">${it.detail||''}</td></tr>`).join('');
    $('empty').style.display=data.items.length?'none':'block';
  } else {
    const r=await fetch('/api/settings/history');
    const data=await r.json();
    $('head').innerHTML='<th>时间</th><th>操作者</th><th>配置项</th><th>旧值</th><th>新值</th>';
    $('body').innerHTML=data.items.map(it=>`<tr><td class="muted">${it.ts}</td><td>${it.actor}</td>
      <td><code>${it.key}</code></td><td class="muted">${it.old_value??''}</td><td>${it.new_value??''}</td></tr>`).join('');
    $('empty').style.display=data.items.length?'none':'block';
  }
}
document.querySelectorAll('.tab[data-view]').forEach(t=>t.onclick=()=>{
  document.querySelectorAll('.tab[data-view]').forEach(x=>x.classList.remove('active'));
  t.classList.add('active'); view=t.dataset.view; $('filter').style.display=view==='audit'?'':'none'; load();
});
$('reload').onclick=load;
load();

function unifyButtons(){
  document.querySelectorAll('button').forEach(b=>{
    if(!b.classList.contains('btn')){b.classList.add('btn','btn-sm')}
  });
}
unifyButtons();
</script>
</body></html>
"""

"""首页模板：实例列表、控制台、文件、备份。

模板用 {{token}} 占位，避免 JS 模板字符串里的 $ 被误解析。
"""

INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN" data-bs-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{app}} · {{instance_name}}</title>
<style>
 :root{color-scheme:dark}
 html,body{height:100%}
 body{margin:0;display:flex;flex-direction:column;height:100vh;overflow:hidden;font:14px/1.55 system-ui,sans-serif;background:#0f1115;color:#e6e6e6}
 header{display:flex;justify-content:space-between;align-items:center;padding:12px 18px;border-bottom:1px solid #23262d}
 header h1{font-size:1rem;margin:0;font-weight:600}
 .banner{padding:6px 18px;font-size:.82rem;background:#2a2013;color:#ffd28a;border-bottom:1px solid #3d2f16}
 .banner.local{background:#13221a;color:#8ff0c0;border-color:#1c3a2a}
 main{display:flex;flex:1;min-height:0}
 aside{border-right:1px solid #23262d;overflow:auto;padding:10px}
 .inst{padding:10px;border:1px solid #23262d;border-radius:8px;margin-bottom:8px;cursor:pointer}
 .inst.active{border-color:#2f6fed}
 .row{display:flex;justify-content:space-between;align-items:center;gap:8px}
 .state{font-size:.78rem;padding:1px 7px;border-radius:99px;background:#2a2f3a}
 .state.running{background:#17543b;color:#8ff0c0}
 .state.crashed{background:#5a1d1d;color:#ffb4b4}
 button{padding:4px 9px;border-radius:6px;border:1px solid #333;background:#1b1f27;color:#e6e6e6;cursor:pointer;font-size:.85rem}
 button:hover{border-color:#2f6fed}
 button.primary{background:#2f6fed;border-color:#2f6fed}
 section{display:flex;flex-direction:column;flex:1;min-width:0;min-height:0}
 .tabs{display:flex;gap:6px;padding:8px 10px;border-bottom:1px solid #23262d}
 .tab{padding:4px 10px;border-radius:6px;border:1px solid #333;background:#1b1f27;color:#e6e6e6;cursor:pointer;font-size:.85rem}
 .tab.active{border-color:#2f6fed;background:#182338}
 .pane{flex:1;min-height:0;display:none;flex-direction:column;overflow:hidden;width:100%}
 .pane.active{display:flex}
 #console{flex:1;min-height:0;margin:0;padding:12px;overflow:auto;white-space:pre-wrap;word-break:break-all;font:12px/1.5 ui-monospace,monospace;background:#0b0d11}
 #cmd{display:flex;gap:8px;padding:10px;border-top:1px solid #23262d}
 #cmd input{flex:1;padding:8px;border-radius:6px;border:1px solid #333;background:#141821;color:#e6e6e6}
 .toolbar{display:flex;gap:8px;align-items:center;padding:8px 10px;border-bottom:1px solid #23262d;font-size:.85rem}
 .toolbar input{padding:6px 8px;border-radius:6px;border:1px solid #333;background:#141821;color:#e6e6e6}
 #filelist,#backuplist,#modlist{flex:1;min-height:0;overflow:auto;padding:0 10px 10px}
 #inssettings,#markerlist{min-height:0}
 .fitem,.bitem{display:flex;justify-content:space-between;gap:8px;padding:6px 4px;border-bottom:1px solid #1c1f26;font-size:.85rem}
 .fitem{cursor:pointer}
 .fitem:hover{background:#141821}
 .fname{font-family:ui-monospace,monospace}
 .muted{opacity:.6}
 a{color:#8ab4ff}
 #editor{position:fixed;inset:5% 8%;background:#12151b;border:1px solid #2c313a;border-radius:10px;display:none;flex-direction:column;padding:10px;z-index:20}
 #editor textarea{flex:1;width:100%;background:#0b0d11;color:#e6e6e6;border:1px solid #262b33;border-radius:8px;padding:8px;font:12px/1.5 ui-monospace,monospace}
 #editor .row{padding-top:8px}
 #console .line{padding:0 2px;white-space:pre-wrap;word-break:break-all}
 #console .lv-warn{color:#ffd28a}
 #console .lv-error{color:#ff8a8a}
 #console .lv-debug,#console .lv-trace{color:#8a93a3}
 #console .lv-join{color:#8ff0c0}
 #console .lv-leave{color:#ffb27a}
 #console .lv-panel{color:#8ab4ff}
 #console{font-family:"JetBrainsMono Nerd Font","JetBrains Mono Web","JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
</style><style>
:root{--tblr-body-font-size:.85rem;--tblr-body-font-size-xs:.78rem}
body{font-size:.85rem}
.btn-sm{padding:.22rem .55rem;font-size:.78rem;line-height:1.2}
.card-body{padding:12px 14px}
</style>
<link rel="stylesheet" href="/assets/tabler.css">
<style>:root{--tblr-body-font-size:.85rem;--tblr-body-font-size-xs:.78rem;--hoshi-accent:#2f6fed;--hoshi-radius:10px;--tblr-font-sans-serif:"JetBrainsMono Nerd Font","JetBrains Mono Web","JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}body{font-family:var(--tblr-font-sans-serif);font-size:.85rem}.btn-sm{padding:.22rem .55rem;font-size:.78rem;line-height:1.2}.card-body{padding:12px 14px}</style>
<link rel="stylesheet" href="/assets/custom.css"></head>
<body>
<header><h1><a href="/">← 概览</a> · {{instance_name}}</h1>
<div style="display:flex;gap:10px;align-items:center">
  <a href="#" id="import-pack">导入整合包</a>
  <a href="/settings">设置</a><a href="/audit">审计</a>
  <span class="muted">{{user}}</span>
  <button id="logout">退出</button>
</div></header>
<div class="banner {{banner_class}}">{{banner}}</div>
<div id="progress" style="display:none;padding:6px 18px;background:#101821;border-bottom:1px solid #23262d;font-size:.82rem">
  <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
    <span id="progress-text"></span>
    <button id="progress-cancel" style="display:none">取消</button>
  </div>
  <div style="height:6px;background:#1c222c;border-radius:99px;margin-top:4px;overflow:hidden">
    <div id="progress-bar" style="height:100%;width:0;background:#2f6fed;transition:width .2s"></div>
  </div>
</div>
<div id="toasts" style="position:fixed;right:16px;bottom:16px;display:flex;flex-direction:column;gap:8px;z-index:60"></div>
<main>
 <section>
  <div class="tabs">
    <button class="tab active" data-pane="console">控制台</button>
    <button class="tab" data-pane="files">文件</button>
    <button class="tab" data-pane="mods">模组</button>
    <button class="tab" data-pane="map">地图</button>
    <button class="tab" data-pane="backups">备份</button>
    <button class="tab" data-pane="settings">设置</button>
    <button class="tab" id="export">导出 zip</button>
  </div>
  <div class="pane active" id="pane-console">
    <pre id="console"></pre>
    <div id="cmd"><input id="text" placeholder="输入命令后回车（受白名单限制）" disabled>
    <button id="send" disabled>发送</button></div>
  </div>
  <div class="pane" id="pane-files">
    <div class="toolbar"><button id="up">上一级</button><span class="muted" id="cwd">/</span></div>
    <div id="filelist"></div>
  </div>
  <div class="pane" id="pane-mods">
    <div class="toolbar"><button id="mods-upload">上传模组</button><button id="mods-refresh">刷新</button>
      <label class="muted"><input type="checkbox" id="mods-lookup" checked> 在线查侧别</label>
      <span class="muted" id="mods-summary"></span></div>
    <div id="modlist"></div>
  </div>
  <div class="pane" id="pane-map">
    <div class="toolbar">
      <button id="map-open">打开地图</button>
      <button id="map-install">安装 BlueMap</button>
      <button id="map-share">生成共享链接</button>
      <button id="map-refresh">刷新</button>
      <span class="muted" id="map-status"></span>
    </div>
    <div class="toolbar" style="flex-wrap:wrap">
      <input id="mk-name" placeholder="标记名" style="width:110px">
      <input id="mk-x" placeholder="X" style="width:70px">
      <input id="mk-y" placeholder="Y" style="width:70px" value="64">
      <input id="mk-z" placeholder="Z" style="width:70px">
      <select id="mk-color"><option>red</option><option>blue</option><option>green</option><option>yellow</option><option>purple</option><option>orange</option><option>white</option></select>
      <input id="mk-note" placeholder="备注" style="width:140px">
      <button class="primary" id="mk-add">加标记</button>
    </div>
    <div id="players" class="muted" style="padding:0 10px"></div>
    <div class="toolbar" style="flex-wrap:wrap;border-top:1px solid #1c1f26">
      <span class="muted">RCON</span>
      <input id="rcon-port" placeholder="端口" style="width:80px" value="25575">
      <input id="rcon-pass" placeholder="密码" type="password" style="width:140px">
      <button id="rcon-save">保存并连接</button>
      <span class="muted" id="rcon-state"></span>
    </div>
    <div id="markerlist" style="flex:1;overflow:auto;padding:0 10px 10px"></div>
  </div>
  <div class="pane" id="pane-settings">
    <div class="toolbar"><span class="muted">这里的开关只影响这一个服务器，未改动的项沿用全局默认。</span></div>
    <div id="inssettings" style="flex:1;overflow:auto;padding:0 10px 10px"></div>
  </div>
  <div class="pane" id="pane-backups">
    <div class="toolbar"><button id="backup-new">创建备份</button><span class="muted" id="retention"></span></div>
    <div id="backuplist"></div>
  </div>
 </section>
</main>
<div id="insset" style="position:fixed;inset:8% 18%;background:#12151b;border:1px solid #2c313a;border-radius:10px;padding:14px;display:none;z-index:30;overflow:auto">
  <div class="row"><b>实例设置</b><span class="muted" id="insset-name"></span></div>
  <div class="row" style="margin-top:10px"><label class="muted" style="width:110px">Java 路径</label>
    <input id="is-java" style="flex:1"><button id="is-java-browse">浏览</button></div>
  <div class="row" style="margin-top:8px"><label class="muted" style="width:110px">最小内存 MB</label><input id="is-min" type="number" style="width:120px">
    <label class="muted" style="width:110px">最大内存 MB</label><input id="is-max" type="number" style="width:120px"></div>
  <div class="row" style="margin-top:8px"><label class="muted" style="width:110px">JVM 参数</label><input id="is-jvm" style="flex:1" placeholder="空格分隔，受白名单限制"></div>
  <div class="row" style="margin-top:8px"><label class="muted" style="width:110px">编码</label>
    <select id="is-enc"><option>utf-8</option><option>gb18030</option></select>
    <label class="muted"><input type="checkbox" id="is-nogui"> nogui</label></div>
  <div class="row" style="margin-top:8px"><label class="muted" style="width:110px">核心 / 参数文件</label>
    <input id="is-core" style="flex:1" placeholder="jar 文件名或 args 相对路径"></div>
  <div class="row" style="margin-top:14px;justify-content:flex-end;gap:8px">
    <span class="muted" id="is-msg"></span>
    <button id="is-cancel">取消</button><button class="primary" id="is-save">保存</button></div>
</div>
<div id="picker" style="position:fixed;inset:10% 25%;background:#12151b;border:1px solid #2c313a;border-radius:10px;padding:12px;display:none;z-index:40;flex-direction:column">
  <div class="row"><b id="picker-title">选择目录</b><span class="muted" id="picker-cwd"></span></div>
  <div class="row" style="margin:8px 0"><button id="picker-up">上一级</button><span class="muted" id="picker-hint"></span></div>
  <div id="picker-list" style="flex:1;overflow:auto;min-height:0"></div>
  <div class="row" style="justify-content:flex-end;gap:8px"><button id="picker-cancel">取消</button><button class="primary" id="picker-ok">选定当前目录</button></div>
</div>
<div id="editor">
  <div class="row"><b id="editor-title">编辑</b></div>
  <textarea id="editor-body" spellcheck="false"></textarea>
  <div class="row" style="display:flex;gap:8px;justify-content:flex-end">
    <button id="editor-cancel">取消</button><button class="primary" id="editor-save">保存</button>
  </div>
</div>
<script>
const state={current:"{{instance_id}}", ws:null, path:''};
const $=id=>document.getElementById(id);
const csrf=document.cookie.split('; ').find(c=>c.startsWith('hoshi_csrf='))?.split('=')[1]||'';
const H={'X-CSRF-Token':csrf};
function badge(s){return `<span class="state ${s}">${s}</span>`}
async function refresh(){
  const r=await fetch('/api/instances'); if(!r.ok) return;
  const data=await r.json(); const box=document.getElementById('list'); if(!box) return; box.innerHTML='';
  if(!data.instances.length){box.innerHTML='<p class="muted">还没有实例。用命令行 hoshi instances add 添加，或点右上角导入整合包。</p>';return}
  for(const it of data.instances){
    const div=document.createElement('div');
    div.className='inst'+(state.current===it.id?' active':'');
    div.innerHTML=`<div class="row"><b>${it.name}</b>${badge(it.state)}</div>
      <div class="muted" style="font-size:.78rem">${it.directory}</div>
      <div class="row" style="margin-top:6px">
        <button data-act="start">启动</button><button data-act="stop">停止</button><button data-act="kill">强杀</button><button data-act="config">设置</button>
      </div>`;
    div.onclick=e=>{if(e.target.dataset.act)return;select(it.id)};
    div.querySelectorAll('button').forEach(b=>b.onclick=async ev=>{
      ev.stopPropagation();
      if(b.dataset.act==='config'){ openInstanceSettings(it); return }
      const resp=await fetch(`/api/instances/${it.id}/${b.dataset.act}`,{method:'POST',headers:H});
      if(!resp.ok){const d=await resp.json().catch(()=>({}));alert(d.error||'操作失败')}
      setTimeout(refresh,300);
    });
    box.appendChild(div);
  }
}
async function select(id){
  state.current=id; state.path=''; await refresh();
  if(state.ws){state.ws.close();state.ws=null}
  const r=await fetch(`/api/instances/${id}/log?lines=300`); const data=await r.json();
  renderLines(data.lines||[]);
  const proto=location.protocol==='https:'?'wss:':'ws:';
  const ws=new WebSocket(`${proto}//${location.host}/ws/console/${id}`);
  state.ws=ws;
  ws.onmessage=ev=>{
    const m=JSON.parse(ev.data);
    if(m.type==='snapshot'){renderLines(m.lines)}
    else if(m.type==='log'){appendLine(m.line)}
    else if(m.type==='state'||m.type==='exit'){refresh()}
  };
  ws.onopen=()=>{$('text').disabled=false;$('send').disabled=false};
  ws.onclose=()=>{$('text').disabled=true;$('send').disabled=true};
  loadFiles(''); loadBackups(); loadMods(); loadMap(); loadInstanceSettings();
}
async function send(){
  const text=$('text').value.trim(); if(!text||!state.ws)return;
  state.ws.send(JSON.stringify({type:'command',text})); $('text').value='';
}
$('send').onclick=send;
$('text').addEventListener('keydown',e=>{if(e.key==='Enter')send()});
$('logout').onclick=async()=>{await fetch('/api/logout',{method:'POST',headers:H});location.href='/login'};

document.querySelectorAll('.tab[data-pane]').forEach(t=>t.onclick=()=>{
  document.querySelectorAll('.tab[data-pane]').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.pane').forEach(p=>p.classList.remove('active'));
  t.classList.add('active'); $('pane-'+t.dataset.pane).classList.add('active');
});

async function loadFiles(path){
  if(!state.current)return;
  const r=await fetch(`/api/instances/${state.current}/files?path=${encodeURIComponent(path)}`);
  if(!r.ok)return;
  const data=await r.json(); state.path=data.path||'';
  $('cwd').textContent='/'+(state.path||'');
  const box=$('filelist'); box.innerHTML='';
  if(data.path){const back=document.createElement('div');back.className='fitem';back.innerHTML='<span class="fname">../</span>';back.onclick=()=>loadFiles(data.parent==='.'?'':data.parent);box.appendChild(back)}
  for(const it of data.entries){
    const div=document.createElement('div'); div.className='fitem';
    div.innerHTML=`<span class="fname">${it.name}${it.type==='dir'?'/':''}</span>
      <span class="muted">${it.type==='dir'?'':fmtSize(it.size)} · ${it.mtime}</span>`;
    div.onclick=()=>it.type==='dir'?loadFiles((state.path?state.path+'/':'')+it.name):openEditor((state.path?state.path+'/':'')+it.name);
    box.appendChild(div);
  }
  if(!data.entries.length) box.innerHTML='<p class="muted">空目录</p>';
}
function fmtSize(n){if(n<1024)return n+' B';if(n<1048576)return (n/1024).toFixed(1)+' KB';return (n/1048576).toFixed(1)+' MB'}
$('up').onclick=()=>{const parts=(state.path||'').split('/').filter(Boolean);parts.pop();loadFiles(parts.join('/'))};

let editing=null;
async function openEditor(path){
  const r=await fetch(`/api/instances/${state.current}/file?path=${encodeURIComponent(path)}`);
  const d=await r.json();
  if(!r.ok){toast(d.error||'打不开','error');return}
  editing=path;
  $('editor-title').textContent=path;
  $('editor-body').value=d.content;
  $('editor').style.display='flex';
}
$('editor-cancel').onclick=()=>{$('editor').style.display='none';editing=null};
$('editor-save').onclick=async()=>{
  if(!editing)return;
  const r=await fetch(`/api/instances/${state.current}/file`,{method:'PUT',headers:{...H,'Content-Type':'application/json'},
    body:JSON.stringify({path:editing,content:$('editor-body').value})});
  const d=await r.json();
  if(!r.ok){toast(d.error||'保存失败','error');return}
  $('editor').style.display='none';
};

async function loadMap(){
  if(!state.current)return;
  const st=await (await fetch('/api/map/status')).json();
  $('map-status').textContent=st.enabled?('上游 '+st.upstream+' · '+(st.jar_installed?'jar 已装':'jar 未装')):'地图未启用（设置里打开 map.enabled）';
  const pl=await (await fetch(`/api/map/players?instance=${encodeURIComponent(st.instance||'')}`)).json();
  $('players').textContent=pl.connected?('在线：'+pl.players.map(p=>`${p.name}(${p.x},${p.z} ${p.dimension.replace('minecraft:','')})`).join('  ')):'玩家位置未连接（需要 RCON）';
  const mk=await (await fetch(`/api/map/markers?instance=${encodeURIComponent(st.instance||'')}`)).json();
  const box=$('markerlist'); box.innerHTML='';
  if(!mk.markers.length){box.innerHTML='<p class="muted">还没有标记</p>';return}
  for(const m of mk.markers){
    const div=document.createElement('div'); div.className='bitem';
    div.innerHTML=`<span class="fname">${m.name}</span>
      <span class="muted">(${m.x}, ${m.y}, ${m.z}) ${m.color} ${m.note||''}</span>
      <button>删除</button>`;
    div.querySelector('button').onclick=async()=>{
      await fetch(`/api/map/markers?id=${m.id}&instance=${encodeURIComponent(st.instance||'')}`,{method:'DELETE',headers:H});
      loadMap();
    };
    box.appendChild(div);
  }
}
$('map-refresh').onclick=loadMap;

$('map-install').onclick=async()=>{
  if(!state.current)return;
  const r=await fetch(`/api/instances/${state.current}/map/install`,{method:'POST',headers:H});
  const d=await r.json();
  if(!r.ok){ toast(d.error||'启动下载失败','error'); return }
  toast('开始获取 BlueMap，可取消','info');
  await pollJob(d.job.id, job=>{
    if(job.error){ toast(job.error,'error'); return }
    toast('BlueMap 已安装：'+(job.result&&job.result.jar||''),'ok');
    loadMap();
  });
};

async function loadRcon(){
  if(!state.current)return;
  const r=await fetch(`/api/instances/${state.current}/rcon`); if(!r.ok)return;
  const d=await r.json();
  $('rcon-port').value=d.port||25575;
  $('rcon-state').textContent=d.enabled?('已开启 · '+(d.poller&&d.poller.connected?'已连接':'未连接')):'未开启';
}
$('rcon-save').onclick=async()=>{
  if(!state.current)return;
  const body={enabled:true,port:Number($('rcon-port').value),password:$('rcon-pass').value};
  const r=await fetch(`/api/instances/${state.current}/rcon`,{method:'POST',headers:{...H,'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  if(!r.ok){ toast(d.error||'保存失败','error'); return }
  toast('已写入 server.properties，重启服务器后生效','ok');
  loadRcon();
};
loadRcon();
$('map-open').onclick=()=>{location.href='/map/'};
$('map-share').onclick=async()=>{
  const r=await fetch('/api/map/share',{method:'POST',headers:{...H,'Content-Type':'application/json'},body:'{}'});
  const d=await r.json();
  if(!r.ok){toast(d.error||'失败','error');return}
  const url=location.origin+d.url;
  prompt('只读链接（复制给朋友）：',url);
};
$('mk-add').onclick=async()=>{
  const body={name:$('mk-name').value.trim(),x:$('mk-x').value,y:$('mk-y').value||64,z:$('mk-z').value,
    color:$('mk-color').value,note:$('mk-note').value};
  if(!body.name||body.x===''||body.z===''){alert('名字与 X/Z 必填');return}
  const r=await fetch('/api/map/markers',{method:'POST',headers:{...H,'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  if(!r.ok){toast(d.error||'失败','error');return}
  if(d.bluemap&&!d.bluemap.applied){alert('已保存，但没写进地图：'+(d.bluemap.reason||''))}
  $('mk-name').value='';$('mk-x').value='';$('mk-z').value='';$('mk-note').value='';
  loadMap();
};

// ---------- 提示条 ----------
function toast(text, kind){
  const box=$('toasts');
  const div=document.createElement('div');
  const color=kind==='error'?'#ff8a8a':kind==='ok'?'#8ff0c0':'#dfe5ee';
  div.style.cssText=`background:#151b24;border:1px solid #2a3140;border-left:3px solid ${color};color:${color};`+
    'padding:8px 12px;border-radius:8px;font-size:.85rem;max-width:360px;box-shadow:0 6px 20px #0007';
  div.textContent=text;
  box.appendChild(div);
  setTimeout(()=>div.remove(), kind==='error'?6000:3500);
}

// ---------- 进度条与任务 ----------
let currentJob=null;
function showProgress(text, pct, cancellable){
  const box=$('progress'); box.style.display='block';
  $('progress-text').textContent=text;
  $('progress-bar').style.width=(pct>=0?pct:0)+'%';
  $('progress-cancel').style.display=cancellable?'':'none';
}
function hideProgress(){ $('progress').style.display='none'; $('progress-bar').style.width='0'; $('progress-cancel').style.display='none'; currentJob=null }

$('progress-cancel').onclick=async()=>{
  if(!currentJob)return;
  await fetch(`/api/jobs/${currentJob}/cancel`,{method:'POST',headers:H});
  toast('已请求取消，等当前批次结束','info');
};

async function pollJob(id, onDone, cancellable){
  currentJob=id;
  while(true){
    const r=await fetch('/api/jobs/'+id); if(!r.ok)return;
    const job=await r.json();
    showProgress(`${job.phase} ${job.total?`(${job.done}/${job.total})`:''}`, job.percent||0, cancellable!==false);
    if(job.finished){ hideProgress(); onDone(job); return }
    await new Promise(r=>setTimeout(r,400));
  }
}

// ---------- 目录选择 ----------
let pickerTarget=null, pickerPath='', pickerFiles=false;
function openPicker(title, start, onPick, files){
  pickerTarget=onPick; pickerFiles=!!files;
  $('picker-title').textContent=title;
  $('picker').style.display='flex';
  $('picker-ok').style.display=pickerFiles?'none':'';
  loadPicker(start||'');
}
async function loadPicker(path){
  const q=new URLSearchParams({path:path||''}); if(pickerFiles){q.set('files','1');q.set('suffix','.exe')}
  const r=await fetch('/api/fs/list?'+q); const d=await r.json();
  if(!r.ok){alert(d.error||'打不开目录');return}
  pickerPath=d.path||'';
  $('picker-cwd').textContent=pickerPath||'（选择盘符）';
  const box=$('picker-list'); box.innerHTML='';
  const up=document.createElement('div'); up.className='fitem'; up.innerHTML='<span class="fname">..</span>';
  up.onclick=()=>loadPicker(d.parent||''); box.appendChild(up);
  for(const e of d.entries){
    const div=document.createElement('div'); div.className='fitem';
    div.innerHTML=`<span class="fname">${e.name}${e.type==='dir'?'/':''}</span>`;
    div.onclick=()=>{ if(e.type==='file'){ if(pickerTarget)pickerTarget(e.path); closePicker() } else loadPicker(e.path) };
    box.appendChild(div);
  }
}
function closePicker(){ $('picker').style.display='none'; pickerTarget=null }
$('picker-up').onclick=async()=>{ const parts=pickerPath.split(/[\\/]/).filter(Boolean); parts.pop(); loadPicker(parts.join('/')) };
$('picker-cancel').onclick=closePicker;
$('picker-ok').onclick=()=>{ if(pickerTarget)pickerTarget(pickerPath); closePicker() };

// ---------- 实例设置 ----------
let editingInstance=null;
async function openInstanceSettings(it){
  editingInstance=it;
  const r=await fetch('/api/instances'); const d=await r.json();
  const full=d.instances.find(x=>x.id===it.id); if(!full)return;
  const cfg=await (await fetch('/api/instances/'+it.id+'/settings')).json();
  $('insset-name').textContent=cfg.name;
  $('is-java').value=cfg.java||''; $('is-min').value=cfg.min_memory_mb; $('is-max').value=cfg.max_memory_mb;
  $('is-jvm').value=(cfg.jvm_args||[]).join(' '); $('is-enc').value=cfg.encoding||'utf-8';
  $('is-nogui').checked=!!cfg.nogui; $('is-core').value=cfg.launch_mode==='jar'?cfg.jar:cfg.args_file;
  $('is-msg').textContent=''; $('insset').style.display='block';
}
$('is-java-browse').onclick=()=>openPicker('选择 java.exe', $('is-java').value||'', p=>{$('is-java').value=p}, true);
$('is-cancel').onclick=()=>{$('insset').style.display='none'};
$('is-save').onclick=async()=>{
  if(!editingInstance)return;
  const body={java:$('is-java').value.trim(),min_memory_mb:Number($('is-min').value),max_memory_mb:Number($('is-max').value),
    jvm_args:$('is-jvm').value,encoding:$('is-enc').value,nogui:$('is-nogui').checked};
  const core=$('is-core').value.trim();
  if(core){ body[/^.*\\.jar$/i.test(core)?'jar':'args_file']=core }
  const r=await fetch('/api/instances/'+editingInstance.id,{method:'PATCH',headers:{...H,'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  if(!r.ok){ $('is-msg').textContent='失败：'+(d.error||''); return }
  $('insset').style.display='none'; refresh();
};

// ---------- 控制台上色 ----------
const LEVEL_RE=/\/(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\]/;
const JOIN_RE=/\]: (\S{1,16}) joined the game/;
const LEAVE_RE=/\]: (\S{1,16}) left the game/;
function classify(line){
  if(line.startsWith('> '))return 'lv-panel';
  if(JOIN_RE.test(line))return 'lv-join';
  if(LEAVE_RE.test(line))return 'lv-leave';
  const m=LEVEL_RE.exec(line);
  if(m){const lv=m[1];return lv==='ERROR'||lv==='FATAL'?'lv-error':lv==='WARN'||lv==='WARNING'?'lv-warn':lv==='DEBUG'||lv==='TRACE'?'lv-debug':'lv-info'}
  const low=line.toLowerCase();
  if(low.includes('exception')||low.includes('error'))return 'lv-error';
  if(low.includes('warn'))return 'lv-warn';
  return 'lv-info';
}
function makeLine(text){
  const div=document.createElement('div'); div.className='line '+classify(text); div.textContent=text; return div;
}
function renderLines(lines){
  const box=$('console'); box.innerHTML='';
  const frag=document.createDocumentFragment();
  for(const line of lines) frag.appendChild(makeLine(line));
  box.appendChild(frag); box.scrollTop=box.scrollHeight;
}
function appendLine(line){
  const box=$('console');
  box.appendChild(makeLine(line));
  while(box.childElementCount>2000) box.removeChild(box.firstChild);
  box.scrollTop=box.scrollHeight;
}

// ---------- 实例级设置 ----------
async function loadInstanceSettings(){
  if(!state.current)return;
  const r=await fetch(`/api/instances/${state.current}/instance-settings`);
  if(!r.ok)return;
  const d=await r.json();
  const box=$('inssettings'); box.innerHTML='';
  for(const item of d.items){
    const row=document.createElement('div'); row.className='bitem';
    const source=item.source==='instance'?'本实例':item.source==='global'?'全局':'默认';
    row.innerHTML=`<span class="fname">${item.label}</span>
      <span class="muted">${item.key} · ${source}</span>`;
    const ctrl=document.createElement('span');
    let input;
    if(item.kind==='bool'){
      input=document.createElement('input'); input.type='checkbox'; input.checked=!!item.value;
    } else {
      input=document.createElement('input'); input.style.width='110px';
      input.value=Array.isArray(item.value)?item.value.join(','):(item.value??'');
    }
    input.dataset.key=item.key;
    const save=document.createElement('button'); save.textContent='保存';
    save.onclick=async()=>{
      const raw=item.kind==='bool'?input.checked:input.value;
      const resp=await fetch(`/api/instances/${state.current}/instance-settings`,{method:'PATCH',headers:{...H,'Content-Type':'application/json'},body:JSON.stringify({values:{[item.key]:raw}})});
      const dd=await resp.json();
      if(!resp.ok){alert(dd.error||'保存失败');return}
      loadInstanceSettings();
    };
    ctrl.appendChild(input); ctrl.appendChild(save);
    if(item.source==='instance'){
      const reset=document.createElement('button'); reset.textContent='恢复默认';
      reset.onclick=async()=>{
        await fetch(`/api/instances/${state.current}/instance-settings/${item.key}/reset`,{method:'POST',headers:H});
        loadInstanceSettings();
      };
      ctrl.appendChild(reset);
    }
    row.appendChild(ctrl); box.appendChild(row);
  }
}

async function loadBackups(){
  if(!state.current)return;
  const r=await fetch(`/api/instances/${state.current}/backups`);
  const d=await r.json();
  $('retention').textContent=`最多保留 ${d.retention} 份`;
  const box=$('backuplist'); box.innerHTML='';
  if(!d.backups.length){box.innerHTML='<p class="muted">还没有备份</p>';return}
  for(const b of d.backups){
    const div=document.createElement('div'); div.className='bitem';
    div.innerHTML=`<span class="fname">${b.name}</span><span class="muted">${fmtSize(b.size)} · ${b.created}</span>
      <span><button data-op="restore">恢复</button> <button data-op="delete">删除</button></span>`;
    div.querySelectorAll('button').forEach(btn=>btn.onclick=async()=>{
      if(btn.dataset.op==='delete'){
        if(!confirm('删除 '+b.name+' ?'))return;
        await fetch(`/api/instances/${state.current}/backups/${b.name}`,{method:'DELETE',headers:H});
      } else {
        if(!confirm('恢复会覆盖当前世界与配置，先确保服务器已停止。继续？'))return;
        const resp=await fetch(`/api/instances/${state.current}/backups/${b.name}/restore`,{method:'POST',headers:H});
        const dd=await resp.json(); if(!resp.ok)alert(dd.error||'失败');
      }
      loadBackups();
    });
    box.appendChild(div);
  }
}
async function loadMods(){
  if(!state.current)return;
  $('mods-summary').textContent='加载中…';
  const lookup=$('mods-lookup').checked?'1':'0';
  const r=await fetch(`/api/instances/${state.current}/mods?lookup=${lookup}`);
  const d=await r.json();
  $('mods-summary').textContent=`共 ${d.summary.total} · 启用 ${d.summary.enabled} · 客户端专用 ${d.summary.client_only} · 未知 ${d.summary.unknown}`;
  const box=$('modlist'); box.innerHTML='';
  if(!d.mods.length){box.innerHTML='<p class="muted">mods 目录为空</p>';return}
  for(const m of d.mods){
    const div=document.createElement('div'); div.className='fitem';
    const tag=m.side==='client'?'<span class="state crashed">客户端</span>':m.side==='server'?'<span class="state">服务端</span>':m.side==='both'?'<span class="state running">通用</span>':'<span class="state">未知</span>';
    div.innerHTML=`<span class="fname">${m.file}</span>
      <span class="muted">${tag} ${m.advice||''} · ${fmtSize(m.size)}</span>
      <button>${m.enabled?'停用':'启用'}</button>`;
    div.querySelector('button').onclick=async()=>{
      const r2=await fetch(`/api/instances/${state.current}/mods/toggle`,{method:'POST',headers:{...H,'Content-Type':'application/json'},
        body:JSON.stringify({file:m.file,enabled:!m.enabled})});
      const d2=await r2.json(); if(!r2.ok)toast(d2.error||'失败','error'); loadMods();
    };
    box.appendChild(div);
  }
}
$('mods-upload').onclick=()=>{
  if(!state.current)return;
  const input=document.createElement('input'); input.type='file'; input.accept='.jar'; input.multiple=true;
  input.onchange=async()=>{
    const files=Array.from(input.files||[]); if(!files.length)return;
    const form=new FormData(); files.forEach(f=>form.append('file',f,f.name));
    showProgress('上传模组 0%',0,false);
    const xhr=new XMLHttpRequest(); xhr.open('POST',`/api/instances/${state.current}/mods/upload`);
    xhr.setRequestHeader('X-CSRF-Token',csrf);
    xhr.upload.onprogress=e=>{ if(e.lengthComputable) showProgress(`上传模组 ${Math.round(e.loaded*100/e.total)}%`, e.loaded*100/e.total, false) };
    xhr.onload=()=>{
      hideProgress();
      let d={}; try{ d=JSON.parse(xhr.responseText) }catch(_){}
      if(xhr.status!==200){ toast(d.error||('上传失败 '+xhr.status),'error'); return }
      toast('已上传 '+d.saved.length+' 个模组'+(d.skipped&&d.skipped.length?('，跳过 '+d.skipped.length+' 个'):''),'ok');
      loadMods();
    };
    xhr.onerror=()=>{ hideProgress(); toast('上传失败','error') };
    xhr.send(form);
  };
  input.click();
};
$('mods-refresh').onclick=loadMods;
$('mods-lookup').onchange=loadMods;

$('backup-new').onclick=async()=>{
  if(!state.current)return;
  const r=await fetch(`/api/instances/${state.current}/backup`,{method:'POST',headers:{...H,'Content-Type':'application/json'},body:'{}'});
  const d=await r.json();
  if(!r.ok){ toast(d.error||'备份失败','error'); return }
  await pollJob(d.job.id, job=>{
    if(job.error){ toast(job.error,'error'); return }
    toast('备份完成','ok'); loadBackups();
  });
};
$('export').onclick=async()=>{
  if(!state.current)return;
  const r=await fetch(`/api/instances/${state.current}/export?include=world,config,mods`,{method:'POST',headers:H});
  const d=await r.json();
  if(!r.ok){ toast(d.error||'导出失败','error'); return }
  toast('开始打包，可随时取消','info');
  await pollJob(d.job.id, job=>{
    if(job.error){ toast(job.error,'error'); return }
    toast('打包完成，开始下载','ok');
    location.href=`/api/jobs/${job.id}/download`;
  });
};

$('import-pack').onclick=async(e)=>{
  e.preventDefault();
  const input=document.createElement('input'); input.type='file'; input.accept='.zip';
  input.onchange=async()=>{
    const file=input.files[0]; if(!file)return;
    const name=prompt('新实例名（目录名）', file.name.replace(/\\.zip$/i,''));
    if(!name)return;
    const form=new FormData(); form.append('name',name); form.append('file',file);
    const r=await fetch('/api/packs/import',{method:'POST',headers:H,body:form});
    const d=await r.json();
    if(!r.ok){alert(d.error||'导入失败');return}
    alert('已导入：'+d.instance.name+ (d.skipped&&d.skipped.length?('\\n跳过 '+d.skipped.length+' 项'):''));
    refresh();
  };
  input.click();
};

if(state.current){ select(state.current) }
setInterval(refresh,4000);

function unifyButtons(){
  document.querySelectorAll('button').forEach(b=>{
    if(!b.classList.contains('btn')){b.classList.add('btn','btn-sm')}
  });
}
new MutationObserver(unifyButtons).observe(document.body,{childList:true,subtree:true});
unifyButtons();
</script>
</body></html>
"""

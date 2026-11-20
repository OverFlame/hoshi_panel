"""首页模板：实例列表、控制台、文件、备份。

模板用 {{token}} 占位，避免 JS 模板字符串里的 $ 被误解析。
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
 .banner{padding:6px 18px;font-size:.82rem;background:#2a2013;color:#ffd28a;border-bottom:1px solid #3d2f16}
 .banner.local{background:#13221a;color:#8ff0c0;border-color:#1c3a2a}
 main{display:grid;grid-template-columns:300px 1fr;height:calc(100vh - 96px)}
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
 section{display:flex;flex-direction:column;min-width:0}
 .tabs{display:flex;gap:6px;padding:8px 10px;border-bottom:1px solid #23262d}
 .tab{padding:4px 10px;border-radius:6px;border:1px solid #333;background:#1b1f27;color:#e6e6e6;cursor:pointer;font-size:.85rem}
 .tab.active{border-color:#2f6fed;background:#182338}
 .pane{flex:1;min-height:0;display:none;flex-direction:column}
 .pane.active{display:flex}
 #console{flex:1;margin:0;padding:12px;overflow:auto;white-space:pre-wrap;word-break:break-all;font:12px/1.5 ui-monospace,monospace;background:#0b0d11}
 #cmd{display:flex;gap:8px;padding:10px;border-top:1px solid #23262d}
 #cmd input{flex:1;padding:8px;border-radius:6px;border:1px solid #333;background:#141821;color:#e6e6e6}
 .toolbar{display:flex;gap:8px;align-items:center;padding:8px 10px;border-bottom:1px solid #23262d;font-size:.85rem}
 .toolbar input{padding:6px 8px;border-radius:6px;border:1px solid #333;background:#141821;color:#e6e6e6}
 #filelist,#backuplist{flex:1;overflow:auto;padding:0 10px 10px}
 .fitem,.bitem{display:flex;justify-content:space-between;gap:8px;padding:6px 4px;border-bottom:1px solid #1c1f26;font-size:.85rem}
 .fitem{cursor:pointer}
 .fitem:hover{background:#141821}
 .fname{font-family:ui-monospace,monospace}
 .muted{opacity:.6}
 a{color:#8ab4ff}
 #editor{position:fixed;inset:5% 8%;background:#12151b;border:1px solid #2c313a;border-radius:10px;display:none;flex-direction:column;padding:10px;z-index:20}
 #editor textarea{flex:1;width:100%;background:#0b0d11;color:#e6e6e6;border:1px solid #262b33;border-radius:8px;padding:8px;font:12px/1.5 ui-monospace,monospace}
 #editor .row{padding-top:8px}
</style></head>
<body>
<header><h1>{{app}} <span class="muted">{{version}}</span></h1>
<div style="display:flex;gap:10px;align-items:center">
  <a href="#" id="import-pack">导入整合包</a>
  <a href="/settings">设置</a><a href="/audit">审计</a>
  <span class="muted">{{user}}</span>
  <button id="logout">退出</button>
</div></header>
<div class="banner {{banner_class}}">{{banner}}</div>
<main>
 <aside id="list"><p class="muted">加载中…</p></aside>
 <section>
  <div class="tabs">
    <button class="tab active" data-pane="console">控制台</button>
    <button class="tab" data-pane="files">文件</button>
    <button class="tab" data-pane="mods">模组</button>
    <button class="tab" data-pane="map">地图</button>
    <button class="tab" data-pane="backups">备份</button>
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
    <div class="toolbar"><button id="mods-refresh">刷新</button>
      <label class="muted"><input type="checkbox" id="mods-lookup" checked> 在线查侧别</label>
      <span class="muted" id="mods-summary"></span></div>
    <div id="modlist"></div>
  </div>
  <div class="pane" id="pane-map">
    <div class="toolbar">
      <button id="map-open">打开地图</button>
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
    <div id="markerlist" style="flex:1;overflow:auto;padding:0 10px 10px"></div>
  </div>
  <div class="pane" id="pane-backups">
    <div class="toolbar"><button id="backup-new">创建备份</button><span class="muted" id="retention"></span></div>
    <div id="backuplist"></div>
  </div>
 </section>
</main>
<div id="editor">
  <div class="row"><b id="editor-title">编辑</b></div>
  <textarea id="editor-body" spellcheck="false"></textarea>
  <div class="row" style="display:flex;gap:8px;justify-content:flex-end">
    <button id="editor-cancel">取消</button><button class="primary" id="editor-save">保存</button>
  </div>
</div>
<script>
const state={current:null, ws:null, path:''};
const $=id=>document.getElementById(id);
const csrf=document.cookie.split('; ').find(c=>c.startsWith('hoshi_csrf='))?.split('=')[1]||'';
const H={'X-CSRF-Token':csrf};
function badge(s){return `<span class="state ${s}">${s}</span>`}
async function refresh(){
  const r=await fetch('/api/instances'); if(!r.ok) return;
  const data=await r.json(); const box=$('list'); box.innerHTML='';
  if(!data.instances.length){box.innerHTML='<p class="muted">还没有实例。用命令行 hoshi instances add 添加，或点右上角导入整合包。</p>';return}
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
  $('console').textContent=(data.lines||[]).join('\\n')+'\\n';
  const proto=location.protocol==='https:'?'wss:':'ws:';
  const ws=new WebSocket(`${proto}//${location.host}/ws/console/${id}`);
  state.ws=ws;
  ws.onmessage=ev=>{
    const m=JSON.parse(ev.data);
    if(m.type==='snapshot'){$('console').textContent=m.lines.join('\\n')+'\\n'}
    else if(m.type==='log'){$('console').textContent+=m.line+'\\n';$('console').scrollTop=$('console').scrollHeight}
    else if(m.type==='state'||m.type==='exit'){refresh()}
  };
  ws.onopen=()=>{$('text').disabled=false;$('send').disabled=false};
  ws.onclose=()=>{$('text').disabled=true;$('send').disabled=true};
  loadFiles(''); loadBackups(); loadMods(); loadMap();
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
  if(!r.ok){alert(d.error||'打不开');return}
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
  if(!r.ok){alert(d.error||'保存失败');return}
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
$('map-open').onclick=()=>{location.href='/map/'};
$('map-share').onclick=async()=>{
  const r=await fetch('/api/map/share',{method:'POST',headers:{...H,'Content-Type':'application/json'},body:'{}'});
  const d=await r.json();
  if(!r.ok){alert(d.error||'失败');return}
  const url=location.origin+d.url;
  prompt('只读链接（复制给朋友）：',url);
};
$('mk-add').onclick=async()=>{
  const body={name:$('mk-name').value.trim(),x:$('mk-x').value,y:$('mk-y').value||64,z:$('mk-z').value,
    color:$('mk-color').value,note:$('mk-note').value};
  if(!body.name||body.x===''||body.z===''){alert('名字与 X/Z 必填');return}
  const r=await fetch('/api/map/markers',{method:'POST',headers:{...H,'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  if(!r.ok){alert(d.error||'失败');return}
  if(d.bluemap&&!d.bluemap.applied){alert('已保存，但没写进地图：'+(d.bluemap.reason||''))}
  $('mk-name').value='';$('mk-x').value='';$('mk-z').value='';$('mk-note').value='';
  loadMap();
};

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
      const d2=await r2.json(); if(!r2.ok)alert(d2.error||'失败'); loadMods();
    };
    box.appendChild(div);
  }
}
$('mods-refresh').onclick=loadMods;
$('mods-lookup').onchange=loadMods;

$('backup-new').onclick=async()=>{
  if(!state.current)return;
  const r=await fetch(`/api/instances/${state.current}/backup`,{method:'POST',headers:{...H,'Content-Type':'application/json'},body:'{}'});
  const d=await r.json(); if(!r.ok)alert(d.error||'备份失败'); loadBackups();
};
$('export').onclick=()=>{
  if(!state.current)return;
  location.href=`/api/instances/${state.current}/export?include=world,config,mods`;
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

refresh(); setInterval(refresh,4000);
</script>
</body></html>
"""

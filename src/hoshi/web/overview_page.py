"""概览页：整体状态与实例卡片，进来先看全局。"""

OVERVIEW_HTML = r"""<!doctype html>
<html lang="zh-CN" data-bs-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{app}}</title>
<style>
 :root{color-scheme:dark}
 html,body{height:100%}
 body{margin:0;display:flex;flex-direction:column;min-height:100vh;background:#0d1015;color:#e6e8eb;
      font:14px/1.6 "JetBrainsMono Nerd Font","JetBrains Mono Web","JetBrains Mono",system-ui,-apple-system,"Segoe UI",sans-serif}
 header{display:flex;justify-content:space-between;align-items:center;padding:14px 22px;border-bottom:1px solid #1e232c}
 header h1{font-size:1rem;margin:0;font-weight:600;letter-spacing:.02em}
 header a{color:#9db4d0;text-decoration:none;margin-left:14px;font-size:.9rem}
 header a:hover{color:#8ab4ff}
 main{padding:20px 22px 40px;max-width:1180px;margin:0 auto;width:100%;box-sizing:border-box}
 .cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
 .card{background:#131820;border:1px solid #1f2530;border-radius:10px;padding:14px 16px;min-width:0}
 .card .k{font-size:.78rem;color:#8a93a3}
 .card .v{font-size:1.5rem;font-weight:600;margin-top:2px}
 .card .s{font-size:.76rem;color:#7d8695;margin-top:2px}
 .bar{height:5px;border-radius:99px;background:#1b2230;margin-top:10px;overflow:hidden}
 .bar>i{display:block;height:100%;background:#2f6fed;width:0}
 .cols{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:16px;margin-top:18px}
 h2{font-size:.82rem;color:#8a93a3;font-weight:600;margin:0 0 10px;letter-spacing:.04em;text-transform:uppercase}
 .inst{background:#131820;border:1px solid #1f2530;border-radius:10px;padding:14px 16px;margin-bottom:10px}
 .inst .top{display:flex;justify-content:space-between;align-items:center;gap:10px}
 .inst .name{font-weight:600}
 .state{font-size:.72rem;padding:2px 8px;border-radius:99px;background:#242a35;color:#b9c2d0}
 .state.running{background:#123a28;color:#8ff0c0}
 .state.crashed{background:#3d1616;color:#ffb4b4}
 .meta{display:flex;gap:14px;flex-wrap:wrap;color:#7d8695;font-size:.78rem;margin-top:6px}
 button{padding:5px 11px;border-radius:7px;border:1px solid #2a3140;background:#18202b;color:#dfe5ee;cursor:pointer;font-size:.82rem}
 button:hover{border-color:#2f6fed}
 button.primary{background:#2f6fed;border-color:#2f6fed}
 .events{background:#131820;border:1px solid #1f2530;border-radius:10px;padding:12px 14px;max-height:420px;overflow:auto}
 .ev{font-size:.8rem;color:#a9b3c2;padding:5px 0;border-bottom:1px solid #1a2029}
 .ev b{color:#dfe5ee;font-weight:500}
 .muted{color:#7d8695}
 .empty{color:#7d8695;font-size:.85rem;padding:18px 0}
 @media (max-width:900px){ .cards{grid-template-columns:repeat(2,minmax(0,1fr))} .cols{grid-template-columns:1fr} }
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
<header>
  <h1>{{app}}</h1>
  <div style="display:flex;align-items:center;gap:14px"><button id="import-pack" class="btn btn-sm btn-primary">导入整合包</button><a href="/settings">设置</a><a href="/audit">审计</a><span class="muted">{{user}}</span>
    <button id="logout" style="margin-left:12px">退出</button></div>
</header>
<div id="progress" style="display:none;padding:6px 22px;background:#101821;border-bottom:1px solid #1e232c;font-size:.8rem">
  <div style="display:flex;justify-content:space-between;gap:10px"><span id="progress-text"></span>
  <button id="progress-cancel" class="btn btn-sm" style="display:none">取消</button></div>
  <div style="height:5px;background:#1b2230;border-radius:99px;margin-top:4px;overflow:hidden">
    <div id="progress-bar" style="height:100%;width:0;background:#2f6fed;transition:width .2s"></div>
  </div>
</div>
<div id="toasts" style="position:fixed;right:16px;bottom:16px;display:flex;flex-direction:column;gap:8px;z-index:60"></div>
<main>
  <div class="cards">
    <div class="card"><div class="k">服务器</div><div class="v" id="m-inst">-</div><div class="s" id="m-inst-s">运行 0</div></div>
    <div class="card"><div class="k">在线玩家</div><div class="v" id="m-players">-</div><div class="s">所有服务器合计</div></div>
    <div class="card"><div class="k">内存</div><div class="v" id="m-mem">-</div><div class="s" id="m-mem-s">面板 -</div>
      <div class="bar"><i id="m-mem-bar"></i></div></div>
    <div class="card"><div class="k">CPU</div><div class="v" id="m-cpu">-</div><div class="s" id="m-cpu-s">- 核</div>
      <div class="bar"><i id="m-cpu-bar"></i></div></div>
  </div>
  <div class="cols">
    <div>
      <h2>服务器</h2>
      <div id="instances"><div class="empty">读取中…</div></div>
    </div>
    <div>
      <h2>最近事件</h2>
      <div class="events" id="events"><div class="empty">读取中…</div></div>
    </div>
  </div>
</main>
<script>
const $=id=>document.getElementById(id);
const csrf=document.cookie.split('; ').find(c=>c.startsWith('hoshi_csrf='))?.split('=')[1]||'';
const H={'X-CSRF-Token':csrf};
function pct(a,b){return b?Math.min(100,Math.round(a*100/b)):0}
async function loadMetrics(){
  const r=await fetch('/api/metrics'); if(!r.ok)return;
  const d=await r.json();
  const host=d.host||{};
  $('m-mem').textContent=(host.used_mb/1024).toFixed(1)+' / '+(host.total_mb/1024).toFixed(1)+' GB';
  $('m-mem-bar').style.width=pct(host.used_mb,host.total_mb)+'%';
  $('m-mem-s').textContent='面板 '+(d.panel.rss_mb||0).toFixed(0)+' MB · '+(host.percent||0)+'%';
  $('m-cpu').textContent=(host.cpu_percent||0)+'%';
  $('m-cpu-bar').style.width=Math.min(100,host.cpu_percent||0)+'%';
  $('m-cpu-s').textContent=(host.cores||0)+' 核 · 面板 '+(d.panel.cpu_percent||0)+'%';
  return d;
}
async function loadInstances(){
  const r=await fetch('/api/instances'); if(!r.ok)return;
  const d=await r.json();
  const running=d.instances.filter(i=>i.state==='running');
  $('m-inst').textContent=d.instances.length;
  $('m-inst-s').textContent='运行 '+running.length;
  const box=$('instances'); box.innerHTML='';
  if(!d.instances.length){box.innerHTML='<div class="empty">还没有服务器。用 hoshi instances add 添加，或在设置里导入。</div>';return}
  for(const it of d.instances){
    const div=document.createElement('div'); div.className='inst';
    div.innerHTML=`<div class="top"><div class="name">${it.name}</div>
      <span class="state ${it.state}">${it.state}</span></div>
      <div class="meta"><span class="muted">${it.directory}</span></div>
      <div class="top" style="margin-top:10px">
        <div class="meta" id="meta-${it.id}"></div>
        <div><button data-act="start">启动</button><button data-act="stop">停止</button>
        <button class="primary" data-act="open">进入</button></div>
      </div>`;
    div.querySelectorAll('button').forEach(b=>b.onclick=async ev=>{
      ev.stopPropagation();
      if(b.dataset.act==='open'){location.href='/i/'+it.id;return}
      const resp=await fetch(`/api/instances/${it.id}/${b.dataset.act}`,{method:'POST',headers:H});
      if(!resp.ok){const dd=await resp.json().catch(()=>({}));alert(dd.error||'操作失败')}
      setTimeout(refreshAll,400);
    });
    box.appendChild(div);
  }
  return d;
}
async function fillMeta(instances, metrics){
  const bag=(metrics&&metrics.instances)||{};
  for(const it of instances){
    const el=document.getElementById('meta-'+it.id); if(!el)continue;
    const m=bag[it.id]||{};
    el.innerHTML=`<span>玩家 ${it.players??'-'}</span><span>内存 ${m.rss_mb?m.rss_mb.toFixed(0)+' MB':'-'}</span><span>CPU ${m.cpu_percent?m.cpu_percent+'%':'-'}</span>`;
  }
}
async function loadEvents(){
  const r=await fetch('/api/audit?limit=20'); if(!r.ok)return;
  const d=await r.json();
  const box=$('events'); box.innerHTML='';
  if(!d.items.length){box.innerHTML='<div class="empty">暂无记录</div>';return}
  for(const e of d.items){
    const div=document.createElement('div'); div.className='ev';
    div.innerHTML=`<b>${e.action}</b> ${e.target||''} <span class="muted">${e.ts.slice(5,16)}</span>`;
    box.appendChild(div);
  }
}
async function refreshAll(){
  const [inst, met] = await Promise.all([loadInstances(), loadMetrics()]);
  if(inst&&met) await fillMeta(inst.instances, met);
  loadEvents();
}
function toast(text, kind){
  const box=$('toasts'); const div=document.createElement('div');
  const color=kind==='error'?'#ff8a8a':kind==='ok'?'#8ff0c0':'#dfe5ee';
  div.style.cssText=`background:#151b24;border:1px solid #2a3140;border-left:3px solid ${color};color:${color};padding:8px 12px;border-radius:8px;font-size:.85rem;max-width:360px;box-shadow:0 6px 20px #0007`;
  div.textContent=text; box.appendChild(div);
  setTimeout(()=>div.remove(), kind==='error'?6000:3500);
}
let currentJob=null;
function showProgress(text, pct, cancellable){
  $('progress').style.display='block'; $('progress-text').textContent=text;
  $('progress-bar').style.width=(pct>=0?pct:0)+'%';
  $('progress-cancel').style.display=cancellable?'':'none';
}
function hideProgress(){ $('progress').style.display='none'; $('progress-bar').style.width='0'; currentJob=null }
$('progress-cancel').onclick=async()=>{ if(currentJob){ await fetch('/api/jobs/'+currentJob+'/cancel',{method:'POST',headers:H}); toast('已请求取消','info') } };
async function pollJob(id, onDone){
  currentJob=id;
  while(true){
    const r=await fetch('/api/jobs/'+id); if(!r.ok)return;
    const job=await r.json();
    showProgress(`${job.phase} ${job.total?`(${job.done}/${job.total})`:''}`, job.percent||0, true);
    if(job.finished){ hideProgress(); onDone(job); return }
    await new Promise(r=>setTimeout(r,400));
  }
}
$('import-pack').onclick=()=>{
  const input=document.createElement('input'); input.type='file'; input.accept='.zip';
  input.onchange=async()=>{
    const file=input.files[0]; if(!file)return;
    const name=prompt('新实例名（目录名）', file.name.replace(/\.zip$/i,''));
    if(!name)return;
    const form=new FormData(); form.append('name',name); form.append('file',file);
    showProgress('上传中 0%',0,false);
    const xhr=new XMLHttpRequest(); xhr.open('POST','/api/packs/import');
    xhr.setRequestHeader('X-CSRF-Token',csrf);
    xhr.upload.onprogress=e=>{ if(e.lengthComputable) showProgress(`上传中 ${Math.round(e.loaded*100/e.total)}%`, e.loaded*100/e.total, false) };
    xhr.onload=async()=>{
      let d={}; try{ d=JSON.parse(xhr.responseText) }catch(_){}
      if(xhr.status!==200){ hideProgress(); toast(d.error||('导入失败 '+xhr.status),'error'); return }
      if(d.job&&d.job.id) await pollJob(d.job.id, ()=>{});
      else hideProgress();
      toast('已导入：'+d.instance.name+(d.skipped&&d.skipped.length?('，跳过 '+d.skipped.length+' 项'):''),'ok');
      refreshAll();
    };
    xhr.onerror=()=>{ hideProgress(); toast('上传失败','error') };
    xhr.send(form);
  };
  input.click();
};
$('logout').onclick=async()=>{await fetch('/api/logout',{method:'POST',headers:H});location.href='/login'};
refreshAll(); setInterval(refreshAll,5000);

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

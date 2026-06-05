import os
import json
import threading
from concurrent import futures
import time
import subprocess
import shutil
import hashlib

import grpc
import redis
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse
import uvicorn

try:
    from . import orchestrator_pb2
    from . import orchestrator_pb2_grpc
except (ImportError, ValueError):
    import orchestrator_pb2
    import orchestrator_pb2_grpc

# ==========================================
# CONFIGURATION
# ==========================================
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
GRPC_PORT = "[::]:50051"
REST_PORT = 8000
PLUGINS_DIR = os.getenv("XBIN_PLUGINS_DIR", "plugins")
UPLOAD_DIR = "uploads"

BACKEND_WEIGHTS = {
    "exact_hasher": 1.0,
    "agentic_arbiter": 1.0,
    "flirt_matcher": 1.0,
    "semantic_llm": 0.85,
    "structural_cfg": 0.70
}
MARGIN_THRESHOLD = 0.05

r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)

def sys_log(msg):
    timestamp = time.strftime("%H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    print(entry)
    r.lpush("xbin:syslogs", entry)
    r.ltrim("xbin:syslogs", 0, 100)

def set_plugin_state(name, status, error=None):
    state = {"status": status, "last_update": time.time()}
    if error: state["error"] = error
    r.set(f"xbin:plugin_state:{name}", json.dumps(state))

def ensure_redis():
    try:
        r.ping()
    except redis.ConnectionError:
        if os.path.exists("/.dockerenv") or REDIS_HOST != "localhost":
            exit(1)
        try:
            check = subprocess.run(["docker", "ps", "-a", "--filter", "name=xbin-redis", "--format", "{{.Names}}"], capture_output=True, text=True)
            if "xbin-redis" in check.stdout:
                sys_log("Restarting Redis...")
                subprocess.run(["docker", "start", "xbin-redis"], check=True, stdout=subprocess.DEVNULL)
            else:
                sys_log("Booting Redis...")
                subprocess.run(["docker", "run", "-d", "--name", "xbin-redis", "-p", "6379:6379", "redis:alpine"], check=True, stdout=subprocess.DEVNULL)
            for _ in range(10):
                try:
                    if r.ping(): return
                except: time.sleep(1)
            exit(1)
        except: exit(1)

def cleanup_stale_plugins():
    try:
        sys_log("Cleanup stale containers...")
        subprocess.run("docker rm -f $(docker ps -aq --filter name=xbin-worker-)", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        r.delete("xbin:active_workers")
        r.delete("xbin:worker_health")
        r.delete("xbin:syslogs")
    except: pass

# ==========================================
# MULTI-ANALYSIS BLACKBOARD API
# ==========================================
app = FastAPI(title="xbin Multi-Analysis Orchestrator", version="1.6.0")

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

@app.get("/api/v1/system/logs")
def get_system_logs():
    logs = r.lrange("xbin:syslogs", 0, -1)
    return {"logs": "\\n".join(reversed(logs))}

@app.get("/api/v1/health")
def get_health():
    health_data = r.hgetall("xbin:worker_health")
    workers = []
    now = time.time()
    for worker_id, val in health_data.items():
        data = json.loads(val)
        workers.append({
            "worker_id": worker_id, 
            "status": "HEALTHY" if (now - data["last_heartbeat"]) < 10 else "DEAD",
            "last_beat": data["last_heartbeat"]
        })
    return {"orchestrator": "HEALTHY", "worker_fleet": workers}

@app.post("/api/v1/upload")
async def upload_binary(file: UploadFile = File(...), requested_analyses: str = ""):
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    analyses = [a.strip() for a in requested_analyses.split(",") if a.strip()]
    sys_log(f"Upload: {file.filename}")
    r.publish("xbin:events", json.dumps({"type": "NEW_BINARY", "filename": file.filename, "path": f"/app/uploads/{file.filename}", "requested_analyses": analyses}))
    return {"status": "success"}

@app.get("/api/v1/plugins/{name}/logs")
def get_plugin_logs(name: str):
    container_name = f"xbin-worker-{name}"
    try:
        res = subprocess.run(["docker", "logs", "--tail", "100", container_name], capture_output=True, text=True)
        return {"logs": res.stdout + res.stderr}
    except Exception as e:
        return {"logs": f"Error: {e}"}

@app.get("/api/v1/plugins/available")
def list_available_plugins():
    if not os.path.exists(PLUGINS_DIR): return {"plugins": []}
    cmd = ["docker", "ps", "-a", "--filter", "name=xbin-worker-", "--format", "{{.Names}}|{{.Status}}|{{.State}}"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    docker_data = {}
    for line in res.stdout.splitlines():
        name, status, state = line.split("|")
        docker_data[name.replace("xbin-worker-", "")] = {"status": status, "state": state}
    
    available = []
    health_data = r.hgetall("xbin:worker_health")
    now = time.time()
    for root, dirs, files in os.walk(PLUGINS_DIR):
        if "Dockerfile" in files:
            name = os.path.basename(root); category = os.path.basename(os.path.dirname(root))
            state_str = r.get(f"xbin:plugin_state:{name}")
            saved = json.loads(state_str) if state_str else {"status": "STOPPED"}
            status = saved["status"]
            if name in docker_data:
                d = docker_data[name]
                status = "RUNNING" if d["state"] == "running" else "CRASHED" if "Exited (0)" not in d["status"] else "STOPPED"
            
            health_status = "UNKNOWN"; last_beat = 0
            for w_id, w_val in health_data.items():
                w_data = json.loads(w_val)
                if w_data.get("backend") == name:
                    last_beat = w_data["last_heartbeat"]
                    health_status = "HEALTHY" if (now - last_beat) < 10 else "DEAD"
            available.append({"name": name, "category": category, "status": status, "health": health_status, "last_beat": last_beat, "error": saved.get("error")})
    return {"plugins": available}

def bg_start_plugin(name: str, category: str):
    image_name, container_name = f"xbin-plugin-{name}", f"xbin-worker-{name}"
    try:
        set_plugin_state(name, "BUILDING")
        subprocess.run(["docker", "build", "-t", image_name, "-f", os.path.join(PLUGINS_DIR, category, name, "Dockerfile"), "."], check=True, stdout=subprocess.DEVNULL)
        set_plugin_state(name, "STARTING")
        subprocess.run(["docker", "rm", "-f", container_name], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        abs_uploads = os.path.abspath(UPLOAD_DIR)
        run_cmd = ["docker", "run", "-d", "--name", container_name, "--network", "host", "-v", f"{abs_uploads}:/app/uploads", "-e", "XBIN_ORCHESTRATOR=localhost:50051", "-e", "REDIS_HOST=localhost", image_name]
        subprocess.run(run_cmd, check=True, stdout=subprocess.DEVNULL)
    except Exception as e:
        sys_log(f"Fail {name}: {e}"); set_plugin_state(name, "ERROR", error=str(e))

@app.post("/api/v1/plugins/{name}/start")
def start_plugin(name: str, category: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(bg_start_plugin, name, category)
    return {"status": "accepted"}

@app.post("/api/v1/plugins/{name}/stop")
def stop_plugin(name: str):
    subprocess.run(["docker", "rm", "-f", f"xbin-worker-{name}"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    set_plugin_state(name, "STOPPED")
    return {"status": "success"}

@app.get("/api/v1/blackboard/{analysis_type}")
def get_analysis_results(analysis_type: str):
    keys = r.keys(f"xbin:bb:{analysis_type}:*")
    return {"analysis_type": analysis_type, "results": {k.split(":")[-1]: json.loads(r.get(k)) for k in keys}}

@app.get("/api/v1/blackboard/{analysis_type}/{item_key}/consensus")
def get_consensus(analysis_type: str, item_key: str):
    """Aggregates all tool reports into a single graph with vouch counts."""
    state_str = r.get(f"xbin:bb:{analysis_type}:{item_key}")
    if not state_str: raise HTTPException(status_code=404)
    
    state = json.loads(state_str)
    consensus = {"nodes": {}, "edges": {}}
    
    for hyp in state["hypotheses"]:
        backend = hyp["backend"]
        data = hyp["data"]
        
        for node in data.get("nodes", []):
            nid = node["id"]
            if nid not in consensus["nodes"]:
                consensus["nodes"][nid] = {"label": node.get("label", nid), "vouches": []}
            if backend not in consensus["nodes"][nid]["vouches"]:
                consensus["nodes"][nid]["vouches"].append(backend)
            
        for edge in data.get("edges", []):
            eid = f"{edge['source']}->{edge['target']}"
            if eid not in consensus["edges"]:
                consensus["edges"][eid] = {"source": edge["source"], "target": edge["target"], "vouches": []}
            if backend not in consensus["edges"][eid]["vouches"]:
                consensus["edges"][eid]["vouches"].append(backend)
            
    return consensus

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>xbin | Consensus Visualizer</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.26.0/cytoscape.min.js"></script>
        <style>
            :root { --bg: #0b0f1a; --card: #161e2e; --text: #f3f4f6; --accent: #3b82f6; --danger: #ef4444; --success: #10b981; --warning: #f59e0b; --muted: #6b7280; --border: #2d3748; }
            body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); margin: 0; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
            header { background: var(--card); padding: 1rem 2rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
            .main-layout { display: grid; grid-template-columns: 340px 1fr; flex: 1; overflow: hidden; }
            .sidebar { border-right: 1px solid var(--border); padding: 1.5rem; overflow-y: auto; background: rgba(22, 30, 46, 0.5); }
            .content { padding: 2rem; overflow-y: auto; }
            .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 1.25rem; margin-bottom: 1.5rem; }
            .btn { border: none; padding: 0.5rem 1rem; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 0.8rem; display: flex; align-items: center; gap: 0.5rem; transition: all 0.2s; }
            .btn:active { transform: scale(0.95); }
            .btn-primary { background: var(--accent); color: white; }
            .btn-danger { background: rgba(239, 68, 68, 0.1); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.1); }
            .btn-action { padding: 0.3rem 0.6rem; font-size: 0.7rem; }
            .plugin-item { padding: 1rem; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 0.75rem; background: rgba(0,0,0,0.2); position: relative; overflow: hidden; }
            .heartbeat-ping { position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: var(--success); opacity: 0; }
            .ping-active { animation: pulse-ping 0.8s ease-out; }
            @keyframes pulse-ping { 0% { opacity: 1; } 100% { opacity: 0; } }
            .badge { padding: 0.2rem 0.5rem; border-radius: 99px; font-size: 0.6rem; font-weight: 800; text-transform: uppercase; }
            .badge-running { background: rgba(16, 185, 129, 0.1); color: var(--success); }
            .badge-wait { background: rgba(245, 158, 11, 0.1); color: var(--warning); animation: blink 1.5s infinite; }
            .badge-error { background: rgba(239, 68, 68, 0.1); color: var(--danger); }
            @keyframes blink { 50% { opacity: 0.5; } }
            table { width: 100%; border-collapse: collapse; }
            th { text-align: left; padding: 0.8rem; color: var(--muted); font-size: 0.7rem; text-transform: uppercase; border-bottom: 1px solid var(--border); }
            td { padding: 0.8rem; border-bottom: 1px solid var(--border); font-size: 0.85rem; }
            #overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); z-index: 1000; display: none; }
            #modal { position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 90vw; height: 85vh; background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 2rem; z-index: 1100; display: none; flex-direction: column; }
            .log-box { flex: 1; background: #070a13; padding: 1rem; border-radius: 8px; font-family: monospace; font-size: 0.75rem; color: #a0aec0; overflow-y: auto; border: 1px solid var(--border); white-space: pre-wrap; }
            #cy-container { flex: 1; background: #070a13; border-radius: 8px; border: 1px solid var(--border); margin-top: 1rem; }
            .toast-container { position: fixed; bottom: 2rem; right: 2rem; z-index: 2000; }
            .toast { background: var(--card); border: 1px solid var(--accent); padding: 1rem; border-radius: 8px; box-shadow: 0 10px 20px rgba(0,0,0,0.5); margin-top: 0.5rem; animation: slideIn 0.3s ease; }
            @keyframes slideIn { from { transform: translateX(100%); } to { transform: translateX(0); } }
        </style>
    </head>
    <body>
        <header>
            <div style="display: flex; align-items: center; gap: 1rem;">
                <div style="background: var(--accent); width: 30px; height: 30px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-weight: 900;">X</div>
                <h1 style="margin: 0; font-size: 1.1rem;">xbin <span style="font-weight: 300; color: var(--muted);">Blackboard</span></h1>
            </div>
            <div style="display: flex; gap: 1rem; align-items: center;">
                <button class="btn" style="background: #2d3748;" onclick="showSystemLogs()">System Logs</button>
                <button class="btn btn-danger btn-action" onclick="bulkAction('stop')">Stop Fleet</button>
                <button class="btn btn-primary btn-action" onclick="bulkAction('start')">Start Fleet</button>
                <div id="orc-health" class="badge badge-running">Orchestrator: OK</div>
            </div>
        </header>

        <div class="main-layout">
            <aside class="sidebar">
                <div class="card">
                    <h2>Deploy Analysis</h2>
                    <input type="file" id="f" style="display:none" onchange="document.getElementById('fl').innerText=this.files[0].name">
                    <button class="btn btn-primary" style="width:100%" onclick="document.getElementById('f').click()">📁 <span id="fl">Binary</span></button>
                    <div style="margin-top:1rem; padding-top:1rem; border-top:1px solid var(--border);">
                        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:0.4rem;">
                            <label style="font-size:0.75rem; display:flex; align-items:center; gap:0.3rem;"><input type="checkbox" class="goal" value="symbol_matching" checked> Symbols</label>
                            <label style="font-size:0.75rem; display:flex; align-items:center; gap:0.3rem;"><input type="checkbox" class="goal" value="cfg_generation" checked> CFG</label>
                        </div>
                    </div>
                    <button class="btn btn-primary" style="width:100%; margin-top:1rem; background:var(--success)" onclick="upload()">🚀 Start Analysis</button>
                </div>
                <div id="plugin-list"></div>
            </aside>
            <main class="content" id="bb-content"></main>
        </div>

        <div id="overlay" onclick="closeModal()"></div>
        <div id="modal">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
                <h3 id="modal-title" style="margin:0; color:var(--accent);">Result</h3>
                <div style="display:flex; gap:0.5rem;">
                    <button class="btn btn-primary btn-action" onclick="copyLogs()">📋 Copy</button>
                    <button onclick="closeModal()" class="btn btn-danger btn-action">Close</button>
                </div>
            </div>
            <div id="modal-content" class="log-box"></div>
            <div id="cy-container" style="display:none"></div>
        </div>

        <div class="toast-container" id="toasts"></div>

        <script>
            let lastHeartbeats = {};
            function toast(m) { const t=document.createElement('div'); t.className='toast'; t.innerText=m; document.getElementById('toasts').appendChild(t); setTimeout(()=>t.remove(),3000); }
            async function upload() {
                const fd=new FormData(); fd.append('file', document.getElementById('f').files[0]);
                const goals=Array.from(document.querySelectorAll('.goal:checked')).map(i=>i.value);
                fd.append('requested_analyses', goals.join(','));
                await fetch('/api/v1/upload', {method:'POST', body:fd}); toast('Binary Announced');
            }
            async function toggle(n,c,s) { const action=s==='RUNNING'?'stop':'start'; await fetch(`/api/v1/plugins/${n}/${action}?category=${c}`, {method:'POST'}); refresh(); }
            async function bulkAction(a, c=null) {
                const res=await fetch('/api/v1/plugins/available'); const data=await res.json();
                data.plugins.forEach(p => {
                    if (c && p.category !== c) return;
                    if (a==='start' && !['RUNNING','BUILDING','STARTING'].includes(p.status)) fetch(`/api/v1/plugins/${p.name}/start?category=${p.category}`, {method:'POST'});
                    if (a==='stop' && p.status==='RUNNING') fetch(`/api/v1/plugins/${p.name}/stop`, {method:'POST'});
                });
            }
            async function showLogs(n) {
                document.getElementById('modal-title').innerText=`Logs: ${n}`;
                document.getElementById('cy-container').style.display='none';
                document.getElementById('modal-content').style.display='block';
                document.getElementById('overlay').style.display='block'; document.getElementById('modal').style.display='flex';
                const res=await fetch(`/api/v1/plugins/${n}/logs`); const d=await res.json();
                document.getElementById('modal-content').innerText=d.logs;
            }
            function showSystemLogs() {
                document.getElementById('modal-title').innerText='System Logs';
                document.getElementById('cy-container').style.display='none';
                document.getElementById('modal-content').style.display='block';
                document.getElementById('overlay').style.display='block'; document.getElementById('modal').style.display='flex';
                fetch('/api/v1/system/logs').then(r=>r.json()).then(d=>document.getElementById('modal-content').innerText=d.logs);
            }
            async function showConsensus(cat, item) {
                document.getElementById('modal-title').innerText=`Consensus CFG: ${item}`;
                document.getElementById('modal-content').style.display='none';
                document.getElementById('cy-container').style.display='block';
                document.getElementById('overlay').style.display='block'; document.getElementById('modal').style.display='flex';
                
                const res = await fetch(`/api/v1/blackboard/${cat}/${item}/consensus`);
                const data = await res.json();
                
                const elements = [];
                for(let id in data.nodes) {
                    const node = data.nodes[id];
                    elements.push({ data: { id: id, label: `${node.label}\\n[${node.vouches.length} vouches]`, vouches: node.vouches.length } });
                }
                for(let id in data.edges) {
                    const edge = data.edges[id];
                    elements.push({ data: { id: id, source: edge.source, target: edge.target, vouches: edge.vouches.length } });
                }

                setTimeout(() => {
                    cytoscape({
                        container: document.getElementById('cy-container'),
                        elements: elements,
                        style: [
                            { selector: 'node', style: { 'background-color': '#3b82f6', 'label': 'data(label)', 'color': '#fff', 'font-size': '8px', 'text-wrap': 'wrap', 'width': (n) => 20 + n.data('vouches')*10 } },
                            { selector: 'edge', style: { 'width': (e) => e.data('vouches')*2, 'line-color': '#4a5568', 'target-arrow-color': '#4a5568', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier' } }
                        ],
                        layout: { name: 'cose' }
                    });
                }, 200);
            }
            function copyLogs() { navigator.clipboard.writeText(document.getElementById('modal-content').innerText); toast('Copied!'); }
            function closeModal() { document.getElementById('modal').style.display='none'; document.getElementById('overlay').style.display='none'; }
            async function refresh() {
                try {
                    const pRes=await fetch('/api/v1/plugins/available'); const pData=await pRes.json();
                    const cats={}; pData.plugins.forEach(p => { if(!cats[p.category]) cats[p.category]=[]; cats[p.category].push(p); });
                    let html='';
                    for(let cat in cats) {
                        html += `<div style="display:flex; justify-content:space-between; margin:1.5rem 0 0.5rem;"><div style="font-size:0.7rem; color:var(--muted); text-transform:uppercase;">${cat}</div><div style="display:flex; gap:0.2rem"><button class="btn btn-action" onclick="bulkAction('stop','${cat}')">Stop</button><button class="btn btn-primary btn-action" onclick="bulkAction('start','${cat}')">Start</button></div></div>`;
                        cats[cat].forEach(p => {
                            if(p.last_beat > (lastHeartbeats[p.name] || 0)) {
                                lastHeartbeats[p.name]=p.last_beat;
                                const el=document.getElementById(`beat-${p.name}`);
                                if(el) { el.classList.remove('ping-active'); void el.offsetWidth; el.classList.add('ping-active'); }
                            }
                            html += `<div class="plugin-item"><div id="beat-${p.name}" class="heartbeat-ping"></div><div style="display:flex; justify-content:space-between; align-items:start"><div><div style="font-weight:bold">${p.name}</div><div class="badge badge-${p.status==='RUNNING'?'running':p.status==='STOPPED'?'stopped':'error'}">${p.status}</div>${p.health==='HEALTHY'?'<span style="color:var(--success); font-size:0.6rem">● READY</span>':''}</div><div style="display:flex; flex-direction:column; gap:0.2rem"><button class="btn btn-action ${p.status==='RUNNING'?'btn-danger':'btn-primary'}" onclick="toggle('${p.name}','${p.category}','${p.status}')">${p.status==='RUNNING'?'Stop':'Start'}</button><button class="btn btn-action" style="background:#2d3748" onclick="showLogs('${p.name}')">Logs</button></div></div></div>`;
                        });
                    }
                    document.getElementById('plugin-list').innerHTML=html;
                    const bb=document.getElementById('bb-content'); bb.innerHTML='';
                    for(let cat of ['symbol_matching', 'cfg_generation']) {
                        const res=await fetch(`/api/v1/blackboard/${cat}`); const d=await res.json();
                        if(Object.keys(d.results).length>0) {
                            let table=`<div class="card"><h2>${cat.replace('_',' ')}</h2><table><tr><th>Target</th><th>Result</th><th>Action</th></tr>`;
                            for(let k in d.results) {
                                const item = d.results[k];
                                table+=`<tr><td style="font-family:monospace">${k}</td><td style="color:var(--accent)">Top Hypothesis by ${item.hypotheses[0].backend}</td><td>${cat==='cfg_generation'?'<button class="btn btn-primary btn-action" onclick="showConsensus(\\''+cat+'\\',\\''+k+'\\')">View Consensus Graph</button>':''}</td></tr>`;
                            }
                            bb.innerHTML += table+'</table></div>';
                        }
                    }
                } catch(e) {}
            }
            setInterval(refresh, 2000); refresh();
        </script>
    </body>
    </html>
    """

# ==========================================
# gRPC BLACKBOARD ENGINE
# ==========================================
class XbinOrchestratorServicer(orchestrator_pb2_grpc.OrchestratorServiceServicer):
    def RegisterWorker(self, request, context):
        r.hset("xbin:active_workers", request.worker_id, f"{request.analysis_type}:{request.backend_name}")
        r.hset("xbin:worker_health", request.worker_id, json.dumps({"backend": request.backend_name, "last_heartbeat": time.time(), "message": "Welcome Signal Received"}))
        sys_log(f"Handshake: {request.worker_id}")
        return orchestrator_pb2.RegisterResponse(success=True)

    def Heartbeat(self, request, context):
        worker_info = r.hget("xbin:active_workers", request.worker_id)
        if worker_info:
            r.hset("xbin:worker_health", request.worker_id, json.dumps({"backend": worker_info.split(":")[-1], "last_heartbeat": time.time(), "message": request.status_message}))
        return orchestrator_pb2.HeartbeatResponse(acknowledged=True)

    def PostResult(self, request, context):
        bb_key = f"xbin:bb:{request.analysis_type}:{request.item_key}"
        weight = BACKEND_WEIGHTS.get(request.backend_name, 0.50)
        new_hyp = {"data": json.loads(request.result_data), "score": round(request.confidence * weight, 3), "backend": request.backend_name}
        state = json.loads(r.get(bb_key)) if r.exists(bb_key) else {"status": "PENDING", "hypotheses": []}
        state["hypotheses"].append(new_hyp); state["hypotheses"] = sorted(state["hypotheses"], key=lambda x: x["score"], reverse=True)
        status = "RESOLVED"
        if len(state["hypotheses"]) > 1:
            if state["hypotheses"][0]["data"] != state["hypotheses"][1]["data"] and (state["hypotheses"][0]["score"] - state["hypotheses"][1]["score"]) <= MARGIN_THRESHOLD:
                status = "CONFLICTED"
        state["status"] = status; r.set(bb_key, json.dumps(state))
        sys_log(f"Update [{request.analysis_type}]: {request.item_key}")
        r.publish("xbin:events", json.dumps({"type": "BLACKBOARD_UPDATE", "analysis_type": request.analysis_type, "item_key": request.item_key, "top_hypothesis": state["hypotheses"][0], "status": status}))
        return orchestrator_pb2.PostResultResponse(accepted=True, current_status=status)

def main():
    ensure_redis(); cleanup_stale_plugins(); r.flushdb()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    orchestrator_pb2_grpc.add_OrchestratorServiceServicer_to_server(XbinOrchestratorServicer(), server)
    server.add_insecure_port(GRPC_PORT); server.start()
    sys_log("xbin Multi-Analysis Engine Online")
    uvicorn.run(app, host="0.0.0.0", port=REST_PORT, log_level="warning")

if __name__ == '__main__':
    main()

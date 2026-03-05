# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from flask_sock import Sock
from apscheduler.schedulers.background import BackgroundScheduler
from functools import wraps
import requests, sys, datetime, json, os, uuid

PORT = 5000
WEB_USER = os.environ.get("WEB_USER", "admin")
WEB_PASS = os.environ.get("WEB_PASS", "admin123")
REPORT_HOUR = 0
REPORT_MINUTE = 5

app = Flask(__name__)
app.secret_key = os.urandom(24) 
sock = Sock(app)

DAILY_CACHE = {}
WS_CLIENTS = set()
CONFIG_FILE = "/opt/traffic_monitor/data/config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f: return json.load(f)
        except: pass
    return {"tg_token": "", "tg_chat_id": "", "nodes": {}, "tokens": {}}

def save_config(data):
    with open(CONFIG_FILE, 'w') as f: json.dump(data, f)

CONFIG = load_config()
if "nodes" not in CONFIG: CONFIG["nodes"] = {}
if "tokens" not in CONFIG: CONFIG["tokens"] = {}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'): return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

HTML_LOGIN = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Traffic Monitor</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-900 flex items-center justify-center min-h-screen">
    <div class="bg-slate-800 p-8 rounded-2xl shadow-2xl border border-slate-700 w-96">
        <h1 class="text-2xl font-bold text-white mb-6 text-center">Xray Monitor</h1>
        {% if error %}<p class="text-red-500 text-sm mb-4 text-center">{{ error }}</p>{% endif %}
        <form method="POST" action="/login">
            <input type="text" name="username" placeholder="Username" class="w-full mb-4 bg-slate-900 border border-slate-700 rounded-lg p-3 text-white focus:border-indigo-500 outline-none" required>
            <input type="password" name="password" placeholder="Password" class="w-full mb-6 bg-slate-900 border border-slate-700 rounded-lg p-3 text-white focus:border-indigo-500 outline-none" required>
            <button type="submit" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 rounded-lg transition">Login</button>
        </form>
    </div>
</body>
</html>
"""

HTML_DASHBOARD = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Xray Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .pulse { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-thumb { background: #475569; border-radius: 3px; }
    </style>
</head>
<body class="bg-slate-900 text-gray-200 min-h-screen flex flex-col">
    <nav class="bg-slate-800 border-b border-slate-700 p-4 sticky top-0 z-40 shadow-md">
        <div class="max-w-7xl mx-auto flex justify-between items-center">
            <div class="flex items-center gap-3">
                <h1 class="text-xl font-bold text-white flex items-center gap-2">Xray Dashboard</h1>
                <div class="flex items-center gap-2 text-xs bg-slate-900 px-2 py-1 rounded border border-slate-700">
                    <span id="ws-status" class="w-2 h-2 rounded-full bg-red-500"></span>
                    <span id="ws-text" class="text-slate-400">Connecting</span>
                </div>
            </div>
            <div class="flex items-center gap-3">
                <button onclick="openModal('addNodeModal')" class="text-sm bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1.5 rounded transition shadow-lg shadow-indigo-500/20">Add Node</button>
                <button onclick="openModal('settingsModal')" class="text-sm bg-slate-700 hover:bg-slate-600 text-white px-3 py-1.5 rounded transition">Settings</button>
                <button onclick="forceReport()" class="text-sm border border-slate-600 hover:bg-slate-700 text-white px-3 py-1.5 rounded transition">Push TG</button>
                <a href="/logout" class="text-sm text-red-400 hover:text-red-300 ml-2">Logout</a>
            </div>
        </div>
    </nav>

    <main class="flex-1 p-4 md:p-8 max-w-7xl mx-auto w-full">
        <div id="nodes-container" class="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6"></div>
    </main>

    <div id="addNodeModal" class="fixed inset-0 bg-black/60 backdrop-blur-sm hidden items-center justify-center z-50">
        <div class="bg-slate-800 p-6 rounded-xl border border-slate-700 w-full max-w-md shadow-2xl">
            <div class="flex justify-between items-center mb-4">
                <h2 class="text-xl font-bold text-white">Add / Update Node</h2>
                <button onclick="closeModal('addNodeModal')" class="text-slate-400 hover:text-white">X</button>
            </div>
            <p class="text-xs text-slate-400 mb-4">Leave blank for auto-generated ID, or specify a unique English ID.</p>
            <input id="newNodeId" type="text" placeholder="Leave blank for random ID" class="w-full mb-4 bg-slate-900 border border-slate-700 rounded-lg p-3 text-white focus:border-indigo-500 outline-none">
            <button onclick="generateCmd()" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2.5 rounded-lg transition">Generate Command</button>
            <div id="cmdResult" class="mt-4 hidden">
                <p class="text-sm text-green-400 mb-2">Run this on Node VPS:</p>
                <div class="bg-slate-900 p-3 rounded border border-slate-700 relative">
                    <code id="installCmd" class="text-xs text-indigo-300 break-all select-all font-mono"></code>
                </div>
            </div>
        </div>
    </div>

    <div id="renameModal" class="fixed inset-0 bg-black/60 backdrop-blur-sm hidden items-center justify-center z-50">
        <div class="bg-slate-800 p-6 rounded-xl border border-slate-700 w-full max-w-sm shadow-2xl">
            <h2 class="text-xl font-bold text-white mb-4">Edit Display Name</h2>
            <input type="hidden" id="renameTargetId">
            <input id="renameInput" type="text" placeholder="Leave blank to reset" class="w-full mb-4 bg-slate-900 border border-slate-700 rounded-lg p-3 text-white focus:border-indigo-500 outline-none">
            <div class="flex gap-3">
                <button onclick="closeModal('renameModal')" class="flex-1 bg-slate-700 hover:bg-slate-600 py-2 rounded-lg transition">Cancel</button>
                <button onclick="submitRename()" class="flex-1 bg-indigo-600 hover:bg-indigo-700 py-2 rounded-lg transition">Save</button>
            </div>
        </div>
    </div>

    <div id="settingsModal" class="fixed inset-0 bg-black/60 backdrop-blur-sm hidden items-center justify-center z-50">
        <div class="bg-slate-800 p-6 rounded-xl border border-slate-700 w-full max-w-md shadow-2xl">
            <div class="flex justify-between items-center mb-4">
                <h2 class="text-xl font-bold text-white">System Settings</h2>
                <button onclick="closeModal('settingsModal')" class="text-slate-400 hover:text-white">X</button>
            </div>
            <div class="space-y-4">
                <div>
                    <label class="block text-xs text-slate-400 mb-1">Telegram Bot Token</label>
                    <input id="tgTokenInput" type="text" value="{{ config.get('tg_token', '') }}" class="w-full bg-slate-900 border border-slate-700 rounded p-2 text-white text-sm outline-none focus:border-indigo-500">
                </div>
                <div>
                    <label class="block text-xs text-slate-400 mb-1">Telegram Chat ID</label>
                    <input id="tgChatIdInput" type="text" value="{{ config.get('tg_chat_id', '') }}" class="w-full bg-slate-900 border border-slate-700 rounded p-2 text-white text-sm outline-none focus:border-indigo-500">
                </div>
            </div>
            <button onclick="saveSettings()" class="w-full mt-6 bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2.5 rounded-lg transition">Save Settings</button>
        </div>
    </div>

    <script>
        const NODE_NAMES = {{ config.get('nodes', {}) | tojson }};
        const GH_USER = "{{ gh_user }}";

        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024, sizes = ['B', 'KB', 'MB', 'GB', 'TB'], i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }

        function openModal(id) { document.getElementById(id).style.display = 'flex'; }
        function closeModal(id) { document.getElementById(id).style.display = 'none'; }

        async function generateCmd() {
            let nodeId = document.getElementById('newNodeId').value.trim();
            if(!nodeId) {
                nodeId = 'node-' + Math.random().toString(36).substring(2, 6);
            }
            
            const res = await fetch('/api/add_node', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({node_id: nodeId})
            });
            const data = await res.json();
            if(data.status !== 'success') return alert('Error generating node token');

            const origin = "https://" + window.location.host;
            const endpoint = origin + "/api/upload_stats";
            
            const githubRawUrl = `https://raw.githubusercontent.com/${GH_USER}/Xray-traffic_hub/main/agent.sh`;
            const cmdText = `curl -sL ${githubRawUrl} | sudo bash -s -- -e ${endpoint} -t ${data.token}`;
            
            document.getElementById('installCmd').innerText = cmdText;
            document.getElementById('cmdResult').style.display = 'block';
        }

        function openRename(nodeId) {
            document.getElementById('renameTargetId').value = nodeId;
            document.getElementById('renameInput').value = NODE_NAMES[nodeId] || nodeId;
            openModal('renameModal');
        }
        
        async function submitRename() {
            const nodeId = document.getElementById('renameTargetId').value;
            const newName = document.getElementById('renameInput').value.trim();
            await fetch('/api/rename_node', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({node_id: nodeId, new_name: newName})
            });
            window.location.reload();
        }

        // --- 核心：彻底删除节点逻辑 ---
        async function deleteNode(nodeId) {
            const displayName = NODE_NAMES[nodeId] || nodeId;
            if(!confirm(`⚠️ 警告: 确定要删除节点 [${displayName}] 吗？\n删除后该节点将立即失去连接权限，且大屏数据会被清空！`)) return;
            
            await fetch('/api/delete_node', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({node_id: nodeId})
            });
            window.location.reload();
        }

        async function saveSettings() {
            const token = document.getElementById('tgTokenInput').value.trim();
            const chatId = document.getElementById('tgChatIdInput').value.trim();
            await fetch('/api/save_settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({tg_token: token, tg_chat_id: chatId})
            });
            alert('Settings Saved!');
            closeModal('settingsModal');
        }

        async function forceReport() {
            alert('Pushing to Telegram...');
            fetch('/api/force_report');
        }

        const container = document.getElementById('nodes-container');
        let nodesData = {};

        function render() {
            container.innerHTML = '';
            for (const [nodeId, users] of Object.keys(nodesData).sort().map(k => [k, nodesData[k]])) {
                let rows = '';
                let totalUp = 0, totalDown = 0;
                const displayName = NODE_NAMES[nodeId] || nodeId;

                for (const [user, stats] of Object.entries(users).sort((a,b) => (b[1].up+b[1].down) - (a[1].up+a[1].down))) {
                    totalUp += stats.up; totalDown += stats.down;
                    if(stats.up + stats.down > 0) {
                        rows += `
                            <tr class="border-b border-slate-700/50 hover:bg-slate-700/20 transition">
                                <td class="py-2.5 text-slate-300 truncate max-w-[100px]" title="${user}">${user}</td>
                                <td class="py-2.5 text-green-400/90 text-right">${formatBytes(stats.up)}</td>
                                <td class="py-2.5 text-blue-400/90 text-right">${formatBytes(stats.down)}</td>
                                <td class="py-2.5 text-white font-mono text-right">${formatBytes(stats.up + stats.down)}</td>
                            </tr>`;
                    }
                }

                const card = `
                    <div class="bg-slate-800 rounded-xl border border-slate-700 p-5 shadow-xl relative overflow-hidden transition-all hover:border-indigo-500/50">
                        <div class="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-indigo-500 to-purple-500"></div>
                        <h2 class="text-lg font-bold text-white mb-4 flex justify-between items-center group">
                            <div class="flex items-center gap-2">
                                <span>${displayName}</span>
                                <button onclick="openRename('${nodeId}')" class="text-slate-500 hover:text-indigo-400 opacity-0 group-hover:opacity-100 transition" title="Edit Name">✏️</button>
                                <button onclick="deleteNode('${nodeId}')" class="text-slate-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition ml-1" title="Delete Node">������️</button>
                            </div>
                            <span class="text-[10px] text-slate-400 bg-slate-900 px-2 py-1 rounded flex items-center gap-1.5 border border-slate-700">Live <span class="text-green-500 pulse">*</span></span>
                        </h2>
                        <div class="mb-5 flex justify-between text-sm bg-slate-900/50 p-3 rounded-lg border border-slate-700/50">
                            <div><span class="text-slate-500 block text-xs mb-0.5">Upload</span> <span class="text-green-400 font-bold">${formatBytes(totalUp)}</span></div>
                            <div class="text-right"><span class="text-slate-500 block text-xs mb-0.5">Download</span> <span class="text-blue-400 font-bold">${formatBytes(totalDown)}</span></div>
                        </div>
                        <div class="overflow-x-auto">
                            <table class="w-full text-sm">
                                <thead>
                                    <tr class="text-slate-500 text-left border-b border-slate-600">
                                        <th class="pb-2 font-medium">User</th>
                                        <th class="pb-2 font-medium text-right">Up</th>
                                        <th class="pb-2 font-medium text-right">Down</th>
                                        <th class="pb-2 font-medium text-right">Total</th>
                                    </tr>
                                </thead>
                                <tbody>${rows}</tbody>
                            </table>
                        </div>
                    </div>`;
                container.innerHTML += card;
            }
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        function connectWS() {
            const ws = new WebSocket(wsUrl);
            ws.onopen = () => {
                document.getElementById('ws-status').className = 'w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.8)]';
                document.getElementById('ws-text').innerText = 'Connected';
            };
            ws.onmessage = (event) => {
                const msg = JSON.parse(event.data);
                if (msg.type === 'init') { nodesData = msg.data || {}; } 
                else if (msg.type === 'update') { nodesData[msg.node] = msg.data; }
                else if (msg.type === 'delete') { delete nodesData[msg.node]; }
                render();
            };
            ws.onclose = () => {
                document.getElementById('ws-status').className = 'w-2 h-2 rounded-full bg-red-500';
                document.getElementById('ws-text').innerText = 'Reconnecting...';
                setTimeout(connectWS, 3000);
            };
        }
        connectWS();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    if session.get('logged_in'): return redirect(url_for('dashboard_page'))
    return redirect(url_for('login_page'))

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        if request.form.get('username') == WEB_USER and request.form.get('password') == WEB_PASS:
            session['logged_in'] = True
            return redirect(url_for('dashboard_page'))
        return render_template_string(HTML_LOGIN, error="Incorrect credentials")
    return render_template_string(HTML_LOGIN)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login_page'))

@app.route('/dashboard')
@login_required
def dashboard_page():
    # 动态把 github 用户名传给前端，防止硬编码
    gh_user = "lengmo23" 
    return render_template_string(HTML_DASHBOARD, config=CONFIG, gh_user=gh_user)

@app.route('/api/add_node', methods=['POST'])
@login_required
def add_node():
    node_id = request.json.get('node_id')
    if not node_id: return jsonify({"status": "error"}), 400
    
    node_token = str(uuid.uuid4())
    CONFIG['tokens'][node_id] = node_token
    save_config(CONFIG)
    
    return jsonify({"status": "success", "token": node_token})

@app.route('/api/rename_node', methods=['POST'])
@login_required
def rename_node():
    node_id = request.json.get('node_id')
    new_name = request.json.get('new_name')
    if new_name == "": CONFIG['nodes'].pop(node_id, None)
    else: CONFIG['nodes'][node_id] = new_name
    save_config(CONFIG)
    return jsonify({"status": "success"})

# --- 核心新增：彻底删除节点接口 ---
@app.route('/api/delete_node', methods=['POST'])
@login_required
def delete_node():
    node_id = request.json.get('node_id')
    if not node_id: return jsonify({"status": "error"}), 400

    # 1. 吊销权限并清除别名
    CONFIG.get('nodes', {}).pop(node_id, None)
    CONFIG.get('tokens', {}).pop(node_id, None)
    save_config(CONFIG)

    # 2. 从今日内存缓存中彻底抹除
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if today in DAILY_CACHE and node_id in DAILY_CACHE[today]:
        DAILY_CACHE[today].pop(node_id, None)
        
        # 3. 通知所有在线的大屏立刻移除该节点
        push_msg = json.dumps({"type": "delete", "node": node_id})
        for client in list(WS_CLIENTS):
            try: client.send(push_msg)
            except: WS_CLIENTS.remove(client)

    return jsonify({"status": "success"})

@app.route('/api/save_settings', methods=['POST'])
@login_required
def save_settings():
    CONFIG['tg_token'] = request.json.get('tg_token', '')
    CONFIG['tg_chat_id'] = request.json.get('tg_chat_id', '')
    save_config(CONFIG)
    return jsonify({"status": "success"})

@sock.route('/ws')
def websocket_route(ws):
    WS_CLIENTS.add(ws)
    try:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        if today in DAILY_CACHE: ws.send(json.dumps({"type": "init", "data": DAILY_CACHE[today]}))
        while True: ws.receive()
    except: pass
    finally:
        if ws in WS_CLIENTS: WS_CLIENTS.remove(ws)

def get_total_traffic(data_dict):
    return sum(u.get('up',0) + u.get('down',0) for u in data_dict.values())

@app.route('/api/upload_stats', methods=['POST'])
def upload_stats():
    req = request.json
    if not req: return jsonify({"status": "error"}), 400
    
    client_token = req.get("token")
    node_id = None
    
    for nid, tk in CONFIG.get('tokens', {}).items():
        if tk == client_token:
            node_id = nid
            break
            
    if not node_id:
        return jsonify({"status": "error", "msg": "Unauthorized Token"}), 403
    
    date, data = req.get("date"), req.get("data")
    if not date: return jsonify({"error": "No date"}), 400
    if date not in DAILY_CACHE: DAILY_CACHE[date] = {}
    
    old_data = DAILY_CACHE[date].get(node_id, {})
    if get_total_traffic(data) >= get_total_traffic(old_data):
        DAILY_CACHE[date][node_id] = data

    push_msg = json.dumps({"type": "update", "node": node_id, "data": data})
    for client in list(WS_CLIENTS):
        try: client.send(push_msg)
        except: WS_CLIENTS.remove(client)
        
    return jsonify({"status": "success"}), 200

@app.route('/api/force_report', methods=['GET'])
@login_required
def force_report():
    target = datetime.datetime.now().strftime("%Y-%m-%d")
    generate_report_and_send(target)
    return "Report Sent", 200

def numfmt(num):
    if num >= 1024**4: return "%.2fTB" % (num / 1024**4)
    elif num >= 1024**3: return "%.2fGB" % (num / 1024**3)
    elif num >= 1024**2: return "%.2fMB" % (num / 1024**2)
    else: return "%.2fKB" % (num / 1024)

def send_telegram_message(text):
    tg_token = CONFIG.get("tg_token")
    tg_chat_id = CONFIG.get("tg_chat_id")
    if not tg_token or not tg_chat_id: return
    try: requests.post(f"https://api.telegram.org/bot{tg_token}/sendMessage", data={"chat_id": tg_chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)
    except: pass

def generate_report_and_send(date_str):
    if date_str not in DAILY_CACHE or not DAILY_CACHE[date_str]: return
    nodes = DAILY_CACHE[date_str]
    lines = [f"<b>Traffic: {date_str}</b>"]
    g_up, g_down = 0, 0
    for node_id, users in sorted(nodes.items()):
        display_name = CONFIG.get('nodes', {}).get(node_id, node_id)
        
        lines.append(f"\n<b>{display_name}</b>")
        lines.append("<pre>")
        lines.append(f"{'User':<10} {'Up':<7} {'Down':<7} {'Total':<7}")
        n_up, n_down = 0, 0
        for u, s in users.items():
            uu, dd = s.get('up',0), s.get('down',0)
            n_up+=uu; n_down+=dd; 
            if (uu+dd)>0: lines.append(f"{u[:10]:<10} {numfmt(uu):<7} {numfmt(dd):<7} {numfmt(uu+dd):<7}")
        lines.append(f"{'-'*34}")
        lines.append(f"{'SUM':<10} {numfmt(n_up):<7} {numfmt(n_down):<7} {numfmt(n_up+n_down):<7}")
        lines.append("</pre>")
        g_up+=n_up; g_down+=n_down
    lines.append(f"\n<b>Total</b>: {numfmt(g_up+g_down)}")
    send_telegram_message("\n".join(lines))

if __name__ == "__main__":
    sched = BackgroundScheduler()
    sched.add_job(lambda: generate_report_and_send((datetime.datetime.now()-datetime.timedelta(days=1)).strftime("%Y-%m-%d")), 'cron', hour=REPORT_HOUR, minute=REPORT_MINUTE)
    sched.start()
    app.run(host='0.0.0.0', port=PORT, debug=False)

"""手机网页遥控台：内置 HTTP 服务，用手机浏览器远程控制这台电脑。

为什么需要它：小米不开放个人把自定义设备加入米家 App，因此米家侧只能实现
「手动场景按钮」；若想要一个功能完整、可远程操作的图形界面，本模块提供
一个自带移动端页面的轻量 Web 服务（仅用标准库，无额外依赖）。

安全设计：
  - 默认关闭，需用户主动启用
  - 所有请求必须携带访问令牌（URL 参数 t / 请求头 X-Token）
  - 令牌在首次启用时随机生成，可随时重置
  - 动作在白名单内，仅允许电源、截屏、状态、音量、媒体、已配置应用与唤醒目标
  - 建议仅在内网使用；需要外网访问时请用 VPN（如 Tailscale）而非直接映射端口
"""
from __future__ import annotations

import json
import mimetypes
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse

from .config import Config, SCREENSHOT_DIR
from .core import sysinfo
from .tasks import MatchedTask, TaskExecutor

# 允许通过遥控台触发的动作白名单
ALLOWED_ACTIONS = {
    "shutdown", "restart", "lock", "sleep", "hibernate", "signout",
    "cancel_shutdown", "screenshot", "report_status", "volume", "media",
    "open_app", "wol",
}

_TOAST_ACTIONS = {"shutdown", "restart", "hibernate", "signout"}


def _http_ok(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    server_version = "VoxNode"
    protocol_version = "HTTP/1.1"

    # -- 基础设施 ------------------------------------------------------
    def log_message(self, fmt: str, *args) -> None:  # 静音标准日志
        pass

    @property
    def app(self) -> "RemoteServer":
        return self.server.app  # type: ignore[attr-defined]

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _query(self) -> dict:
        parsed = urlparse(self.path)
        return {k: v[0] for k, v in parse_qs(parsed.query).items()}

    def _token_ok(self, query: dict) -> bool:
        token = query.get("t") or self.headers.get("X-Token", "")
        return bool(token) and secrets.compare_digest(token, self.app.token)

    # -- 路由 ----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        query = self._query()

        if path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return
        if not self._token_ok(query):
            self._send(401, _http_ok({"error": "访问令牌无效，请使用软件「遥控台」页显示的完整链接"}))
            return

        if path == "/":
            self._send(200, self.app.page_html().encode("utf-8"),
                       "text/html; charset=utf-8")
        elif path == "/api/status":
            self._send(200, _http_ok(self.app.status()))
        elif path == "/api/config":
            self._send(200, _http_ok(self.app.client_config()))
        elif path == "/api/screenshot":
            self._send_screenshot()
        else:
            self._send(404, _http_ok({"error": "未找到"}))

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        query = self._query()
        if not self._token_ok(query):
            self._send(401, _http_ok({"error": "访问令牌无效"}))
            return
        if path != "/api/action":
            self._send(404, _http_ok({"error": "未找到"}))
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send(400, _http_ok({"error": "请求体不是合法 JSON"}))
            return

        action = str(payload.get("action", ""))
        params = payload.get("params") or {}
        if action not in ALLOWED_ACTIONS:
            self._send(403, _http_ok({"error": f"不允许的动作：{action}"}))
            return
        if not isinstance(params, dict):
            self._send(400, _http_ok({"error": "params 必须是对象"}))
            return

        result = self.app.run_action(action, params)
        self._send(200, _http_ok(result))

    def _send_screenshot(self) -> None:
        directory = Path(self.app.screenshot_dir or SCREENSHOT_DIR)
        files = sorted(directory.glob("screenshot_*.png"), reverse=True) if directory.is_dir() else []
        if not files:
            self._send(404, _http_ok({"error": "还没有截图，请先点「截屏」"}))
            return
        data = files[0].read_bytes()
        self._send(200, data, mimetypes.guess_type(files[0].name)[0] or "image/png")


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, handler, app: "RemoteServer"):
        self.app = app
        super().__init__(addr, handler)


class RemoteServer:
    """遥控台服务：在后台线程里提供手机可访问的控制页面。"""

    def __init__(self, config: Config,
                 executor_factory: Callable[[], TaskExecutor],
                 on_log: Callable[[str], None] = lambda m: None):
        self.config = config
        self.executor_factory = executor_factory
        self.on_log = on_log
        self._server: Optional[_Server] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.ensure_token()

    # -- 令牌 ----------------------------------------------------------
    def ensure_token(self) -> str:
        token = self.config.get("remote.token", "")
        if not token:
            token = secrets.token_urlsafe(18)
            self.config.set("remote.token", token)
        return token

    def reset_token(self) -> str:
        token = secrets.token_urlsafe(18)
        self.config.set("remote.token", token)
        return token

    @property
    def token(self) -> str:
        return self.config.get("remote.token", "") or self.ensure_token()

    @property
    def port(self) -> int:
        return int(self.config.get("remote.port", 8765))

    @property
    def bind(self) -> str:
        return self.config.get("remote.bind", "0.0.0.0") or "0.0.0.0"

    # -- 生命周期 ------------------------------------------------------
    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> bool:
        with self._lock:
            if self.running:
                return True
            self.ensure_token()
            try:
                self._server = _Server((self.bind, self.port), _Handler, self)
            except OSError as e:
                self.on_log(f"遥控台启动失败：端口 {self.port} 不可用（{e}）")
                self._server = None
                return False
            self._thread = threading.Thread(target=self._server.serve_forever,
                                            name="voxnode-remote", daemon=True)
            self._thread.start()
            self.on_log(f"遥控台已启动：{self.bind}:{self.port}")
            return True

    def stop(self) -> None:
        with self._lock:
            server, thread = self._server, self._thread
            self._server, self._thread = None, None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2)
        self.on_log("遥控台已停止")

    # -- 业务 ----------------------------------------------------------
    @property
    def screenshot_dir(self) -> str:
        return self.config.get("screenshot_dir", "") or str(SCREENSHOT_DIR)

    def run_action(self, action: str, params: dict) -> dict:
        try:
            executor = self.executor_factory()
            result = executor.execute(MatchedTask(
                rule={"action": action, "params": params}, groups={}))
        except Exception as e:
            self.on_log(f"遥控台动作 {action} 失败：{e}")
            return {"ok": False, "reply": f"执行失败：{e}"}
        self.on_log(f"遥控台执行 {action}：{'成功' if result.ok else '失败'}")
        return {"ok": result.ok, "reply": result.reply}

    def status(self) -> dict:
        try:
            from .core import monitor
            data = sysinfo.summary()
            try:
                data["disk_percent"] = monitor.disk_usage("C:\\")["percent"]
            except Exception:
                data["disk_percent"] = 0
            return {"ok": True, **data}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def client_config(self) -> dict:
        """页面初始化用：可点的应用、唤醒目标、音量/媒体指令等。"""
        return {
            "apps": [a.get("name", "") for a in self.config.get("apps", []) if a.get("name")],
            "wol": [h.get("name", "") for h in self.config.get("wol", []) if h.get("name")],
            "host": sysinfo.hostname(),
        }

    # -- 访问地址 ------------------------------------------------------
    def urls(self) -> list[str]:
        token = self.token
        port = self.port
        out = []
        for itf in sysinfo.interfaces():
            ip = itf.get("ipv4") or ""
            if ip and not ip.startswith("127."):
                out.append(f"http://{ip}:{port}/?t={token}")
        if not out:
            out.append(f"http://127.0.0.1:{port}/?t={token}")
        return out

    # -- 页面 ----------------------------------------------------------
    def page_html(self) -> str:
        return _PAGE.replace("__TOKEN__", self.token)


# ---------------------------------------------------------------- 移动端页面
_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#14161a">
<title>VoxNode 遥控台</title>
<style>
  :root{
    --bg:#14161a; --card:#22262e; --card2:#282d36; --border:#2e333d;
    --text:#e8eaed; --muted:#9aa0aa; --accent:#ff6900; --ok:#46c46c; --danger:#e5484d;
  }
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  body{margin:0;background:var(--bg);color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;
    padding:16px 14px 40px}
  h1{font-size:19px;margin:0 0 2px;font-weight:700}
  h1 span{color:var(--accent)}
  .sub{color:var(--muted);font-size:12px;margin-bottom:14px}
  .stats{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin-bottom:16px}
  .stat{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:10px 11px}
  .stat .k{color:var(--muted);font-size:11px}
  .stat .v{font-size:16px;font-weight:700;margin:3px 0 5px}
  .bar{height:5px;border-radius:3px;background:#1a1d23;overflow:hidden}
  .bar i{display:block;height:100%;width:0;background:var(--accent);transition:width .4s}
  h2{font-size:12px;color:var(--muted);font-weight:600;margin:18px 0 8px;letter-spacing:.5px}
  .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}
  .grid.two{grid-template-columns:repeat(2,1fr)}
  button{font:inherit;color:var(--text);background:var(--card);border:1px solid var(--border);
    border-radius:12px;padding:13px 6px;cursor:pointer;transition:transform .06s,background .15s}
  button:active{transform:scale(.96);background:var(--card2)}
  button.hot{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
  button.danger{border-color:var(--danger);color:var(--danger)}
  button.danger:active{background:var(--danger);color:#fff}
  .empty{color:var(--muted);font-size:12px}
  #toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%) translateY(80px);
    background:#2b313b;border:1px solid var(--border);color:var(--text);
    padding:11px 18px;border-radius:11px;font-size:13px;max-width:86vw;text-align:center;
    opacity:0;transition:.25s;pointer-events:none;z-index:9}
  #toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
  #shot{position:fixed;inset:0;background:rgba(0,0,0,.88);display:none;
    align-items:center;justify-content:center;padding:12px;z-index:10}
  #shot img{max-width:100%;max-height:100%;border-radius:8px}
  .foot{color:var(--muted);font-size:11px;margin-top:26px;text-align:center;line-height:1.6}
</style>
</head>
<body>
  <h1>VoxNode <span>遥控台</span></h1>
  <div class="sub" id="host">连接中…</div>

  <div class="stats">
    <div class="stat"><div class="k">CPU</div><div class="v" id="cpu">--</div>
      <div class="bar"><i id="cpub"></i></div></div>
    <div class="stat"><div class="k">内存</div><div class="v" id="mem">--</div>
      <div class="bar"><i id="memb"></i></div></div>
    <div class="stat"><div class="k">C 盘</div><div class="v" id="disk">--</div>
      <div class="bar"><i id="diskb"></i></div></div>
  </div>

  <h2>电源</h2>
  <div class="grid">
    <button class="danger" onclick="act('lock')">锁屏</button>
    <button onclick="act('sleep')">睡眠</button>
    <button onclick="act('cancel_shutdown')">取消关机</button>
    <button class="danger" onclick="act('hibernate',{},true)">休眠</button>
    <button class="danger" onclick="act('signout',{},true)">注销</button>
    <button class="danger" onclick="act('restart',{delay:60},true)">重启</button>
    <button class="danger" style="grid-column:span 3" onclick="act('shutdown',{delay:60},true)">关机（60 秒）</button>
  </div>

  <h2>常用</h2>
  <div class="grid">
    <button class="hot" onclick="act('screenshot')">截屏</button>
    <button onclick="act('report_status')">系统状态</button>
    <button onclick="shot()">查看屏幕</button>
  </div>

  <h2>音量与播放</h2>
  <div class="grid">
    <button onclick="act('volume',{op:'减'})">音量 −</button>
    <button onclick="act('volume',{op:'静音'})">静音</button>
    <button onclick="act('volume',{op:'加'})">音量 ＋</button>
    <button onclick="act('media',{op:'上一首'})">上一首</button>
    <button onclick="act('media',{op:'暂停'})">播放/暂停</button>
    <button onclick="act('media',{op:'下一首'})">下一首</button>
  </div>

  <h2>打开应用</h2>
  <div class="grid two" id="apps"><div class="empty">加载中…</div></div>

  <h2>唤醒其他设备（WOL）</h2>
  <div class="grid two" id="wol"><div class="empty">加载中…</div></div>

  <div class="foot">
    令牌已内置于当前链接，请勿转发给他人<br>
    离开内网使用请通过 VPN 访问，不要直接把端口映射到公网
  </div>

  <div id="toast"></div>
  <div id="shot" onclick="this.style.display='none'"><img id="shotimg" alt="屏幕截图"></div>

<script>
const TOKEN = "__TOKEN__";
const q = "?t=" + encodeURIComponent(TOKEN);

function toast(msg, ms){
  const el = document.getElementById("toast");
  el.textContent = msg; el.classList.add("show");
  clearTimeout(el._t); el._t = setTimeout(()=>el.classList.remove("show"), ms||2600);
}

async function act(action, params, confirmFirst){
  if (confirmFirst && !confirm("确定要执行「" + action + "」吗？")) return;
  try{
    const r = await fetch("/api/action" + q, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({action:action, params:params||{}})
    });
    const d = await r.json();
    toast(d.ok === false ? ("失败：" + (d.reply||d.error||"未知错误")) : (d.reply||"已执行"));
    if (action === "shutdown" || action === "restart") refresh();
  }catch(e){ toast("请求失败：" + e.message); }
}

async function shot(){
  try{
    const r = await fetch("/api/screenshot" + q);
    if(!r.ok){ const d = await r.json().catch(()=>({})); toast(d.error||"暂无截图"); return; }
    const blob = await r.blob();
    document.getElementById("shotimg").src = URL.createObjectURL(blob);
    document.getElementById("shot").style.display = "flex";
  }catch(e){ toast("获取截图失败：" + e.message); }
}

async function refresh(){
  try{
    const d = await (await fetch("/api/status" + q)).json();
    if(!d.ok) return;
    document.getElementById("host").textContent =
      d.hostname + " · " + d.os + " · 已运行 " + d.uptime;
    document.getElementById("cpu").textContent = Math.round(d.cpu_percent) + "%";
    document.getElementById("cpub").style.width = d.cpu_percent + "%";
    document.getElementById("mem").textContent = Math.round(d.mem_percent) + "%";
    document.getElementById("memb").style.width = d.mem_percent + "%";
    document.getElementById("disk").textContent = Math.round(d.disk_percent||0) + "%";
    document.getElementById("diskb").style.width = (d.disk_percent||0) + "%";
  }catch(e){}
}

function fill(container, items, key, action, emptyText){
  container.innerHTML = "";
  if(!items || !items.length){
    const d = document.createElement("div");
    d.className = "empty"; d.textContent = emptyText;
    container.appendChild(d);
    return;
  }
  items.forEach(function(name){
    const b = document.createElement("button");
    b.textContent = name;
    b.onclick = function(){ const p = {}; p[key] = name; act(action, p); };
    container.appendChild(b);
  });
}

async function loadConfig(){
  try{
    const d = await (await fetch("/api/config" + q)).json();
    fill(document.getElementById("apps"), d.apps, "app", "open_app", "尚未在软件里配置应用");
    fill(document.getElementById("wol"), d.wol, "host", "wol", "尚未配置唤醒目标");
  }catch(e){}
}

refresh(); loadConfig();
setInterval(refresh, 3000);
</script>
</body>
</html>
"""


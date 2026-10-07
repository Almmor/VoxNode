"""核心功能单元测试（pytest）。

运行：pytest -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from miiotpcapi.config import DEFAULT_TASKS, Config
from miiotpcapi.core import monitor, screenshot, sysinfo, wol
from miiotpcapi.tasks import ACTIONS, TaskExecutor, match
from miiotpcapi.xiaomi.mina import MiNA


@pytest.fixture()
def config(tmp_path):
    return Config(path=tmp_path / "config.json")


# -- 配置 ------------------------------------------------------------------
def test_config_defaults(config):
    assert config.get("setup_completed") is False
    assert len(config.get("tasks")) >= 5
    assert config.get("xiaomi.device.device_id") == ""


def test_config_persist(tmp_path):
    p = tmp_path / "c.json"
    c = Config(path=p)
    c.set("power.default_delay", 30)
    assert Config(path=p).get("power.default_delay") == 30


def test_config_deep_set(config):
    config.set("bridge.poll_interval", 3.5)
    assert config.get("bridge.poll_interval") == 3.5
    assert config.get("bridge.tts_reply") is True  # 未覆盖的字段保留默认值


# -- 指令匹配 ---------------------------------------------------------------
@pytest.mark.parametrize(
    "query,action",
    [
        ("关机", "shutdown"),
        ("帮我关机", "shutdown"),
        ("取消关机", "cancel_shutdown"),
        ("重启电脑", "restart"),
        ("截个屏", "screenshot"),
        ("电脑状态", "report_status"),
        ("打开微信", "open_app"),
        ("关闭浏览器", "close_app"),
        ("唤醒客厅台式机", "wol"),
    ],
)
def test_match_actions(query, action):
    m = match(query, DEFAULT_TASKS)
    assert m is not None, f"未能匹配: {query}"
    assert m.rule["action"] == action


def test_match_captures_group():
    m = match("打开记事本", DEFAULT_TASKS)
    assert m is not None
    assert m.groups.get("app") == "记事本"


def test_match_no_result():
    assert match("今天天气怎么样", DEFAULT_TASKS) is None


def test_match_respects_disabled():
    tasks = [{"id": "x", "enabled": False, "patterns": ["关机"], "action": "shutdown"}]
    assert match("关机", tasks) is None


def test_all_default_actions_implemented():
    for rule in DEFAULT_TASKS:
        assert rule["action"] in ACTIONS, f"动作未实现: {rule['action']}"


def test_executor_unknown_action():
    executor = TaskExecutor(".")
    result = executor.execute(type("M", (), {"rule": {"action": "nope"}, "groups": {}})())
    assert result.ok is False


def test_format_reply(config):
    from miiotpcapi.tasks import format_reply
    rule = {"reply": "正在打开{app}"}
    assert format_reply(rule, {"app": "微信"}) == "正在打开微信"


# -- WOL -------------------------------------------------------------------
def test_normalize_mac():
    assert wol.normalize_mac("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert wol.normalize_mac("AA:BB:CC:DD:EE:FF") == "AA:BB:CC:DD:EE:FF"


def test_normalize_mac_invalid():
    with pytest.raises(ValueError):
        wol.normalize_mac("not-a-mac")


# -- 系统信息 / 监控 ---------------------------------------------------------
def test_sysinfo_summary():
    s = sysinfo.summary()
    for key in ("hostname", "os", "cpu_cores", "mem_total_gb", "uptime"):
        assert s[key] not in ("", None)
    assert s["cpu_cores"] >= 1


def test_status_text_is_speakable():
    text = sysinfo.status_text()
    assert "电脑" in text and len(text) > 10


def test_memory_and_disk():
    mem = monitor.memory()
    assert mem["total"] > 0
    assert 0 <= mem["percent"] <= 100
    disk = monitor.disk_usage("C:\\")
    assert disk["total"] > 0


def test_processes_listing():
    procs = monitor.processes()
    assert procs, "进程列表为空"
    assert {"pid", "name", "mem"} <= set(procs[0])


# -- 截图 -------------------------------------------------------------------
def test_screenshot_capture(tmp_path):
    p = screenshot.capture(tmp_path)
    assert p.exists()
    assert p.stat().st_size > 1000
    assert p.suffix == ".png"


# -- 小米模块 ---------------------------------------------------------------
def test_mi_account_not_logged_in():
    from miiotpcapi.xiaomi.account import MiAccount
    assert MiAccount("", "", token_path=None).is_logged_in() is False


def test_pick_speaker():
    devices = [{"deviceID": "", "hardware": "X"}, {"deviceID": "abc", "hardware": "L05B"}]
    assert MiNA.pick_speaker(devices)["deviceID"] == "abc"


def test_bridge_requires_account(config):
    from miiotpcapi.xiaomi.bridge import XiaoaiBridge
    bridge = XiaoaiBridge(config)
    with pytest.raises(RuntimeError, match="账号"):
        bridge._ensure_clients()


# -- 密码加密 ---------------------------------------------------------------
def test_password_roundtrip(config):
    from miiotpcapi import secure
    secret = "p@ssw0rd-中文-123"
    secure.save_password(config, secret)
    assert secret not in str(config.get("xiaomi.password_enc"))
    assert secure.load_password(config) == secret
    secure.clear_password(config)
    assert secure.load_password(config) == ""


# -- 米家（MIoT / MiIO）------------------------------------------------------
def test_miot_sign_structure():
    import base64
    from miiotpcapi.xiaomi.miot import sign_data, sign_nonce

    ssecurity = base64.b64encode(b"0123456789abcdef").decode()
    nonce = base64.b64encode(b"abcdefgh" + (0).to_bytes(4, "big")).decode()
    assert len(sign_nonce(ssecurity, nonce)) > 0

    signed = sign_data("/home/device_list", '{"a": 1}', ssecurity)
    assert set(signed) == {"data", "nonce", "signature"}
    assert signed["data"] == '{"a": 1}'
    # 签名应为合法的 base64
    base64.b64decode(signed["signature"])
    base64.b64decode(signed["nonce"])


def test_power_iid_convention():
    from miiotpcapi.xiaomi.miot import POWER_IID
    assert POWER_IID == (2, 1)


def test_channel_value_matches():
    from miiotpcapi.xiaomi.channel import value_matches

    assert value_matches(True, "1")
    assert value_matches(True, "on")
    assert value_matches(False, "0")
    assert value_matches(False, "off")
    assert value_matches(30, "30")
    assert value_matches("30", "30")
    assert not value_matches(2, "1")
    assert not value_matches(None, "1")


def test_qrlogin_module_contract():
    from miiotpcapi.xiaomi import qrlogin as qr

    login = qr.XiaomiQrLogin(sid="mijia")
    assert login.status == qr.WAITING
    # 未发起会话时轮询应返回失败而不是抛异常
    login.lp = ""
    assert login.poll() == qr.FAILED


def test_default_tasks_include_miot():
    from miiotpcapi.config import DEFAULT_TASKS
    from miiotpcapi.tasks import ACTIONS

    actions = {r["action"] for r in DEFAULT_TASKS}
    assert "miot_power" in actions
    assert "miot_power" in ACTIONS


def test_miot_power_requires_account(config):
    from miiotpcapi.tasks import MatchedTask, TaskExecutor

    executor = TaskExecutor()
    result = executor.execute(MatchedTask(
        rule={"action": "miot_power", "params": {"on": True}}, groups={"dev": "客厅灯"}))
    assert result.ok is False
    assert "小米账号" in result.reply


def test_default_mijia_channel_config(config):
    channel = config.get("mijia_channel")
    assert channel["enabled"] is False
    assert channel["props"][0]["siid"] == 2
    assert isinstance(channel["mappings"], list)
    assert isinstance(channel["reset"], list)


# -- 改名相关的向后兼容 -------------------------------------------------------
def test_config_dir_is_voxnode():
    from miiotpcapi.config import APP_DIR

    assert APP_DIR.name == ".voxnode"


def test_autostart_value_name():
    from miiotpcapi.core import autostart

    assert autostart._VALUE_NAME == "VoxNode"
    assert "MiPCBridge" in autostart._LEGACY_VALUE_NAMES


def test_secure_legacy_entropy_defined():
    from miiotpcapi import secure

    assert secure._entropy == b"VoxNode-v1"
    assert secure._legacy_entropy == b"MiPCBridge-v1"


# -- 指令通道：多属性组合编码 ---------------------------------------------------
def test_values_match_multi():
    from miiotpcapi.xiaomi.channel import values_key, values_match

    assert values_match([1, 0], "1,0")
    assert values_match([True, False], "on,off")
    assert values_match([30], "30")
    assert not values_match([1, 1], "1,0")
    assert not values_match([1], "1,0")      # 段数不符
    assert values_key([True, False, 30]) == "1,0,30"


def test_normalize_props_compat():
    from miiotpcapi.xiaomi.channel import normalize_props

    assert normalize_props({"props": [{"siid": 2, "piid": 1}]}) == [{"siid": 2, "piid": 1}]
    legacy = normalize_props({"prop": {"siid": 3, "piid": 1, "label": "x"}})
    assert legacy and legacy[0]["siid"] == 3
    assert normalize_props({}) == []


def test_config_migrates_legacy_channel(tmp_path):
    import json

    p = tmp_path / "c.json"
    p.write_text(json.dumps({
        "mijia_channel": {"prop": {"siid": 4, "piid": 1, "label": "键"}, "reset_value": 0}
    }), "utf-8")
    ch = Config(path=p).get("mijia_channel")
    assert ch["props"][0]["siid"] == 4
    assert "prop" not in ch
    assert ch["reset"][0]["value"] == 0
    assert "reset_value" not in ch


# -- 网页遥控台 ---------------------------------------------------------------
def test_remote_defaults(config):
    assert config.get("remote.enabled") is False
    assert config.get("remote.port") == 8765
    assert config.get("remote.token") == ""


def test_remote_server_end_to_end(tmp_path):
    import json
    import urllib.error
    import urllib.request

    from miiotpcapi.remote import RemoteServer
    from miiotpcapi.tasks import TaskExecutor

    cfg = Config(path=tmp_path / "c.json")
    cfg.set("remote.port", 0, save=False)      # 交给系统分配，避免测试机端口被别的程序占住
    srv = RemoteServer(cfg, lambda: TaskExecutor())
    assert srv.token, "应自动生成访问令牌"
    assert srv.start(), "遥控台应能在本机启动"
    try:
        base = f"http://127.0.0.1:{srv.port}"

        # 带令牌可读取状态
        with urllib.request.urlopen(f"{base}/api/status?t={srv.token}", timeout=5) as r:
            data = json.loads(r.read())
        assert data["ok"] is True and data["hostname"]

        # 不带令牌必须 401
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(f"{base}/api/status", timeout=5)
        assert err.value.code == 401

        # 错误令牌同样 401
        with pytest.raises(urllib.error.HTTPError) as err2:
            urllib.request.urlopen(f"{base}/api/status?t=wrong-token", timeout=5)
        assert err2.value.code == 401

        # 页面可渲染且令牌已注入
        with urllib.request.urlopen(f"{base}/?t={srv.token}", timeout=5) as r:
            page = r.read().decode("utf-8")
        assert "VoxNode" in page
        assert "__TOKEN__" not in page

        def post(action: str) -> int:
            req = urllib.request.Request(
                f"{base}/api/action?t={srv.token}",
                data=json.dumps({"action": action}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())["ok"]

        # 白名单外的动作被拒绝
        try:
            post("miot_power")
            raise AssertionError("白名单外的动作应被拒绝")
        except urllib.error.HTTPError as e:
            assert e.code == 403

        # 白名单内的动作可执行
        assert post("report_status") is True
    finally:
        srv.stop()


# -- 与 Android App 的接口契约 --------------------------------------------------
# 这里列出的动作与参数必须与 android/app/src/main/java/com/voxnode/remote/
# MainActivity.kt 中实际发送的请求保持一致，避免两端漂移。
ANDROID_APP_CALLS = [
    ("lock", {}),
    ("sleep", {}),
    ("cancel_shutdown", {}),
    ("hibernate", {}),
    ("signout", {}),
    ("restart", {"delay": 60}),
    ("shutdown", {"delay": 60}),
    ("screenshot", {}),
    ("report_status", {}),
    ("volume", {"op": "减"}),
    ("volume", {"op": "静音"}),
    ("volume", {"op": "加"}),
    ("media", {"op": "上一首"}),
    ("media", {"op": "暂停"}),
    ("media", {"op": "下一首"}),
    ("open_app", {"app": "记事本"}),
    ("wol", {"host": "客厅台式机"}),
]


def test_android_app_actions_are_allowed():
    from miiotpcapi.remote import ALLOWED_ACTIONS

    for action, _params in ANDROID_APP_CALLS:
        assert action in ALLOWED_ACTIONS, f"手机 App 用了白名单外的动作：{action}"


def test_android_app_action_params_are_understood():
    """校验 App 传的参数能被电脑端解析。

    注意：这里**绝不执行**关机 / 锁屏 / 休眠 / 注销等动作，
    只做「动作已注册 + 参数键正确 + 取值在允许集合内」的静态校验，
    避免跑测试时把开发机自己关掉。
    """
    from miiotpcapi.tasks import ACTIONS, MEDIA_OPS, VOLUME_OPS

    for action, params in ANDROID_APP_CALLS:
        assert action in ACTIONS, f"动作未实现：{action}"
        if action in ("shutdown", "restart"):
            assert "delay" in params
        elif action == "volume":
            assert params.get("op") in VOLUME_OPS, f"音量指令未支持：{params}"
        elif action == "media":
            assert params.get("op") in MEDIA_OPS, f"媒体指令未支持：{params}"
        elif action == "open_app":
            assert params.get("app")
        elif action == "wol":
            assert params.get("host")


def test_safe_actions_actually_run():
    """只跑完全无副作用的动作，确认执行链路通畅。"""
    from miiotpcapi.tasks import MatchedTask, TaskExecutor

    executor = TaskExecutor()
    result = executor.execute(MatchedTask(rule={"action": "report_status"}, groups={}))
    assert result.ok and result.reply


def test_android_app_endpoints_exist(tmp_path):
    """App 调用的三个读取接口都要能正常返回。"""
    import json
    import urllib.request

    from miiotpcapi.remote import RemoteServer
    from miiotpcapi.tasks import TaskExecutor

    cfg = Config(path=tmp_path / "c.json")
    cfg.set("remote.port", 0, save=False)
    srv = RemoteServer(cfg, lambda: TaskExecutor())
    assert srv.start()
    base = f"http://127.0.0.1:{srv.port}"
    try:
        for path, key in [("/api/status", "hostname"), ("/api/config", "apps")]:
            with urllib.request.urlopen(f"{base}{path}?t={srv.token}", timeout=5) as r:
                data = json.loads(r.read())
            assert key in data, f"{path} 缺少字段 {key}"
        # 截图接口：没有截图时返回 404、有则返回图片，两者都不能崩
        try:
            with urllib.request.urlopen(f"{base}/api/screenshot?t={srv.token}", timeout=5) as r:
                assert r.status == 200
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        srv.stop()


# -- PWA（把网页遥控台装成 App）--------------------------------------------------
def test_pwa_manifest_and_assets(tmp_path):
    import json
    import urllib.error
    import urllib.request

    from miiotpcapi.remote import RemoteServer
    from miiotpcapi.tasks import TaskExecutor

    cfg = Config(path=tmp_path / "c.json")
    cfg.set("remote.port", 0, save=False)
    srv = RemoteServer(cfg, lambda: TaskExecutor())
    assert srv.start()
    base = f"http://127.0.0.1:{srv.port}"
    try:
        # manifest：可安装所必需的字段
        with urllib.request.urlopen(
                f"{base}/manifest.webmanifest?t={srv.token}", timeout=5) as r:
            assert "manifest+json" in r.headers["Content-Type"]
            manifest = json.loads(r.read())
        assert manifest["name"] and manifest["short_name"]
        assert manifest["display"] == "standalone"
        assert manifest["start_url"].endswith(f"t={srv.token}")   # 从桌面图标启动即已鉴权
        sizes = {i["sizes"] for i in manifest["icons"]}
        assert {"192x192", "512x512"} <= sizes

        # 图标：必须是合法 PNG
        for path in ("/icon-192.png", "/icon-512.png"):
            with urllib.request.urlopen(f"{base}{path}?t={srv.token}", timeout=5) as r:
                data = r.read()
            assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path} 不是 PNG"
            assert len(data) > 300

        # Service Worker：必须注册 fetch 事件才算可安装
        with urllib.request.urlopen(f"{base}/sw.js", timeout=5) as r:
            sw = r.read().decode("utf-8")
            assert "javascript" in r.headers["Content-Type"]
        assert "addEventListener('fetch'" in sw

        # 页面里要有 PWA 相关的 meta / link 与 SW 注册
        with urllib.request.urlopen(f"{base}/?t={srv.token}", timeout=5) as r:
            page = r.read().decode("utf-8")
        for needle in ("manifest.webmanifest", "apple-touch-icon",
                       "apple-mobile-web-app-capable", "serviceWorker"):
            assert needle in page, f"页面缺少 {needle}"

        # 图标与 manifest 需要令牌，避免被局域网内其他人探测
        for path in ("/icon-192.png", "/manifest.webmanifest"):
            try:
                urllib.request.urlopen(f"{base}{path}", timeout=5)
                raise AssertionError(f"{path} 无令牌时应拒绝")
            except urllib.error.HTTPError as e:
                assert e.code == 401
    finally:
        srv.stop()


# -- 手机通过 MAC 唤醒电脑（WOL）------------------------------------------------
def test_broadcast_address_math():
    # /24
    assert sysinfo.broadcast_address("192.168.1.5", "255.255.255.0") == "192.168.1.255"
    # /16
    assert sysinfo.broadcast_address("10.1.2.3", "255.255.0.0") == "10.1.255.255"
    # 非整字节掩码也要算对
    assert sysinfo.broadcast_address("192.168.0.130", "255.255.255.128") == "192.168.0.255"
    # 信息不全或非法时返回空串，绝不抛异常
    assert sysinfo.broadcast_address("", "255.255.255.0") == ""
    assert sysinfo.broadcast_address("192.168.1.5", "") == ""
    assert sysinfo.broadcast_address("不是IP", "255.255.255.0") == ""


def test_interfaces_expose_wol_fields():
    for itf in sysinfo.interfaces():
        for key in ("name", "ipv4", "netmask", "broadcast", "mac", "up"):
            assert key in itf, f"网卡信息缺少 {key}"
        if itf["ipv4"] and itf["netmask"]:
            # 有 IP 就必须能算出广播地址，手机端才能定向唤醒
            assert itf["broadcast"]


def test_desktop_magic_packet_bytes(monkeypatch):
    """真实抓一次电脑端发出的魔术包，确认是标准的 102 字节格式。"""
    captured: dict = {}

    class FakeSocket:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def setsockopt(self, *args):
            pass

        def sendto(self, data, addr):
            captured["data"] = data
            captured["addr"] = addr

    monkeypatch.setattr(wol.socket, "socket", lambda *a, **k: FakeSocket())
    wol.send("aa-bb-cc-dd-ee-ff", "192.168.1.255", 9)

    data = captured["data"]
    assert len(data) == 102                          # 6 + 16 × 6
    assert data[:6] == b"\xff" * 6
    assert data[6:] == bytes.fromhex("AABBCCDDEEFF") * 16
    assert captured["addr"] == ("192.168.1.255", 9)


def test_client_config_carries_wol_targets_and_macs(config):
    """手机 App 靠这两组数据建立「本地唤醒设备」，字段名不能随意改。"""
    from miiotpcapi.remote import RemoteServer

    config.set("wol", [{
        "name": "客厅台式机", "mac": "AA:BB:CC:DD:EE:FF",
        "ip": "192.168.1.255", "port": 9,
    }])
    srv = RemoteServer(config, lambda: TaskExecutor())
    cfg = srv.client_config()

    assert cfg["host"]
    assert cfg["wol"] == ["客厅台式机"]              # 旧字段保持兼容
    assert cfg["wol_targets"] == [{
        "name": "客厅台式机", "mac": "AA:BB:CC:DD:EE:FF",
        "ip": "192.168.1.255", "port": 9,
    }]
    for nic in cfg["macs"]:
        for key in ("name", "ipv4", "mac", "broadcast"):
            assert key in nic


def test_client_config_tolerates_broken_wol_entries(config):
    """脏配置不能把接口带崩：缺名称的丢弃，端口非法回退到 9。"""
    from miiotpcapi.remote import RemoteServer

    config.set("wol", [
        {"mac": "AA:BB:CC:DD:EE:FF"},                                  # 没有名称 → 丢弃
        {"name": "坏端口", "mac": "11:22:33:44:55:66", "port": "abc"},
    ])
    srv = RemoteServer(config, lambda: TaskExecutor())
    targets = srv.client_config()["wol_targets"]

    assert [t["name"] for t in targets] == ["坏端口"]
    assert targets[0]["port"] == 9
    assert targets[0]["ip"] == "255.255.255.255"    # 缺省广播地址


def test_pwa_offers_local_mac_for_phone_wol(tmp_path):
    """网页遥控台要给出本机 MAC / 广播地址，供手机 App 唤醒这台电脑。"""
    import urllib.request

    from miiotpcapi.remote import RemoteServer

    cfg = Config(path=tmp_path / "c.json")
    cfg.set("remote.port", 0, save=False)
    srv = RemoteServer(cfg, lambda: TaskExecutor())
    assert srv.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{srv.port}/?t={srv.token}", timeout=5) as r:
            page = r.read().decode("utf-8")
        assert 'id="wolself"' in page, "页面缺少承载本机网卡信息的容器"
        assert "fillWolSelf" in page, "页面缺少渲染网卡信息的逻辑"
        assert "广播地址已复制" in page, "网卡信息应可点击复制"
        # 要如实说明：浏览器发不了魔术包，唤醒得靠手机 App
        assert "浏览器没法自己发 WOL 魔术包" in page
    finally:
        srv.stop()


# -- 与 Android App 的 WOL 契约 -----------------------------------------------
ANDROID_MAIN = Path(__file__).resolve().parents[1] / "android" / "app" / "src" / "main"


def _android_text(*parts: str) -> str:
    return ANDROID_MAIN.joinpath(*parts).read_text(encoding="utf-8")


def test_android_app_reads_the_config_fields_we_send(config):
    """App 解析的字段名必须与 client_config() 输出一致，否则唤醒列表会是空的。"""
    from miiotpcapi.remote import RemoteServer

    kotlin = _android_text("java", "com", "voxnode", "remote", "MainActivity.kt")
    keys = RemoteServer(config, lambda: TaskExecutor()).client_config()

    for field in ("wol_targets", "macs"):
        assert field in keys, f"client_config 不再返回 {field}"
        assert f'"{field}"' in kotlin, f"手机 App 没有读取 {field}"


def test_android_wol_does_not_depend_on_the_pc():
    """唤醒包必须由手机自己发出：电脑关机时它没法替手机转发。"""
    wol_kt = _android_text("java", "com", "voxnode", "remote", "Wol.kt")

    assert "DatagramSocket" in wol_kt, "手机端应自己开 UDP socket 发送魔术包"
    assert "broadcast = true" in wol_kt
    assert "255.255.255.255" in wol_kt

    manifest = _android_text("AndroidManifest.xml")
    assert "CHANGE_WIFI_MULTICAST_STATE" in manifest
    assert "ACCESS_WIFI_STATE" in manifest


def test_android_magic_packet_recipe_matches_desktop():
    """两端配方必须一致：6 字节 0xFF + MAC 重复 16 次，共 102 字节。"""
    wol_kt = _android_text("java", "com", "voxnode", "remote", "Wol.kt")

    assert "ByteArray(6 + 16 * 6)" in wol_kt
    assert "for (i in 0 until 6) packet[i] = 0xFF.toByte()" in wol_kt
    assert "for (round in 0 until 16)" in wol_kt
    assert "System.arraycopy(macBytes, 0, packet, 6 + round * 6, 6)" in wol_kt


def test_android_wol_targets_are_stored_locally():
    """唤醒列表要落在手机本地，电脑连不上时也能用。"""
    prefs = _android_text("java", "com", "voxnode", "remote", "Prefs.kt")

    assert "wol_targets" in prefs
    assert "saveWolTargets" in prefs and "wolTargets" in prefs
    assert "wol_imported" in prefs, "要记住自动加过的 MAC，用户删掉后不该复活"
    assert "clearServer" in prefs, "换服务器时不能连唤醒设备一起清掉"


def test_android_parses_both_targets_and_nics():
    api_side = _android_text("java", "com", "voxnode", "remote", "MainActivity.kt")
    assert "parseNics" in api_side
    assert "parseTargets" in api_side
    assert "importWolDevices" in api_side

    wol_kt = _android_text("java", "com", "voxnode", "remote", "Wol.kt")
    assert "parseNics" in wol_kt and "parseTargets" in wol_kt


# -- Android 资源一致性 ---------------------------------------------------------
ANDROID_RES = ANDROID_MAIN / "res"


def _string_names(relative: str) -> set[str]:
    import re

    text = ANDROID_RES.joinpath(*relative.split("/")).read_text(encoding="utf-8")
    return set(re.findall(r'<string name="([^"]+)"', text))


def test_android_string_resources_stay_in_sync():
    """默认文案（中文）与 en 翻译必须一一对应。

    少一条翻译只是回退到默认文案，但**多**一条会让 lint 以 ExtraTranslation
    把 release 构建直接判为失败（0.5.0 开发中真的踩过），所以这里守住两端完全对齐。
    """
    default = _string_names("values/strings.xml")
    english = _string_names("values-en/strings.xml")

    extra = sorted(english - default)
    missing = sorted(default - english)
    assert not extra, f"en 多出这些键，会让 release 构建失败：{extra}"
    assert not missing, f"en 缺少这些键的翻译：{missing}"


def test_android_wol_strings_exist_and_are_referenced():
    """新增的 WOL 文案必须真实存在，且确实被布局或代码引用（避免写了没用）。"""
    names = _string_names("values/strings.xml")
    for key in ("sec_wol_phone", "wol_hint_phone", "empty_wol_phone", "btn_add_wol"):
        assert key in names, f"缺少文案 {key}"

    layout = _android_text("res", "layout", "activity_main.xml")
    for key in ("sec_wol_phone", "wol_hint_phone", "empty_wol_phone", "btn_add_wol"):
        assert f"@string/{key}" in layout, f"布局没有引用 {key}"

    # 唤醒列表必须始终可见（不能藏在 controlPanel 里，否则电脑关机时点不到）
    panel_start = layout.index('android:id="@+id/controlPanel"')
    wol_start = layout.index('android:id="@+id/wolSection"')
    # wolSection 出现在 controlPanel 的闭合之后
    control_close = layout.rindex("</LinearLayout>", panel_start, wol_start)
    assert panel_start < control_close < wol_start, "wolSection 必须在 controlPanel 之外"



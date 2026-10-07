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
    assert channel["prop"]["siid"] == 2
    assert isinstance(channel["mappings"], list)


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

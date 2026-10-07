# 第三方开源声明 / Third-Party Notices

本项目 `miiotpcapi` / `MiPC Bridge` 在实现小米账号登录、小爱音箱（MiNA）通信协议时，
参考了以下开源项目的公开实现。这些项目均采用 **MIT 许可证**，
本项目据此保留其原始版权与许可声明，以符合 MIT 许可证「保留版权声明」的要求。

---

## 1. MiService

- 项目地址：https://github.com/Yonsm/MiService
- 作者：Yonsm
- 许可证：MIT License，Copyright (c) 2021-2026 Yonsm
- 本项目参考内容：
  - 小米账号登录流程（`serviceLogin` → `serviceLoginAuth2` → `serviceToken` 换取）
  - OTP（短信 / 邮箱）两步验证流程
  - MiNA 小爱音箱 API：设备列表、`text_to_speech`（TTS）、
    `nlp_result_get`（获取最近对话，用于语音指令轮询）
- 对应文件：`miiotpcapi/xiaomi/account.py`、`miiotpcapi/xiaomi/mina.py`

```
MIT License

Copyright (c) 2021-2026 Yonsm

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 2. xiaomusic

- 项目地址：https://github.com/hanxi/xiaomusic
- 作者：涵曦
- 许可证：MIT License，Copyright (c) 2023 涵曦
- 本项目参考内容：
  - MiNA 音箱 `player_set_volume` / `player_play_url` 等 ubus 调用方式
  - 部分机型需使用 `player_play_music` 的机型适配思路
- 对应文件：`miiotpcapi/xiaomi/mina.py`

```
MIT License

Copyright (c) 2023 涵曦

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 运行时依赖

| 依赖 | 许可证 |
|------|--------|
| PyQt6 | GPL-3.0（作为独立进程使用的动态链接不受其传染；如需闭源分发请评估或改用 PySide6/LGPL） |
| psutil | BSD-3-Clause |
| mss | MIT |
| requests | Apache-2.0 |

> 说明：PyQt6 以 GPL-3.0 授权，本项目自身代码为 MIT。若你计划闭源分发本软件，
> 请将 GUI 依赖替换为 LGPL 授权的 PySide6，或遵循 PyQt6 的 GPL 条款。详见 README「许可证」一节。

## 商标声明

「小米」「小爱同学」「米家」等为小米科技有限责任公司的商标。
本项目为个人开发的第三方工具，与小米公司无任何从属或合作关系。

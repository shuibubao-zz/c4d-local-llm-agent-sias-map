# student_C4D_教学说明

> 本文档的目标：**一个没有任何本地 AI 部署经验的人，照着从头到尾做一遍，能完整复现出
> 与本项目相同的结果**（一张可交互的 SIAS 周边地图 + 完整的 AI 对话日志）。
>
> 每一步都写明「做什么 → 命令 → 期望看到什么 → 如果不对怎么办」。
>
> 对应评审维度：**可复用性（15%）**

---

## 目录

- [0. 准备工作：你会用到什么](#0-准备工作你会用到什么)
- [1. 第一步：安装 Ollama](#1-第一步安装-ollama)
- [2. 第二步：拉取 Gemma 4 E4B 模型](#2-第二步拉取-gemma-4-e4b-模型)
- [3. 第三步：验证本地推理可用](#3-第三步验证本地推理可用)
- [4. 第四步：安装 Python 依赖](#4-第四步安装-python-依赖)
- [5. 第五步：环境自检（四项关键信息取证）](#5-第五步环境自检四项关键信息取证)
- [6. 第六步：生成地图](#6-第六步生成地图)
- [7. 第七步：多轮对话与容错测试（Level 3）](#7-第七步多轮对话与容错测试level-3)
- [8. 第八步：查看产物](#8-第八步查看产物)
- [9. 踩坑记录（真实遇到过的 6 个问题）](#9-踩坑记录真实遇到过的-6-个问题)
- [10. 复现检查清单](#10-复现检查清单)

---

## 0. 准备工作：你会用到什么

### 0.1 硬件要求

| 项目 | 最低 | 本项目实测环境 | 说明 |
|---|---|---|---|
| 内存 | 8 GB | **16 GB** | 8 GB 请改用 `gemma4:e2b` |
| 磁盘 | 15 GB 可用 | 55 GB 可用 | 模型约 6.2 GB |
| CPU | 近 5 年的 x86_64 | 13th Gen Intel Core i7-13620H | **无独显也能跑** |
| GPU | 不是必需 | 无（Intel UHD 核显） | 有 NVIDIA 独显会自动加速 |
| 系统 | Windows 10+ / macOS / Linux | Windows 11 家庭版 | 命令基本一致 |

> ⚠️ **重要预期管理**：本机是**纯 CPU 推理**，速度比显卡慢很多。
> 首轮请求包含模型加载时间（本项目实测约 37 秒），后续请求会明显变快。
> 请给足耐心，这不是程序卡死了。

### 0.2 需要的软件

| 软件 | 版本 | 用途 |
|---|---|---|
| Ollama | 0.40.2（或更新） | 本地大模型推理服务 |
| Python | 3.9 以上（本项目用 3.13） | 运行 Agent 代码 |
| pip | 随 Python | 安装依赖 |
| 浏览器 | Chrome / Edge | 查看生成的交互式地图 |

### 0.3 时间预算

| 步骤 | 耗时 |
|---|---|
| 安装 Ollama | 3~5 分钟 |
| 拉取模型（6.2 GB） | 视网速，10~60 分钟 |
| 安装 Python 依赖 | 1 分钟 |
| 环境自检（含首次模型加载） | 1~3 分钟 |
| 生成地图（一次完整推理） | 数分钟（CPU 推理） |
| **合计** | **约 20 分钟 ~ 1.5 小时** |

---

## 1. 第一步：安装 Ollama

### Windows

1. 打开 <https://ollama.com/download>
2. 下载 `OllamaSetup.exe`
3. 双击安装（一路下一步即可）
4. 安装完成后，Ollama 会**自动在后台运行**，任务栏出现小羊驼图标

验证安装：

```bash
ollama --version
```

**期望输出**（版本号可能更高，不影响）：

```
ollama version is 0.40.2
```

**如果提示 `'ollama' 不是内部或外部命令`**：

- 关掉终端重新打开一次（让 PATH 生效）
- 还不行就手动把安装目录（默认 `C:\Users\<你的用户名>\AppData\Local\Programs\Ollama`）
  加到系统环境变量 PATH 里

> 💡 **免安装方案（无需管理员权限）**
> 如果不想装到系统里，也可以下载官方 zip 包解压后直接运行：
> `ollama-windows-amd64.zip`（来自 <https://github.com/ollama/ollama/releases>），
> 解压后在该目录执行 `.\ollama.exe serve` 即可。本项目实际就是用这个方式部署的。

### macOS / Linux

```bash
# macOS
brew install ollama
# 或者从 https://ollama.com/download/mac 下载 dmg

# Linux（一条命令）
curl -fsSL https://ollama.com/install.sh | sh
```

### 启动服务（如果没有自动运行）

```bash
ollama serve
```

> 这个命令会**占住当前终端**，这是正常的 —— 它就是推理服务本体。
> 如果提示 `Error: listen tcp 127.0.0.1:11434: bind: address already in use`，
> 说明服务**已经在跑了**，不用管，直接进行下一步。

---

## 2. 第二步：拉取 Gemma 4 E4B 模型

### 2.1 执行拉取

```bash
ollama pull gemma4:e4b-it-q4_K_M
```

**这一串名字的含义**（四项关键信息里的前两项就在这里）：

| 片段 | 含义 |
|---|---|
| `gemma4` | 模型家族：Gemma 4 |
| `e4b` | 规格：E4B（effective 4.5B，适合 16 GB 笔记本） |
| `it` | instruction-tuned（指令微调版，能听懂"请生成 JSON"这类要求） |
| `q4_K_M` | **量化方式**：4-bit，K-quant，中等混合精度 |

### 2.2 期望看到什么

```
pulling manifest
pulling 370c2879f176: 100% ▕██████████████████▏ 5.5 GB
pulling 4cb21b935cd7: 100% ▕██████████████████▏ 991 MB
pulling 05612e54110f: 100% ▕██████████████████▏  98 MB
...
verifying sha256 digest
writing manifest
success
```

`success` 出现即下载完成，总共约 6.2 GB。

### 2.3 确认模型在本地

```bash
ollama list
```

**期望输出**：

```
NAME                       ID              SIZE      MODIFIED
gemma4:e4b-it-q4_K_M       xxxxxxxxxxxx    6.1 GB    x minutes ago
```

### 2.4 查看模型详情（中文能力/量化取证用）

```bash
ollama show gemma4:e4b-it-q4_K_M
```

会看到 `quantization: Q4_K_M`、`parameters: 7.5B`、`embedding length` 等信息 ——
**这是截图取证的好素材**。

### 2.5 如果下载很慢 / 卡住

| 现象 | 原因 | 处理 |
|---|---|---|
| 速度只有几十 KB/s | 网络出口受限 | 换个时间、换网络 |
| 一直卡在 0% | **可能被系统代理拦截** | 见 [§9.1 踩坑记录](#91-坑一系统代理会拦截-ollama-的模型下载) |
| 中途报 `digest mismatch` | 传输损坏 | 重跑 `ollama pull`，会自动续传 |

---

## 3. 第三步：验证本地推理可用

在写 Python 代码之前，**先用 curl 确认服务本身没问题**。这一步能把
「模型问题」和「代码问题」分开，排查效率高得多。

```bash
curl http://localhost:11434/v1/chat/completions ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"gemma4:e4b-it-q4_K_M\",\"messages\":[{\"role\":\"user\",\"content\":\"只回答两个字：你好\"}]}"
```

> Windows CMD 用 `^` 续行；PowerShell / bash 用 `\`。
> 也可以直接写成一行，避免转义麻烦。

**期望**：返回一段 JSON，其中 `choices[0].message.content` 里是模型的回答。

**如果返回 `{"error":"model ... not found"}`** → 模型 tag 写错了，用 `ollama list` 核对。

---

## 4. 第四步：安装 Python 依赖

### 4.1 进入技能包目录

```bash
cd student_C4D_agent-skill
```

### 4.2 安装依赖

```bash
pip install -r requirements.txt
```

**只装 4 个包**：

| 包 | 作用 |
|---|---|
| `requests` | 发 HTTP 请求给本地 Ollama（**注意：不是 openai SDK**） |
| `folium` | 生成交互式 HTML 地图（底层是 Leaflet.js） |
| `branca` / `xyzservices` | folium 的依赖，自动带上 |

> ⚠️ 本项目**不需要** `openai`、`dashscope`、`anthropic` 等任何云端大模型 SDK。
> 如果你看到教程让你 `pip install openai`，那是走云端 API 的路线，与本项目无关。

### 4.3 验证导入

```bash
python -c "import requests, folium; print('依赖 OK')"
```

### 4.4 可选：先跑离线自检

```bash
python selftest_offline.py
```

这个脚本**不需要模型、不需要联网**，会测试容错解析器、校验器、本地工具和地图渲染管线。

**期望输出结尾**：

```
  结果：29 项通过，0 项失败，共 29 项
  全部通过。
```

如果这一步就失败了，说明 Python 环境有问题，先解决它再往下走。

---

## 5. 第五步：环境自检（四项关键信息取证）

```bash
python check_env.py
```

这条命令把评审要求的**四项关键信息**一次性打印出来，
并且会**真实发一次最小推理请求**，实测出 tok/s。

### 期望输出（本项目实测值）

```
==========================================================================
  C4D 环境自检 —— 四项关键信息取证
==========================================================================
  检查时间：2026-10-09 18:21:04

==========================================================================
  [③ 设备信息]
==========================================================================
  操作系统    : Windows 11 (10.0.26200)
  Python      : 3.13.14
  CPU         : 13th Gen Intel(R) Core(TM) i7-13620H
  CPU 逻辑核  : 16
  内存        : 15.69 GB
  GPU         : Intel(R) UHD Graphics
  → 未检测到 NVIDIA 独显，本机走 **CPU 推理**（llama.cpp CPU backend）

==========================================================================
  [② 运行工具 Ollama]
==========================================================================
  ✓ Ollama 正在运行
  服务地址    : http://localhost:11434
  版本        : 0.40.2

==========================================================================
  [① 模型名称及版本]
==========================================================================
    - gemma4:e4b-it-q4_K_M                 6.13 GB   量化=Q4_K_M
  ✓ 目标模型已在本地：gemma4:e4b-it-q4_K_M
  模型家族    : gemma4
  参数规模    : 7.5B
  量化级别    : Q4_K_M
  模型格式    : gguf

==========================================================================
  [④ 推理速度实测 tok/s]
==========================================================================
  模型输出    : {"status":"ok","model":"gemma4"}
  总耗时      : 37.13 s（含首次加载）
  输出 token  : 63
  墙钟速度    : 1.70 tok/s
```

> 📸 **这就是截图素材** —— 四项关键信息（模型名、量化、Ollama、设备、tok/s）
> 全在这一屏里。请在此处截图，存到 `student_C4D_output_screenshots/`。

同时会把结果写入 `logs/env_report.json`，供文档引用。

---

## 6. 第六步：生成地图

### 6.1 运行主链路

```bash
python main.py
```

### 6.2 会发生什么

1. 打印横幅（含四项关键信息）
2. 预检：Ollama 活着吗？模型在本地吗？
3. **调用本地模型**生成地点 JSON
4. 容错解析 + 字段校验
5. 本地工具计算空间关系
6. 渲染 Folium 地图 → `student_C4D_map.html`
7. 写 AI 日志 → `student_C4D_AI日志.md`

### 6.3 期望输出（节选）

```
================================================================================
   C4D · 本地大模型 Agent 技能 —— SIAS University 交互式地图生成
--------------------------------------------------------------------------------
   模型    : gemma4:e4b-it-q4_K_M
   量化    : Q4_K_M
   运行工具: Ollama  ->  http://localhost:11434
   设备    : 13th Gen Intel(R) Core(TM) i7-13620H / 16 GB / Intel(R) UHD Graphics
   说明    : 不依赖任何云端 API，地点数据全部由本地 Gemma 4 模型生成
================================================================================

[预检] 检查本地 Ollama 服务与模型 ...
  ✓ Ollama v0.40.2 运行中 @ http://localhost:11434
  ✓ 模型 gemma4:e4b-it-q4_K_M 已在本地

==================================================================
[第 1 轮] 首轮-生成地点数据
==================================================================
  → 正在调用本地模型 gemma4:e4b-it-q4_K_M ...
  ← 模型返回 xxxx 字符，耗时 xx.xxs，输出 xxxx tokens，x.xx tok/s
  ← JSON 解析：成功（策略：策略1-直接解析）
  ← 字段校验：12/12 条完全合格
  ✓ 可用地点：12 个
...
[完成] 交互式地图已生成：.../student_C4D_map.html
```

### 6.4 打开地图

直接**双击** `student_C4D_map.html`，或拖进浏览器。

你应该看到：

- 一张以郑州西亚斯学院为中心的地图
- 左上角标题面板（含点位图例与数据来源说明）
- 地图上散布着带**编号的彩色圆点**（颜色代表类别）
- **点击任意圆点** → 弹出该点位的详情（中文名 + 英文名 + 描述 + 精确坐标）
- 右上角**图层控制**：可切换底图、可按类别显示/隐藏点位
- 左上角**全屏**按钮、左下角**测距**工具、右下角**鼠标经纬度**

> 📸 **这就是地图截图素材**。建议截两张：
> ① 全貌（能看到多个点位与标题面板）；② 某个 Marker 的弹窗展开状态。

---

## 7. 第七步：多轮对话与容错测试（Level 3）

### 7.1 交互式多轮对话

```bash
python main.py --interactive
```

进入后可以输入：

```
add 西亚斯学院体育馆
```

模型会在既有坐标系内**生成一个新点位并追加到地图**，地图会自动刷新。

```
modify 西亚斯学院图书馆 描述改为：藏书量最大的自习中心
```

模型会改写指定点位的描述并刷新地图。

其他指令：`list`（列出当前点位）、`save`（保存）、`quit`（退出）

### 7.2 容错对抗测试

```bash
python main.py --fault-test
```

这个模式**故意用一段诱导性提示词**，要求模型「先写思考过程 → 再给 JSON 代码块 → 最后总结」，
然后观察五级容错是否仍能救回 JSON。

**期望输出**：

```
✓ 容错成功：模型输出了额外文字，但解析器用「策略2-剥离```围栏」策略成功提取出 JSON。
```

这一条记录会完整写进 AI 日志，作为「解析异常容错处理」能力的**直接证据**。

### 7.3 一键演示（录屏用）

```bash
python main.py --demo
```

无人值守跑完「首轮生成 → 容错测试 → 多轮新增」全流程，适合录演示视频。

---

## 8. 第八步：查看产物

运行结束后，目录下会多出这些文件：

```
student_C4D_agent-skill/
├── student_C4D_map.html            ← 交互式地图（双击打开）
├── student_C4D_AI日志.md            ← 完整对话日志（强制交付物）
└── logs/
    ├── agent_calls.jsonl            ← 逐轮结构化日志（机器可读）
    ├── raw_model_outputs/           ← 每轮**模型原文**快照
    │   ├── round01_首轮-生成地点数据.txt
    │   └── ...
    └── env_report.json              ← 环境自检结果
```

### 验证日志里确实有原始输出

用记事本打开 `logs/raw_model_outputs/` 下的任意一个 txt，
里面应该是模型返回的**完整 JSON 文本**，包含中文描述。

### 验证 AI 日志完整

打开 `student_C4D_AI日志.md`，应该能看到：

- 每轮的 system 提示词原文
- 每轮的 user 提示词原文
- 每轮的**模型原始输出**（逐字）
- 每轮的 JSON 容错解析逐级诊断
- 每轮的耗时与 **tok/s**

---

## 9. 踩坑记录（真实遇到过的 6 个问题）

这一节是本教学说明最有价值的部分 —— 都是本项目在实际部署时**真实踩过的坑**。

### 9.1 坑一：系统代理会拦截 Ollama 的模型下载

**现象**：`ollama pull` 卡在 0%，或报 SSL 连接错误；但浏览器能正常访问网页。

**原因**：本机设置了 HTTP 代理（`HTTP_PROXY` / `HTTPS_PROXY` 环境变量），
而代理的放行列表里**没有包含** `registry.ollama.ai`（模型仓库）和
`release-assets.githubusercontent.com`（安装包主机），导致大文件下载被中断。

**解决**：启动 Ollama 前清空代理变量，或把仓库域名加入 `NO_PROXY`：

```bash
# 方式一：完全不走代理
export HTTP_PROXY= HTTPS_PROXY= http_proxy= https_proxy=
ollama serve

# 方式二：只让模型仓库走直连
export NO_PROXY="registry.ollama.ai,ollama.com,localhost,127.0.0.1"
ollama serve
```

Windows PowerShell：

```powershell
$env:HTTP_PROXY=""; $env:HTTPS_PROXY=""
$env:NO_PROXY="registry.ollama.ai,ollama.com,localhost,127.0.0.1"
ollama serve
```

**判断方法**：用 curl 分别测「走代理」和「不走代理」的耗时：

```bash
curl -s -o /dev/null -w "走代理 %{http_code} %{speed_download}B/s\n" -r 0-52428799 https://registry.ollama.ai/v2/...
curl --noproxy '*' -s -o /dev/null -w "直连 %{http_code} %{speed_download}B/s\n" -r 0-52428799 https://registry.ollama.ai/v2/...
```

### 9.2 坑二：首次请求特别慢，误以为卡死

**现象**：第一次调用模型等了 30~40 秒才有反应。

**原因**：Ollama 需要把 6 GB 的权重从磁盘加载进内存，这部分时间算在第一次请求里。

**解决**：正常现象，耐心等。之后同一模型的其他请求会快得多。
如果经常冷启动，可以设置 `OLLAMA_KEEP_ALIVE` 让模型常驻内存：

```bash
export OLLAMA_KEEP_ALIVE=30m
```

### 9.3 坑三：模型输出带了 ```json 代码块

**现象**：`json.loads()` 直接抛 `JSONDecodeError`。

**原因**：这是小模型的「习惯」—— 训练数据里 JSON 常被包在 Markdown 代码块里。

**解决**：本项目不靠"祈祷模型听话"，而是用 `json_repair.py` 的第 2 级策略
自动剥离围栏。**这正是容错模块存在的意义。**

### 9.4 坑四：内存不足导致速度暴跌

**现象**：推理速度从 5 tok/s 掉到 1 tok/s 以下，或者出现卡顿。

**原因**：16 GB 内存要同时装下 6 GB 模型 + KV cache + 操作系统 + 浏览器/IDE，
一旦触发磁盘交换（swap），速度会断崖式下跌。

**解决**：推理时关掉不必要的大内存程序（浏览器标签页、IDE）。
用 `check_env.py` 观察内存占用率。

### 9.5 坑五：中文描述变乱码

**现象**：控制台输出的中文变成 `????` 或方块。

**原因**：Windows 控制台默认编码不是 UTF-8。

**解决**：运行时显式指定 UTF-8：

```bash
# 方式一：设置环境变量
set PYTHONUTF8=1
python main.py

# 方式二：命令行加参数
python -X utf8 main.py

# 方式三：换 Windows Terminal（默认 UTF-8）
```

本项目所有文件读写都显式指定了 `encoding="utf-8"`，所以**文件产物不会乱码**，
只有控制台显示可能受影响。

### 9.6 坑六：`Address already in use`

**现象**：`ollama serve` 报端口 11434 被占用。

**原因**：Ollama 桌面版已经作为后台服务在运行了。

**解决**：不用再手动启动。直接用 `curl http://localhost:11434/api/version` 确认服务活着即可。

---

## 10. 复现检查清单

照抄完请逐条打勾，全部打勾说明完全复现成功：

### 环境

- [ ] `ollama --version` 有输出（版本 ≥ 0.40.2）
- [ ] `ollama list` 能看到 `gemma4:e4b-it-q4_K_M`（约 6.1 GB）
- [ ] `curl http://localhost:11434/api/version` 返回 `{"version":"..."}`
- [ ] `pip install -r requirements.txt` 无报错
- [ ] `python -c "import requests, folium"` 无报错

### 代码

- [ ] `python selftest_offline.py` → **29 项通过，0 项失败**
- [ ] `python check_env.py` → 打印出四项关键信息且实测出 tok/s
- [ ] `python main.py` → 输出 `[完成] 交互式地图已生成`

### 产物

- [ ] `student_C4D_map.html` 存在，且**双击能在浏览器打开**
- [ ] 地图上**能看到 ≥ 5 个点位**（本项目实测数量见验证报告）
- [ ] **点击任意点位能弹出详情**（中文名 + 英文名 + 描述 + 坐标）
- [ ] 地图能**缩放、拖动**
- [ ] `student_C4D_AI日志.md` 存在，且包含**模型原始输出**
- [ ] `logs/raw_model_outputs/` 下有逐轮原文快照
- [ ] `logs/env_report.json` 存在

### 诚实性检查（很重要的自检）

- [ ] 打开 `config.py`，确认**里面没有任何地点坐标数组**
- [ ] 打开 `logs/raw_model_outputs/*.txt`，确认**内容确实是模型生成的**（不是从代码里抄的）
- [ ] 确认所有点位描述是中文，且各不相同

---

## 附：一分钟极速复现（TL;DR）

```bash
# 前置：已安装 Ollama 并已 ollama serve

ollama pull gemma4:e4b-it-q4_K_M          # ① 拉模型（约 6.2 GB）
cd student_C4D_agent-skill                 # ② 进目录
pip install -r requirements.txt            # ③ 装依赖
python selftest_offline.py                 # ④ 离线自检（应 29/29）
python check_env.py                        # ⑤ 四项关键信息取证 → 截图
python main.py                             # ⑥ 生成地图
# 双击 student_C4D_map.html 查看结果 → 截图
```

# student_C4D_拿来说明

> 本文档回答四个问题：**用了什么**（库与工具）、**参考了什么**（资料）、
> **做了什么**（本轮已实现）、**没做什么**（本轮明确不做与边界）。
>
> 对应评审维度：技术实现（20%）· 产物完整性（15%）

---

## 1. 用了哪些库与工具

### 1.1 运行时（不属于 Python 依赖，但项目离不开）

| 名称 | 版本 | 用途 | 为什么选它 |
|---|---|---|---|
| **Ollama** | 0.40.2 | 本地大模型推理服务 | C4D 官方推荐；自带 **OpenAI 兼容 HTTP API**；一条命令拉起；跨平台；Windows 包内即 llama.cpp runner |
| **Gemma 4 E4B** | `e4b-it-q4_K_M` | 生成地点结构化数据 | 见 `方案设计.md` §4：16 GB 内存下的最优档，官方推荐入门档 |
| **Python** | 3.13.12 | 运行 Agent | 生态最全，Folium 是 Python 原生库 |
| **Windows 11** | Build 26200 | 操作系统 | 本机环境 |

### 1.2 Python 第三方依赖（完整清单见 `requirements.txt`）

| 包 | 本项目实测版本 | 用途 | 为什么选它 |
|---|---|---|---|
| **requests** | 2.34.2 | 向 `localhost:11434` 发 HTTP 请求 | 最通用的 HTTP 客户端；**不引入任何大模型 SDK**，保持"纯本地调用"的透明性 |
| **folium** | 0.20.0 | 生成交互式 HTML 地图 | C4D 官方推荐方案；底层是 Leaflet.js，产物是**单文件 HTML，双击即开**，无需任何前端工程 |
| **branca** | 0.8.2 | folium 的 HTML/JS 模板引擎 | folium 自动依赖 |
| **xyzservices** | 2026.9.1 | 瓦片图层元数据 | folium 自动依赖 |

### 1.3 Python 标准库（零依赖实现的部分）

| 模块 | 用途 |
|---|---|
| `json` | 解析模型输出的 JSON |
| `re` | 正则清洗（去围栏、去尾逗号、全角引号归一） |
| `math` | haversine 距离与方位角计算（本地工具，不引入 numpy） |
| `ctypes` | 免第三方库读取 Windows 内存信息 |
| `winreg` | 免第三方库读取 CPU 型号与 GPU 描述 |
| `subprocess` / `shutil` | 调用 `nvidia-smi`、检查磁盘空间 |
| `argparse` | 命令行参数（四种运行模式） |
| `html` | 弹窗内容转义，防止描述里的特殊字符破坏 HTML |
| `hashlib`（自检脚本用） | 产物完整性核对 |

> 💡 **设计取向**：能不用第三方库就不用。
> 硬件探测、距离计算、日志记录全部用标准库手写，只为让「换一台机器也能跑」更稳。

---

## 2. 参考了什么

### 2.1 官方与权威资料

| 资料 | 地址 | 用到了什么 |
|---|---|---|
| C4D 挑战主文档 | `materials/C4D.pdf`（本资料包内） | 四级任务要求、评审五维度权重、截图四项信息要求、最简示例代码 |
| C4D 补充说明 | `materials/C4D 补充说明.pdf` | 确认非计算机简化通道的内容（本项目**不走**该通道，仅作对照） |
| 结构化评分标准 | `rubric.json` | 五个评分维度与 red flag 清单 |
| Ollama 官方 Gemma 4 页面 | <https://ollama.com/library/gemma4> | 核对模型 tag 命名（`e4b-it-q4_K_M` 确实存在）、量化变体清单 |
| Ollama API 文档 | <https://github.com/ollama/ollama/blob/main/docs/api.md> | `/api/version`、`/api/tags`、`/api/show`、`/v1/chat/completions` 的字段定义 |
| Folium 文档 | <https://python-visualization.github.io/folium/> | `Map`、`CircleMarker`、`DivIcon`、`Popup`、`FeatureGroup`、`plugins.*` 用法 |
| Leaflet 文档 | <https://leafletjs.com/reference.html> | 底图图层、`bindPopup`、`L.control.layers` 行为 |
| Gemma 4 官方博客 | <https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/> | 四款模型的参数与内存需求表 |
| 维基百科 Sias University 条目 | <https://en.wikipedia.org/wiki/Sias_University> | 校园中心经纬度（34.402°N, 113.758°E，Osm 坐标） |
| 比格图地标库 | <http://www.bigemap.net/city-25916.html> | 交叉核对西亚斯学院在新郑的大致坐标范围 |

### 2.2 设计上参考的做法

| 参考对象 | 借鉴了什么 |
|---|---|
| C4D 主文档「最简示例（Python + Ollama + Folium）」 | 整体链路的骨架：本地模型出 JSON → Folium 打点 |
| 常见 Agent 工程实践（工具调用分离、能力分层） | 把「通信 / 能力 / 编排 / 渲染 / 留档」拆成独立模块，而不是一个巨型脚本 |
| OpenAI Chat Completions 消息格式 | messages 中 `system` 约束 + `user` 指令 + 多轮上下文的标准写法 |

### 2.3 关于坐标数据来源的诚实说明

本项目**没有调用任何第三方地图 API**（没有 geocoding、没有 POI 检索）。

- **地点坐标**：全部由**本地 Gemma 4 模型**在运行时生成
- **校园中心锚点**（代码中唯一写死的坐标）：来自维基百科该条目的 Osm 标注，
  用途是把模型输出框定在真实地理范围。C4D 主文档的最简示例同样采用固定中心点 +
  模型生成点位的做法
- **底图瓦片**：渲染时加载的公开瓦片服务（高德 / OSM），只提供底图，**不提供任何点位数据**

---

## 3. 本轮已经实现的功能

### 3.1 核心功能（Level 2 Silver —— 全部完成）

| # | 功能 | 实现位置 | 状态 |
|---|---|---|---|
| 1 | Python 调用 Ollama OpenAI 兼容接口访问本地 Gemma 4 | `ollama_client.py` | ✅ 已实测 |
| 2 | 系统提示词强制模型只返回合法 JSON 数组 | `config.SYSTEM_PROMPT` | ✅ 已实测 |
| 3 | 解析异常容错（五级递进策略） | `json_repair.py` | ✅ 29 项离线自检 + 真实对抗测试 |
| 4 | 交互式 Folium 地图（缩放/点击弹窗） | `map_generator.py` | ✅ 已实测 |
| 5 | ≥5 个标记点位，字段含 name / name_zh / latitude / longitude / description | `map_generator.py` | ✅ 已实测（实际数量见验证报告） |
| 6 | 输出 `student_C4D_map.html`，浏览器可直接打开 | `main.py` | ✅ 已实测 |
| 7 | 完整可运行 Python 源码 + 充分中文注释 | 全部模块 | ✅ |
| 8 | `requirements.txt` 写明全部第三方依赖 | `requirements.txt` | ✅ |
| 9 | 完整留存模型原始输出日志 | `logger.py` + `logs/` | ✅ |

### 3.2 加分功能（Level 3 Gold —— 部分完成）

| 扩展方向 | 要求 | 本项目状态 |
|---|---|---|
| **多轮对话 Agent** | 用户可交互式添加/修改地图标记 | ✅ **已完整实现并实跑**（`main.py --interactive`，含 `add` / `modify` / `list` / `save`） |
| **多工具调用** | 模型调用多个函数 | 🟡 **框架 + 3 个工具已实现**（haversine 距离、方位角、路线描述），3 个预留接口（weather / rating / vision），**接口已定义但未实现** |
| 代码生成 Agent | 模型自动生成代码并执行 | ❌ 本轮不做（安全考量：让模型生成并执行代码需要沙箱，超出本轮范围） |
| 视觉理解 | 校园照片识别并标注 | ❌ 本轮不做（需多模态适配，见 §4.3） |
| **多语言地图** | 中英文双语标注 | ✅ **已实现**（每个点位同时有 `name` 英文与 `name_zh` 中文，弹窗双语展示） |

### 3.3 工程附加项（超出 Level 2 要求的部分）

| 功能 | 说明 |
|---|---|
| 四模式命令行入口 | `main.py` / `--interactive` / `--fault-test` / `--demo` |
| 环境自检脚本 | `check_env.py` 一键打印四项关键信息 + 实测 tok/s |
| **零依赖离线自检** | `selftest_offline.py` 29 项测试，**不需要模型也不需要联网**，方便评审快速验证代码质量 |
| 容错对抗测试 | `--fault-test` 主动诱导模型输出脏文本，用真实数据证明容错有效 |
| tok/s 双口径统计 | 同时给「墙钟速度」与「纯推理速度」，避免用包含加载时间的数据误导 |
| 地图分类配色 + 图例 | 关键词规则判定类别（9 类），自动配色并生成图例面板 |
| 最近两点连线图层 | 用本地工具算出的结果作为演示图层（可开关） |
| 多底图切换 | 高德街道图 / 高德卫星图 / OpenStreetMap 三选一 |

---

## 4. 本轮明确不做的部分与原因

> 这一节是**主动划边界**。写清楚"不做什么"和"为什么不做"，
> 比假装什么都做了更负责任。

### 4.1 天气 / 评分工具（预留接口，未实现）

**不做原因**：这两个功能必须调用**外部网络 API**，与本项目「全部走本地」的
核心原则相冲突。C4D 只要求「预留扩展接口」，不要求完整实现全部多工具。

**如何扩展**：`tools.py` 中 `weather_query` / `rating_query` 的函数签名与返回协议
已定义好（`{"ok", "tool", "result", "error"}`），填入 API 调用即可，上层无需改动。

### 4.2 代码生成 Agent

**不做原因**：让模型生成代码并**执行**，需要一套沙箱隔离（否则有安全风险）。
本轮聚焦「结构化输出 + 地图」主链路，不引入执行任意代码的风险面。

### 4.3 视觉理解（照片识别并标注）

**不做原因**：Gemma 4 确实支持多模态，但把图像送进 Ollama 需要额外的
base64 编码与 `/api/generate` 的 `images` 字段适配，属于独立的一条链路。
本轮优先把文本 Agent 主链路做扎实。

**如何扩展**：`tools.py` 中 `image_recognition` 的接口已预留。

### 4.4 Level 4 相关内容

| 项目 | 为什么不做 |
|---|---|
| 模型对比报告（E2B / E4B / 26B / 31B） | 本机 16 GB 内存，26B / 31B **物理上跑不动**；且每个模型 5~20 GB，下载成本高 |
| 多设备适配（手机 / 台式机） | 本机只有这一台笔记本，无第二台设备 |
| 量化对比（Q4 vs Q8 vs FP16） | 需要额外下载 2~3 个量化版本（每个 10 GB+），磁盘与时间成本高 |
| Uncensored 模型对比 | 需要下载社区微调变体；且本项目的任务（生成校园地点数据）**不涉及任何内容安全触发场景**，做这个对比意义有限 |
| 性能调优（context / batch / GPU offload） | **本机无独立显卡**，GPU offload 无从谈起；CPU 侧的调优空间有限，收益不明显 |

### 4.5 其他已知限制

| 限制 | 说明 |
|---|---|
| **坐标是"合理近似"** | 模型生成的点位坐标不保证与真实建筑的测绘坐标一致。详见 `方案设计.md` §6.1 |
| 推理速度受硬件限制 | 纯 CPU 推理，速度显著低于带独显的机器（实测值见验证报告） |
| 地图有网才显示底图 | 生成的 HTML 是**离线可用**的，但底图瓦片从 CDN 拉取；断网时地图容器在、底图空白。如需完全离线，可换本地瓦片目录 |
| 输出稳定性 | 量化小模型偶发输出越界或脏文本。本项目用容错 + 校验兜住，但**不能保证 100% 一次成型**（这正是容错模块存在的意义） |

---

## 5. 项目文件与职责一览

```
student_C4D_agent-skill/
├── config.py              # 配置中枢：四项关键信息 + 提示词 + 地图锚点
├── ollama_client.py       # Ollama 接口封装（只打 localhost，含预检 + tok/s 统计）
├── json_repair.py         # 五级 JSON 容错解析 + 字段校验      ← Agent 能力核心
├── agent.py               # Agent 编排：结构化输出 / 多轮对话 / 工具调度
├── map_generator.py       # Folium 渲染：分类配色 / 图层 / 弹窗 / 图例
├── tools.py               # 本地工具 + 多工具预留接口
├── logger.py              # 原始对话日志（JSONL + 原文快照 + Markdown）
├── check_env.py           # 环境自检：四项关键信息 + tok/s 实测
├── selftest_offline.py    # 零依赖离线自检（29 项）
├── main.py                # 主入口（四模式）
├── run_demo.py            # 演示脚本（录屏用）
├── requirements.txt       # 依赖清单
└── logs/                  # 运行产物
```

> 补充：工作区根目录下还有一份 `student_C4D_全量合集.md`，
> 它把上面全部源码与全部 Markdown 文档的完整文本汇总在一个文件里，方便评审一次性通读；
> 内容是自动生成的，与工作区各文件逐字节一致，不是手写的新内容。

---

## 6. 一句话总结

这个项目用**一个本地小模型 + 三百行核心代码**，证明了：

> **不依赖任何云端 API，也能把自然语言指令变成一张真实可用的交互式地图。**

它的工程重点不在于"让模型输出 JSON"（那是提示词的事），
而在于**当模型不听话时，系统依然能给出可靠结果，并且每一步都留得下证据**。

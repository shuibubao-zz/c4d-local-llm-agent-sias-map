# student_C4D_agent-skill

> C4D 本地大模型 Agent 技能包 —— 用**本地 Gemma 4 模型**驱动 Agent，
> 生成 SIAS University（郑州西亚斯学院）周边的交互式地图。
> 全程不依赖任何云端 API。

---

## 1. 这是什么

一个可运行、可复现的本地 LLM Agent 技能包。它做三件事：

1. **接收自然语言指令**（"给我生成一个 SIAS University 周边的地图"）
2. **调用本地 Gemma 4 模型**（Ollama，`localhost:11434`）生成**结构化 JSON 地点数据**
3. **用 Python + Folium 渲染**成交互式 HTML 地图（`student_C4D_map.html`）

> ⚠️ 关键约束：**地点坐标全部由本地模型生成，代码里没有任何硬编码的地点数组。**
> 代码里唯一写死的坐标是「校园中心锚点」，它只用于把模型输出框定在真实地理范围内，
> 这一点与 C4D 官方任务书给出的最简示例做法一致。

---

## 2. 四项关键信息（评审硬性要求）

| 项目 | 值 |
|---|---|
| ① 模型名称及版本 | `gemma4:e4b-it-q4_K_M` |
| ② 量化方式 | `Q4_K_M`（4-bit K-quant Medium） |
| ③ 运行工具 | Ollama（本地 HTTP 服务 `http://localhost:11434`） |
| ④ 推理速度 tok/s | 运行时实测，见 `python check_env.py` 输出与 `logs/` |

设备：Dell Inspiron 16 Plus 7630 ｜ 13th Gen Intel Core i7-13620H（10C/16T）｜
16 GB RAM ｜ Intel UHD Graphics（核显，**纯 CPU 推理**）｜ Windows 11 Build 26200

---

## 3. 文件结构

```
student_C4D_agent-skill/
├── config.py            # 全局配置：模型名/量化/提示词/地图锚点（四项关键信息的单一事实源）
├── ollama_client.py     # Ollama OpenAI 兼容接口封装（只打 localhost，含预检与 tok/s 统计）
├── json_repair.py       # 五级递进 JSON 容错解析器  ← Agent 能力核心
├── agent.py             # Agent 核心：结构化输出 / 多轮对话 / 工具调用编排
├── map_generator.py     # Folium 交互式地图渲染（分类配色/图层/弹窗/图例）
├── tools.py             # 本地工具集 + 多工具调用预留接口（Level 3）
├── logger.py            # AI 对话原始日志记录（逐轮 system/user/原文/tok/s）
├── check_env.py         # 环境自检：四项关键信息一键取证 + 实测 tok/s
├── main.py              # 主入口（四种运行模式）
├── run_demo.py          # 演示脚本（供录屏，无人值守跑完全流程）
├── requirements.txt     # 第三方依赖清单
├── logs/                # 运行产物：原始对话 JSONL + 模型原文快照
└── README.md            # 本文件
```

---

## 4. 快速开始

```bash
# 1) 安装依赖
pip install -r requirements.txt

# 2) 安装并启动 Ollama（若尚未安装）
#    Windows: 从 https://ollama.com/download 下载安装
ollama serve

# 3) 拉取模型（约 6.2 GB）
ollama pull gemma4:e4b-it-q4_K_M

# 4) 环境自检（四项关键信息一键打印，可截图）
python check_env.py

# 5) 生成地图（Level 2 主链路）
python main.py
```

运行成功后会在当前目录生成 `student_C4D_map.html`，双击即可在浏览器打开。

---

## 5. 四种运行模式

| 命令 | 用途 | 对应级别 |
|---|---|---|
| `python main.py` | 一次性生成地图（主链路） | Level 2 |
| `python main.py --interactive` | 交互式多轮对话，可 add/modify 标记点 | **Level 3** |
| `python main.py --fault-test` | 容错对抗测试：故意诱导模型输出脏文本 | Level 2（Agent 能力） |
| `python main.py --demo` | 演示模式，一次跑完全流程 | 录屏用 |

---

## 6. Agent 能力说明（评审 25% 维度）

| 能力 | 实现位置 | 说明 |
|---|---|---|
| **系统提示词约束结构化输出** | `config.SYSTEM_PROMPT` | 明确要求"只输出 JSON 数组"，列出禁项（禁 markdown、禁解释） |
| **解析异常容错** | `json_repair.py` | 五级递进：直接解析 → 剥离代码块 → 括号配对提取 → 引号/尾逗号修复 → 对象提升/换行转义 |
| **字段与坐标校验** | `json_repair.validate_locations` | 只体检不补值；不合格条目剔除并留档，绝不编造坐标 |
| **多轮对话（记忆）** | `agent.py` 的 `self.history` | 保留 system + 历史 user/assistant，支持新增/修改标记点 |
| **工具调用** | `tools.py` + `agent.enrich_with_tools` | 本地 haversine 距离/方位角/路线描述，已真实调用；weather/rating/vision 预留接口 |
| **完整日志留档** | `logger.py` | 逐轮 system/user/模型原文/解析诊断/tok/s，落 JSONL + 原文快照 |

---

## 7. 常见问题

**Q：提示"无法连接 localhost:11434"？**
A：Ollama 服务没启动。执行 `ollama serve`（Windows 安装版通常开机自启）。

**Q：提示"本地未找到模型"？**
A：`ollama pull gemma4:e4b-it-q4_K_M`（约 6.2 GB，首次下载耐心等待）。

**Q：跑得慢？**
A：本机为纯 CPU 推理（无独立显卡）。首次调用包含模型加载时间，之后会明显变快。
可调 `config.MAX_TOKENS` 控制输出长度。

**Q：模型偶尔输出多余文字导致 JSON 失败？**
A：这正是 `json_repair.py` 存在的原因 —— 五级容错会尽力救回；
若仍失败，失败现场会完整保存在 `logs/raw_model_outputs/` 下，不会静默伪造数据。

---

## 8. 边界（本轮不做的部分）

* 不调用任何外部第三方地图 API 获取点位（点位只能来自本地模型）
* 不接入云端大模型 API（全程本地）
* 天气/评分/图像识别三个工具仅预留接口，未实现（原因见 `../student_C4D_拿来说明.md`）
* 手写公式识别、多设备适配、模型对比报告属于 Level 4，本轮不做

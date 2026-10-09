# -*- coding: utf-8 -*-
"""
config.py —— 全局配置与「四项关键信息」的单一事实源
==================================================

C4D 评审硬性要求：截图/录屏与文档中必须清晰标注以下四项信息。
本文件把这四项集中定义成一个地方，避免散落在多个文件里、互相不一致：

    ① 模型名称及版本  : MODEL_NAME  = gemma4:e4b-it-q4_K_M
    ② 量化方式        : QUANTIZATION = Q4_K_M
    ③ 运行工具        : RUNTIME_TOOL = Ollama (HTTP API: localhost:11434)
    ④ 推理速度 tok/s  : 运行期实测，见 logger.py 落盘的 logs/*.jsonl

⚠️ 关于「占位值」与「代码直接产出值」的区分（评审要求第 4 条）：
  * DEVICE_INFO 中标记 `source="auto"` 的字段由 check_env.py 在运行时自动探测并覆写，
    属于「代码直接产出」；标记 `source="manual"` 的字段需要本人在本机补全后才算数。
  * TOK_S_PLACEHOLDER 只是一个模板占位字符串，**真实数值必须以 Agent 实测日志为准**，
    不要在文档里把它当成结果。
  * 所有占位符统一使用 `<<...>>` 形式，便于用 grep 一次性找出还没补的部分。

作者：student
日期：2026-10
"""

import os

# ============================================================================
# 一、模型与运行时（四项关键信息之 ①②③）
# ============================================================================

# ① 模型名称及版本：Ollama 官方库 tag 形式，评审截图里要能看到这一串
MODEL_NAME = "gemma4:e4b-it-q4_K_M"

# 模型家族 / 规格速记（用于文档与日志标题）
MODEL_FAMILY = "Gemma 4 E4B (effective 4.5B)"
MODEL_PARAMS = "~4.5B effective"
MODEL_CONTEXT = "128K"

# ② 量化方式：与 Ollama tag 中的后缀一致（Q4_K_M = 4bit，K-quant，Medium 混合精度）
QUANTIZATION = "Q4_K_M"

# ③ 运行工具：Ollama，本地推理服务，默认监听 11434
RUNTIME_TOOL = "Ollama"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Ollama 的 OpenAI 兼容接口（任务书要求用这一条）
OPENAI_COMPAT_URL = f"{OLLAMA_HOST}/v1/chat/completions"
# Ollama 原生接口（用于拉取版本号、列出本地模型、看 tok/s 元数据）
NATIVE_CHAT_URL = f"{OLLAMA_HOST}/api/chat"
NATIVE_TAGS_URL = f"{OLLAMA_HOST}/api/tags"
NATIVE_VERSION_URL = f"{OLLAMA_HOST}/api/version"

# 推理参数
TEMPERATURE = 0.2          # 结构化输出任务要稳，温度压低
TOP_P = 0.9
MAX_TOKENS = 4096          # 输出 12 个点位 + 中文描述，需要足够空间
REQUEST_TIMEOUT = 600      # 纯 CPU 推理较慢，超时给足（秒）

# ============================================================================
# 二、设备信息（四项关键信息之 ③ 的载体）
# ----------------------------------------------------------------------------
# source="auto"   → check_env.py 运行时自动探测覆写
# source="manual" → 需要本人在本机补全
# ============================================================================

DEVICE_INFO = {
    "host_model":   {"value": "Dell Inspiron 16 Plus 7630",              "source": "auto"},
    "os":           {"value": "Windows 11 家庭版 中文版 (Build 26200)",   "source": "auto"},
    "cpu":          {"value": "13th Gen Intel(R) Core(TM) i7-13620H",     "source": "auto"},
    "cpu_cores":    {"value": "10 物理核 / 16 逻辑线程",                   "source": "auto"},
    "cpu_base_ghz": {"value": "2.40 GHz",                                 "source": "auto"},
    "ram":          {"value": "16 GB (可用 15.69 GB)",                    "source": "auto"},
    "gpu":          {"value": "Intel(R) UHD Graphics（核显，无独立显卡）", "source": "auto"},
    "gpu_vram":     {"value": "共享系统内存，无独立显存",                  "source": "auto"},
    "inference_dev": {"value": "CPU 推理（llama.cpp CPU backend）",        "source": "manual"},
    "disk_free_gb": {"value": "<<运行 check_env.py 后自动填>>",            "source": "auto"},
}

# 四项关键信息里唯一没法提前写死的一项：推理速度占位
# 真实值由 Agent 每次调用后写入 logs/*.jsonl 的 tokens_per_second 字段
TOK_S_PLACEHOLDER = "<<TOK_S：以 logs/ 实测值为准>>"
OLLAMA_VERSION_PLACEHOLDER = "<<OLLAMA_VERSION：以 check_env.py 输出为准>>"

# ============================================================================
# 三、地图与地理锚点
# ----------------------------------------------------------------------------
# 说明：中心锚点用于把模型的输出「框定」在真实地理范围内（任务书最简示例同样
# 采用固定中心点 + 模型生成点位的做法）。点位坐标本身全部来自本地模型输出，
# 代码中不存在任何硬编码的地点坐标数组。
# ============================================================================

# 郑州西亚斯学院（新郑）主校区中心 —— 依据维基百科 Osm 坐标 34.402N / 113.758E
MAP_CENTER = [34.4020, 113.7580]
# 缩放级别说明：14 个点位跨度约 450m × 690m，
# zoom=14 时整屏覆盖数公里、点会挤成一团；zoom=16 时视野约 1.5 km，点距清晰可辨
MAP_ZOOM_START = 16
CAMPUS_NAME_ZH = "郑州西亚斯学院"
CAMPUS_NAME_EN = "SIAS University"
CAMPUS_CITY = "河南省郑州市新郑市"

# 交付物文件名（严格对齐任务书的命名模板，占位姓名使用 student）
OUTPUT_MAP_HTML = "student_C4D_map.html"
AI_LOG_MARKDOWN = "student_C4D_AI日志.md"
RAW_LOG_DIR = "logs"                 # 原始模型返回（JSONL，逐轮一条）
RAW_JSON_DIR = "logs/raw_model_outputs"  # 每轮模型输出的原文快照


def workspace_root() -> str:
    """
    返回**交付物根目录**。

    场景：交付物要求所有文件并列在工作区目录下，而代码住在 `xxx/student_C4D_Agent技能/`。
    因此当本包目录名以 `_agent-skill` 结尾时，认为其父目录就是工作区根目录，
    生成的地图与 AI 日志会在两处各放一份：
      * 工作区根目录 —— 满足交付物并列摆放的要求
      * 技能包目录内 —— 保证技能包自身独立可跑、自包含

    若把本包单独拷到别处运行（目录名不以 `_agent-skill` 结尾），则退回为包内目录。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    if os.path.basename(here).endswith("_agent-skill") and parent:
        return parent
    return here


def publish_targets() -> list:
    """
    需要额外同步到工作区根目录的文件清单。
    返回 [(包内相对文件名, 根目录目标文件名), ...]
    """
    root = workspace_root()
    if os.path.abspath(root) == os.path.dirname(os.path.abspath(__file__)):
        return []   # 已经就在根目录，无需同步
    return [
        (OUTPUT_MAP_HTML, OUTPUT_MAP_HTML),
        (AI_LOG_MARKDOWN, AI_LOG_MARKDOWN),
    ]

# ============================================================================
# 四、提示词（Agent 结构化输出能力的关键）
# ============================================================================

# 用户指令：任务书原文要求的输入
INITIAL_USER_PROMPT = (
    "请给我生成一个 SIAS University（郑州西亚斯学院）周边的地图。\n"
    "学校位于河南省郑州市新郑市，校区中心坐标约为纬度 34.4020、经度 113.7580。\n"
    "请列出校园内及周边 12 个有意义的地点，覆盖教学楼、图书馆、宿舍区、体育场、"
    "校门、食堂、周边地标等类型。"
)

# 系统提示词：强制「只输出合法 JSON 数组」，是 Agent 结构化输出能力的核心约束
SYSTEM_PROMPT = """你是一个地理信息结构化助手（GeoJSON Agent）。你的唯一输出是一段合法的 JSON，不得包含任何其他文字。

【硬性输出规则】
1. 只输出一个 JSON 数组，数组的第一个字符必须是 `[`，最后一个字符必须是 `]`。
2. 禁止输出 Markdown 代码块标记（禁止 ```json 或 ```）。
3. 禁止输出任何解释、前言、后记、思考过程、注释文字。
4. 禁止在 JSON 之外使用换行说明；所有描述写在 JSON 字段内部。
5. 数字类型字段必须是纯数字（不加引号），字符串字段必须用双引号。

【数组元素结构】每个元素必须且只能包含这 5 个字段：
{
  "name":        英文名称（string），例如 "SIAS University Library"；
  "name_zh":     中文名称（string），例如 "西亚斯学院图书馆"；
  "latitude":    纬度（number，保留 6 位小数，范围 34.38 ~ 34.43）；
  "longitude":   经度（number，保留 6 位小数，范围 113.72 ~ 113.80）；
  "description": 点位描述（string，中文，40~80 字，说明该地点的用途或特点）。
}

【坐标约束】
所有 latitude / longitude 必须落在上述经纬度范围内，并且彼此之间不能完全重合。

【示例（仅示意格式，不要照抄内容）】
[{"name":"Example Gate","name_zh":"示例校门","latitude":34.402000,"longitude":113.758000,"description":"这是格式示例，实际请按用户要求生成真实地点。"}]

现在，严格按照用户要求生成 JSON 数组。再次强调：只输出 JSON，不要有任何多余字符。"""

# 多轮对话（Level 3）用的提示词模板
ADD_MARKER_PROMPT = (
    "请在上一步确定的坐标系范围内，新增 1 个地点：{location_name}。\n"
    "仍然只输出一个只含 1 个元素的 JSON 数组，字段结构与之前完全一致。"
)

MODIFY_MARKER_PROMPT = (
    "请修改地点「{old_name}」的信息：{new_info}\n"
    "只输出一个只含 1 个元素的 JSON 数组，字段结构与之前完全一致，"
    "name / name_zh 保持原样，只更新 description（必要时可微调坐标）。"
)

# 用于演示「容错能力」的对抗性提示词：故意诱导模型输出多余文字
# （评审点：模型输出夹带多余文字导致 JSON 解析失败时的容错逻辑）
FAULT_INJECTION_PROMPT = (
    "请用中文先写一段 50 字左右的思考过程，解释你为什么选这些地点；"
    "然后在后面附上 JSON 数组，并用 ```json 代码块包起来，"
    "最后再用一句话总结。请列出 3 个 SIAS University 周边地点。"
)

# ============================================================================
# 五、Level 3 预留：多工具调用开关
# ============================================================================

ENABLE_MULTI_TURN = True      # 交互式多轮对话（新增/修改标记点）
ENABLE_EXTRA_TOOLS = True     # 多工具调用框架（tools/ 目录，预留扩展）

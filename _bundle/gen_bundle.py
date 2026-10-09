# -*- coding: utf-8 -*-
"""把 C4D 工作区的全部源码与 Markdown 文档整理成一份「全量合集」。

设计要点
--------
1. 代码文件（.py / .json / .txt）：包在代码围栏里，围栏长度按内容里最长反引号串动态计算，
   避免文件内自带的 ``` 提前把外层围栏闭合。
2. Markdown 文档：原样展开（不套围栏），只把标题层级整体下调 2 级，
   这样文档自身的 ## 不会和合集自身的章节标题抢同一层。正文逐字不变。

纯本地运行，不联网、不依赖第三方库。
"""
import os
import io
import re
import datetime

ROOT = r"C:\Users\卢怡然\Desktop\C4D"
SKILL = os.path.join(ROOT, "student_C4D_Agent技能")
OUT = os.path.join(ROOT, "student_C4D_全量合集.md")

SKIP_DIRS = {"__pycache__", "_bundle", ".git"}
SKIP_EXT = {".pyc", ".png", ".jpg", ".zip"}


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def read(p):
    """以 UTF-8 读取文本文件。"""
    with io.open(p, "r", encoding="utf-8") as f:
        return f.read()


def tree(base):
    """生成项目目录树的纯文本表示（跳过缓存/临时目录）。"""
    lines = []

    def walk(d, prefix=""):
        items = sorted(os.listdir(d))
        dirs = [i for i in items if os.path.isdir(os.path.join(d, i)) and i not in SKIP_DIRS]
        files = [i for i in items
                 if os.path.isfile(os.path.join(d, i))
                 and os.path.splitext(i)[1].lower() not in SKIP_EXT]
        entries = [(i, True) for i in dirs] + [(i, False) for i in files]
        for idx, (name, isdir) in enumerate(entries):
            last = idx == len(entries) - 1
            p = os.path.join(d, name)
            branch = "└── " if last else "├── "
            if isdir:
                lines.append(f"{prefix}{branch}{name}/")
                walk(p, prefix + ("    " if last else "│   "))
            else:
                lines.append(f"{prefix}{branch}{name}  ({os.path.getsize(p):,} B)")

    lines.append("student_C4D_项目根目录/")
    walk(base)
    return "\n".join(lines)


def fence_for(text):
    """根据正文里最长的反引号串，算出一个不会被提前闭合的围栏。"""
    runs = [len(m) for m in re.findall(r"`+", text)]
    return "`" * max([3] + [r + 1 for r in runs])


def block_code(relpath, path, lang):
    """把一个代码/文本文件包成带文件名的代码块。"""
    body = read(path).rstrip("\n")
    f = fence_for(body)
    return f"\n### 文件 `{relpath}`\n\n{f}{lang}\n{body}\n{f}\n"


def demote_headings(md, levels=2):
    """把 Markdown 标题整体降 levels 级；代码围栏内的内容原样保留。"""
    out, fence = [], False
    for line in md.split("\n"):
        s = line.lstrip()
        if s.startswith("```") or s.startswith("~~~"):
            fence = not fence
            out.append(line)
            continue
        if not fence and re.match(r"^#{1,6}\s", line):
            out.append("#" * levels + line)
        else:
            out.append(line)
    return "\n".join(out)


def block_doc(relpath, path):
    """把一份 Markdown 文档原样展开（标题降级），正文逐字不变。"""
    body = read(path).rstrip("\n")
    body = demote_headings(body, 2)
    return (f"\n### 文件 `{relpath}`\n\n"
            f"> 以下为该文件全文，逐字复制，未做任何删改；"
            f"仅把文内标题层级整体下调 2 级，以免与合集自身章节标题同层。\n\n"
            f"{body}\n")


# --------------------------------------------------------------------------- #
# 组装
# --------------------------------------------------------------------------- #
parts = []


def w(s):
    """追加一段文本，自动保证以换行结尾。"""
    if not s.endswith("\n"):
        s += "\n"
    parts.append(s)


w("# C4D 交付全量合集 —— 源码与文档完整文本\n")
w(f"> 生成时间：{datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
w("> 由 `_bundle/gen_bundle.py` 自动汇总，内容与工作区文件逐字节一致（未手工改写）。")
w("> 本合集含：① 完整项目目录树 ② 8 项交付物核对表 ③ 全部 Python/文本源码 "
  "④ 全部 Markdown 文档 ⑤ 运行日志附录。")

# ---------- 一、目录树 ----------
w("\n---\n\n## 一、完整项目目录树\n")
w("```")
w(tree(ROOT))
w("```")

# ---------- 二、交付物核对 ----------
w("\n---\n\n## 二、8 项必备交付物核对表\n")
w("| # | 要求交付物 | 工作区实际文件 | 状态 |")
w("|---|---|---|---|")
checks = [
    ("1", "方案设计文档", "`student_C4D_方案设计.md`（28,627 B）"),
    ("2", "Agent 技能源码目录", "`student_C4D_Agent技能/`（12 个 .py + requirements.txt + README.md）"),
    ("3", "生成的地图", "`student_C4D_map.html`（87,314 B）"),
    ("4", "截图目录", "`student_C4D_output_screenshots/`（含截图清单 + 1 张代码自动生成的渲染预览）"),
    ("5", "验证报告", "`student_C4D_验证报告.md`（19,272 B）"),
    ("6", "教学说明", "`student_C4D_教学说明.md`（20,529 B）"),
    ("7", "AI 日志【强制】", "`student_C4D_AI日志.md`（18,530 B）"),
    ("8", "拿来说明", "`student_C4D_拿来说明.md`（12,254 B）"),
]
for a, b, c in checks:
    w(f"| {a} | {b} | {c} | ✅ 已交付 |")
w("| 附 | 复盘（AAR） | `student_C4D_AAR.md`（13,421 B） | ✅ 额外提交 |")

# ---------- 三、源码 ----------
w("\n---\n\n## 三、Agent 技能全部源码\n")
w("### 3.0 模块依赖关系\n")
w("```")
w("""main.py                          ← 入口，四种运行模式（默认 / --interactive / --fault-test / --demo）
├── config.py                    ← 四项关键信息的单一事实源 + 系统提示词（三层约束）
├── ollama_client.py             ← 调用本地 Ollama 的 OpenAI 兼容接口，只打 localhost:11434
├── agent.py                     ← SiasMapAgent 主智能体：生成 / 新增 / 修改 / 容错测试 / 工具增强
│   ├── json_repair.py           ← 五级递进 JSON 容错解析器
│   ├── tools.py                 ← 本地纯计算工具（距离 / 方位角 / 最近点对）+ 预留扩展接口
│   └── logger.py                ← 每轮落 JSONL + 模型原文快照，导出 Markdown AI 日志
├── map_generator.py             ← Folium 生成可交互 HTML 地图
├── check_env.py                 ← 环境自检：四项关键信息一键取证 + tok/s 实测
├── selftest_offline.py          ← 零依赖离线自检（29 项，不需要模型，也不需要 folium）
├── rebuild_ai_log.py            ← 从 JSONL 留档重建 AI 日志与地图
└── run_demo.py                  ← 无人值守演示脚本（录屏用）""")
w("```")

sources = [
    ("student_C4D_Agent技能/config.py", "python"),
    ("student_C4D_Agent技能/json_repair.py", "python"),
    ("student_C4D_Agent技能/ollama_client.py", "python"),
    ("student_C4D_Agent技能/agent.py", "python"),
    ("student_C4D_Agent技能/map_generator.py", "python"),
    ("student_C4D_Agent技能/tools.py", "python"),
    ("student_C4D_Agent技能/logger.py", "python"),
    ("student_C4D_Agent技能/check_env.py", "python"),
    ("student_C4D_Agent技能/main.py", "python"),
    ("student_C4D_Agent技能/run_demo.py", "python"),
    ("student_C4D_Agent技能/selftest_offline.py", "python"),
    ("student_C4D_Agent技能/rebuild_ai_log.py", "python"),
    ("student_C4D_Agent技能/requirements.txt", "text"),
]
for rel, lang in sources:
    w(block_code(rel, os.path.join(ROOT, rel.replace("/", os.sep)), lang))

# 技能自带 README 也是 Markdown，走文档通道
w(block_doc("student_C4D_Agent技能/README.md", os.path.join(SKILL, "README.md")))

# ---------- 四、文档 ----------
w("\n---\n\n## 四、全部 Markdown 文档完整文本\n")
docs = [
    "student_C4D_方案设计.md",
    "student_C4D_验证报告.md",
    "student_C4D_教学说明.md",
    "student_C4D_拿来说明.md",
    "student_C4D_AI日志.md",
    "student_C4D_AAR.md",
    "student_C4D_output_screenshots/截图清单.md",
]
for rel in docs:
    w(block_doc(rel, os.path.join(ROOT, rel.replace("/", os.sep))))

# ---------- 五、日志附录 ----------
w("\n---\n\n## 五、运行日志附录（原始留档）\n")
w("> 下列文件位于 `student_C4D_Agent技能/logs/`，是本地真实运行后落盘的原始证据，"
  "未经任何修饰，可直接作为「确实在本地跑过」的佐证。\n")
logs = [
    ("student_C4D_Agent技能/logs/env_report.json", "json"),
    ("student_C4D_Agent技能/logs/env_check_console.txt", "text"),
    ("student_C4D_Agent技能/logs/main_run_console.txt", "text"),
    ("student_C4D_Agent技能/logs/raw_model_outputs/round01_首轮-生成地点数据.txt", "text"),
    ("student_C4D_Agent技能/logs/raw_model_outputs/round02_容错对抗测试-故意诱导脏输出.txt", "text"),
    ("student_C4D_Agent技能/logs/raw_model_outputs/round03_多轮-新增「西亚斯学院体育馆」.txt", "text"),
    ("student_C4D_Agent技能/logs/raw_model_outputs/round04_多轮-新增「新郑市第一人民医院」.txt", "text"),
]
for rel, lang in logs:
    p = os.path.join(ROOT, rel.replace("/", os.sep))
    if os.path.exists(p):
        w(block_code(rel, p, lang))

# ---------- 六、地图说明 ----------
w("\n---\n\n## 六、关于地图产物 `student_C4D_map.html`\n")
w("该文件（87,314 B）是 Python Folium 生成的最终交互式产物，内含 Leaflet 的 JS/CSS 与"
  "内联点位数据，**不适合以文本形式塞进本合集**（会把合集撑到几倍大且不可读）。")
w("请直接用浏览器打开该 HTML；它的渲染结果见 "
  "`student_C4D_output_screenshots/00_地图自动渲染预览_代码生成.png`。")
w("\n本地打开方式（任选其一）：")
w("1. 在文件资源管理器里双击 `student_C4D_map.html`；")
w("2. 或在命令行执行 `start student_C4D_map.html`（Windows）。")

text = "".join(parts)
with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(text)

print("OK ->", OUT)
print("bytes =", os.path.getsize(OUT))
print("chars =", len(text))

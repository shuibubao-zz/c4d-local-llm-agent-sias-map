# -*- coding: utf-8 -*-
"""
rebuild_ai_log.py —— 从原始日志重建 AI 日志文档（无需重新调用模型）
==================================================================

为什么需要它？
--------------
`student_C4D_AI日志.md` 是本项目的**强制交付物**。它由 `main.py` 在运行时生成，
内容是「本次会话的逐轮记录」。

但有时会遇到这些情况：
  * 日志文档的排版/措辞想改一改，但又不想为了改排版把模型重新跑一遍（CPU 推理很慢）
  * 想把**多次运行**的记录合并成一份完整的日志
  * 只保留了 `logs/agent_calls.jsonl`，Markdown 被误删了

这个脚本就是干这个的：**读 `logs/agent_calls.jsonl`，重新渲染出 Markdown**。
它不碰模型、不联网、不需要 Ollama。

用法：
    python rebuild_ai_log.py                    # 覆盖生成 student_C4D_AI日志.md
    python rebuild_ai_log.py --out custom.md    # 指定输出文件
    python rebuild_ai_log.py --append a.jsonl --append b.jsonl   # 合并多份日志

作者：student
日期：2026-10
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config                      # noqa: E402
import json_repair                 # noqa: E402
from logger import AgentLogger     # noqa: E402


def load_turns(paths):
    """从若干 jsonl 文件里读出全部轮次记录。"""
    turns = []
    for p in paths:
        if not os.path.exists(p):
            print(f"  ! 跳过不存在的文件：{p}")
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    turns.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"  ! 跳过无法解析的行（前 60 字符）：{line[:60]}")
    # 重新编号，保证跨文件合并后轮次连续
    for i, t in enumerate(turns, start=1):
        t["round"] = i
    return turns


def collect_locations(turns):
    """从各轮原始输出里重新解析出正式地图点位（排除容错测试轮）。"""
    locs = []
    for t in turns:
        if "容错" in t.get("phase", ""):
            continue
        if not t.get("parsed_ok"):
            continue
        data, _ = json_repair.parse_model_json(t.get("raw_model_output", ""))
        if not data:
            continue
        if isinstance(data, dict):
            data = [data]
        good, _ = json_repair.drop_invalid_records(data)
        locs.extend(good)
    # 去重
    seen, uniq = set(), []
    for loc in locs:
        key = (loc.get("name_zh"), loc.get("name"))
        if key not in seen:
            seen.add(key)
            uniq.append(loc)
    return uniq


def build_header(turns, locations, entry: str) -> str:
    """构造日志开头的「人工撰写说明」部分（与 main.py 保持一致的结构）。"""
    speeds = [t["metrics"].get("tokens_per_second", 0) for t in turns
              if t.get("metrics", {}).get("tokens_per_second")]
    ok = sum(1 for t in turns if t.get("parsed_ok"))
    elapsed = [t["metrics"].get("elapsed_time", 0) for t in turns if t.get("metrics")]

    lines = []
    lines.append("## 1. 本次运行说明（人工撰写）\n")
    lines.append(f"- **运行时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}（文档重建时间）")
    lines.append(f"- **重建来源**：`logs/agent_calls.jsonl`（`rebuild_ai_log.py` 生成）")
    lines.append(f"- **原始运行入口**：{entry}")
    lines.append(f"- **模型**：`{config.MODEL_NAME}`（Ollama tag，量化 {config.QUANTIZATION}）")
    lines.append(f"- **接口**：Ollama OpenAI 兼容端点 `{config.OPENAI_COMPAT_URL}`（本地）")
    lines.append(f"- **总轮次**：{len(turns)}")
    lines.append(f"- **解析成功轮次**：{ok}/{len(turns)}"
                 f"（{round(ok/len(turns)*100,1) if turns else 0}%）")
    if speeds:
        lines.append(f"- **推理速度**：{min(speeds):.2f} ~ {max(speeds):.2f} tok/s，"
                     f"均值 {sum(speeds)/len(speeds):.2f} tok/s")
    if elapsed:
        lines.append(f"- **模型总推理耗时**：{sum(elapsed):.2f} s")
    lines.append(f"- **正式地图点位**：{len(locations)} 个")
    lines.append("")
    lines.append("### 1.1 本轮生成的地点清单（原文来自模型输出）\n")
    lines.append("| # | name_zh | name | latitude | longitude |")
    lines.append("|---|---|---|---|---|")
    for i, loc in enumerate(locations, 1):
        lines.append(f"| {i} | {loc.get('name_zh')} | {loc.get('name')} | "
                     f"{loc.get('latitude')} | {loc.get('longitude')} |")
    lines.append("")
    lines.append("### 1.2 各轮次概览\n")
    lines.append("| 轮次 | 用途 | 耗时(s) | 输出 tokens | tok/s | 解析策略 | 结果 |")
    lines.append("|---|---|---|---|---|---|---|")
    for t in turns:
        m = t.get("metrics") or {}
        lines.append(f"| {t['round']} | {t.get('phase')} | "
                     f"{m.get('elapsed_time', 0):.2f} | {m.get('completion_tokens', 0)} | "
                     f"{m.get('tokens_per_second', 0):.2f} | "
                     f"{m.get('json_strategy_hit') or '—'} | "
                     f"{'成功' if t.get('parsed_ok') else '失败'} |")
    lines.append("")
    lines.append("\n---\n")
    lines.append("## 2. 逐轮原始对话记录（机器留档，未删改）\n")
    lines.append("> 以下为脚本自动写入的原始日志。`模型原始输出` 一栏是模型的**逐字原文**，\n"
                 "> 包含失败现场，未做任何美化。\n")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="从 jsonl 重建 AI 日志 Markdown")
    ap.add_argument("--jsonl", default=os.path.join(config.RAW_LOG_DIR, "agent_calls.jsonl"),
                    help="日志来源（默认 logs/agent_calls.jsonl）")
    ap.add_argument("--append", action="append", default=[],
                    help="额外追加的 jsonl 文件（可多次指定，用于合并多次运行）")
    ap.add_argument("--out", default=config.AI_LOG_MARKDOWN, help="输出 Markdown 路径")
    ap.add_argument("--map", action="store_true",
                    help="同时用同一批地点数据重建 student_C4D_map.html（保证日志与地图一致）")
    ap.add_argument("--entry", default="python main.py（Level 2 主链路）",
                    help="原始运行入口描述")
    args = ap.parse_args()

    paths = [args.jsonl] + args.append
    print(f"读取日志：{paths}")
    turns = load_turns(paths)
    if not turns:
        print("✗ 没有读到任何轮次记录，无法重建。")
        return 1
    print(f"  共读到 {len(turns)} 轮记录")

    locations = collect_locations(turns)
    print(f"  重新解析出 {len(locations)} 个正式地图点位（已排除容错测试轮）")

    logger = AgentLogger(
        log_dir=config.RAW_LOG_DIR,
        model_name=config.MODEL_NAME,
        runtime_tool=f"{config.RUNTIME_TOOL} ({config.OLLAMA_HOST})",
        quantization=config.QUANTIZATION,
        device_brief=(f"{config.DEVICE_INFO['cpu']['value']} / "
                      f"{config.DEVICE_INFO['ram']['value']} / "
                      f"{config.DEVICE_INFO['gpu']['value']}"),
    )
    logger.turns = turns

    header = build_header(turns, locations, args.entry)
    md = logger.render_markdown(extra_header=header)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"✓ 已重建：{args.out}（{len(md)} 字符）")

    # 顺便用同一批地点数据重建地图（保证「日志 ↔ 地图」内容严格一致）
    if args.map:
        import map_generator
        out_map = map_generator.generate_map(
            locations,
            output_path=config.OUTPUT_MAP_HTML,
            subtitle=f"模型 {config.MODEL_NAME}（{config.QUANTIZATION}）· "
                     f"Ollama · 纯本地推理 · 数据由本地模型生成",
        )
        st = map_generator.map_stats(locations)
        print(f"✓ 已重建地图：{out_map}（{st['markers']} 个点位，类别 {st['categories']}）")

    # 同步到工作区根目录
    root = config.workspace_root()
    here = os.path.dirname(os.path.abspath(__file__))
    if os.path.abspath(root) != here:
        import shutil
        for name in (os.path.basename(args.out),
                     config.OUTPUT_MAP_HTML if args.map else None):
            if not name:
                continue
            src = os.path.join(here, name)
            if os.path.exists(src):
                dst = os.path.join(root, name)
                shutil.copyfile(src, dst)
                print(f"✓ 已同步到工作区根目录：{dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

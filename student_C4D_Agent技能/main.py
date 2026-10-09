# -*- coding: utf-8 -*-
"""
main.py —— 项目主入口
====================

三种运行模式（对齐 C4D 的 Level 2 与 Level 3）：

    python main.py                     # 默认：一次性生成地图（Level 2 主链路）
    python main.py --interactive       # 交互式多轮对话（Level 3 加分）
    python main.py --fault-test        # 容错对抗测试（证明解析容错能力）
    python main.py --demo              # 演示模式：跑完 1+2+3 全流程（供录屏）

每一步的完整对话（system / user / 模型原文 / 解析诊断 / tok/s）都会自动写入
`logs/agent_calls.jsonl` 与 `logs/raw_model_outputs/*.txt`，
最后由代码汇总成 `student_C4D_AI日志.md`。

作者：student
日期：2026-10
"""

import argparse
import os
import shutil
import sys
from datetime import datetime

# 让脚本无论从哪里被调用都能 import 同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config                     # noqa: E402
import map_generator              # noqa: E402
from agent import SiasMapAgent    # noqa: E402
from ollama_client import (ModelNotPulledError, OllamaError,  # noqa: E402
                           OllamaNotRunningError)

BANNER = r"""
================================================================================
   C4D · 本地大模型 Agent 技能 —— SIAS University 交互式地图生成
--------------------------------------------------------------------------------
   模型    : {model}
   量化    : {quant}
   运行工具: {tool}  ->  {host}
   设备    : {cpu} / {ram} / {gpu}
   说明    : 不依赖任何云端 API，地点数据全部由本地 Gemma 4 模型生成
================================================================================
"""


def publish_to_workspace() -> None:
    """
    把地图与 AI 日志同步一份到工作区根目录。

    原因：C4D 的交付物要求所有文件并列摆在工作区目录下，
    而代码住在 `student_C4D_Agent技能/` 子目录里。
    这里做一次同步，两份都在，既满足交付要求，也保证技能包自包含。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    root = config.workspace_root()
    if os.path.abspath(root) == here:
        return
    for fname in (config.OUTPUT_MAP_HTML, config.AI_LOG_MARKDOWN):
        src = os.path.join(here, fname)
        dst = os.path.join(root, fname)
        if os.path.exists(src):
            try:
                shutil.copyfile(src, dst)
            except Exception as e:  # noqa: BLE001
                print(f"  (同步到工作区根目录失败：{e})")
    print(f"  → 已同步交付物到工作区根目录：{root}")


def print_banner() -> None:
    d = config.DEVICE_INFO
    print(BANNER.format(
        model=config.MODEL_NAME,
        quant=config.QUANTIZATION,
        tool=config.RUNTIME_TOOL,
        host=config.OLLAMA_HOST,
        cpu=d["cpu"]["value"],
        ram=d["ram"]["value"],
        gpu=d["gpu"]["value"],
    ))


def build_ai_log_header(agent: "SiasMapAgent", locations, stats, extra: str = "") -> str:
    """
    生成 AI 日志的人工撰写部分（放在运行原文之前）。
    这样 AI 日志既有人写的说明，又有机器原样留存的对话，信息密度最高。
    """
    lines = []
    lines.append("## 1. 本次运行说明（人工撰写）\n")
    lines.append(f"- **运行时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **运行入口**：`python main.py`（见题目要求的 Level 2 主链路）")
    lines.append(f"- **模型**：`{config.MODEL_NAME}`（Ollama tag，量化 {config.QUANTIZATION}）")
    lines.append(f"- **接口**：Ollama OpenAI 兼容端点 `{config.OPENAI_COMPAT_URL}`（本地）")
    lines.append(f"- **生成地点数**：{len(locations)} 个")
    lines.append(f"- **解析成功轮次**：{stats['parse_ok_rounds']}/{stats['total_rounds']}"
                 f"（{stats['parse_success_rate']}%）")
    lines.append(f"- **推理速度**：{stats['tok_s_min']} ~ {stats['tok_s_max']} tok/s，"
                 f"均值 {stats['tok_s_avg']} tok/s")
    lines.append("")
    lines.append("### 1.1 本轮生成的地点清单（原文来自模型输出）\n")
    lines.append("| # | name_zh | name | latitude | longitude |")
    lines.append("|---|---|---|---|---|")
    for i, loc in enumerate(locations, 1):
        lines.append(f"| {i} | {loc.get('name_zh')} | {loc.get('name')} | "
                     f"{loc.get('latitude')} | {loc.get('longitude')} |")
    lines.append("")
    if extra:
        lines.append(extra)
    lines.append("\n---\n")
    lines.append("## 2. 逐轮原始对话记录（机器留档，未删改）\n")
    lines.append("> 以下为脚本自动写入的原始日志。`模型原始输出` 一栏是模型的**逐字原文**。\n")
    return "\n".join(lines)


def mode_once(agent: SiasMapAgent) -> int:
    """Level 2 主链路：一次生成 -> 建图 -> 写日志。"""
    print("\n[模式] 一次性生成（Level 2 主链路）")
    locations = agent.generate_locations()
    if not locations:
        print("\n✗ 未能获得可用地点数据，终止。请检查 logs/raw_model_outputs/ 下的模型原文。")
        agent.save_ai_log()
        return 1

    stats = map_generator.map_stats(locations)
    print(f"\n[统计] 共 {stats['markers']} 个点位，类别分布：{stats['categories']}")

    # 本地工具调用演示（空间关系计算，不联网）
    tool_info = agent.enrich_with_tools(locations)
    if tool_info.get("route_examples"):
        print("\n[工具调用演示] 本地 describe_route 工具输出：")
        for t in tool_info["route_examples"]:
            print(f"    · {t}")
    if tool_info.get("nearest_pair"):
        np = tool_info["nearest_pair"]
        print(f"    · 最近两点：{np['a']} ↔ {np['b']}，约 {np['meters']} 米")

    out = map_generator.generate_map(
        locations,
        output_path=config.OUTPUT_MAP_HTML,
        subtitle=f"模型 {config.MODEL_NAME}（{config.QUANTIZATION}）· "
                 f"Ollama · 纯本地推理 · 数据由本地模型生成",
    )
    print(f"\n[完成] 交互式地图已生成：{out}")

    extra = ""
    if tool_info.get("route_examples"):
        extra = ("### 1.2 本地工具调用记录（非模型生成，代码直接产出）\n\n"
                 + "\n".join(f"- {t}" for t in tool_info["route_examples"]) + "\n")
    header = build_ai_log_header(agent, locations, agent.stats(), extra=extra)
    p = agent.save_ai_log(extra_header=header)
    print(f"[完成] AI 日志已写入：{p}")
    return 0


def mode_interactive(agent: SiasMapAgent) -> int:
    """Level 3 加分：交互式多轮对话。"""
    print("\n[模式] 交互式多轮对话（Level 3）")
    locations = agent.generate_locations()
    if not locations:
        print("\n✗ 首轮生成失败，无法进入多轮模式。")
        return 1
    map_generator.generate_map(locations, output_path=config.OUTPUT_MAP_HTML)
    print(f"\n初始地图已生成（{len(locations)} 个点位）：{config.OUTPUT_MAP_HTML}")

    print("""
可用指令：
  add <地点名称>          新增一个标记点（模型生成，追加进地图）
  modify <原名称> <新描述> 修改某个标记点的描述
  list                    列出当前所有点位
  save                    保存地图与 AI 日志
  quit                    退出并保存
""")
    while True:
        try:
            cmd = input("\n[多轮对话] 请输入指令 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n(已中断)")
            break
        if not cmd:
            continue

        low = cmd.lower()
        if low in ("quit", "exit", "q"):
            break
        if low == "list":
            for i, loc in enumerate(locations, 1):
                print(f"  {i:2d}. {loc.get('name_zh')} ({loc.get('name')}) "
                      f"[{loc.get('latitude')}, {loc.get('longitude')}]")
            continue
        if low == "save":
            map_generator.generate_map(locations, output_path=config.OUTPUT_MAP_HTML)
            agent.save_ai_log(extra_header=build_ai_log_header(agent, locations, agent.stats()))
            print("  已保存地图与 AI 日志。")
            continue
        if low.startswith("add "):
            name = cmd[4:].strip()
            new_loc = agent.add_marker(name)
            if new_loc:
                locations.append(new_loc)
                print(f"  ✓ 已新增：{new_loc.get('name_zh')} "
                      f"[{new_loc.get('latitude')}, {new_loc.get('longitude')}]")
                map_generator.generate_map(locations, output_path=config.OUTPUT_MAP_HTML)
                print("  地图已刷新。")
            else:
                print("  ✗ 新增失败（模型输出未通过解析，原文已留档）。")
            continue
        if low.startswith("modify "):
            parts = cmd[7:].strip().split(" ", 1)
            if len(parts) != 2:
                print("  用法：modify <原名称> <新描述>")
                continue
            old, new_info = parts
            modified = agent.modify_marker(old, new_info)
            if modified:
                hit = False
                for i, loc in enumerate(locations):
                    if loc.get("name_zh") == old or loc.get("name") == old:
                        locations[i] = modified
                        hit = True
                        break
                if not hit:
                    locations.append(modified)
                print(f"  ✓ 已修改：{modified.get('name_zh')}")
                map_generator.generate_map(locations, output_path=config.OUTPUT_MAP_HTML)
                print("  地图已刷新。")
            else:
                print("  ✗ 修改失败（模型输出未通过解析，原文已留档）。")
            continue
        print("  未知指令。可用：add / modify / list / save / quit")

    if locations:
        map_generator.generate_map(locations, output_path=config.OUTPUT_MAP_HTML)
        agent.save_ai_log(extra_header=build_ai_log_header(agent, locations, agent.stats()))
        print(f"\n[完成] 地图：{config.OUTPUT_MAP_HTML}")
        print(f"[完成] AI 日志：{config.AI_LOG_MARKDOWN}")
    return 0


def mode_fault_test(agent: SiasMapAgent) -> int:
    """容错对抗测试：故意诱导模型输出脏文本，验证五级容错。"""
    print("\n[模式] 容错对抗测试")
    parsed, metrics = agent.fault_injection_test()
    hit = metrics.get("json_strategy_hit")
    if parsed is not None:
        print(f"\n✓ 容错成功：模型输出了额外文字，但解析器用「{hit}」策略成功提取出 JSON。")
        print(f"  提取到 {len(parsed) if isinstance(parsed, list) else 1} 条记录。")
    else:
        print("\n✗ 五级容错均未成功。模型原始输出已完整留档，可据此调提示词。")
    agent.save_ai_log()
    print(f"\nAI 日志（含失败现场）：{config.AI_LOG_MARKDOWN}")
    return 0 if parsed is not None else 1


def mode_demo(agent: SiasMapAgent) -> int:
    """演示模式：一次性跑完 Level 2 + 容错 + 多轮，方便录屏。"""
    print("\n[模式] 演示模式（Level 2 + 容错测试 + Level 3 多轮）")
    rc = mode_once(agent)
    if rc != 0:
        return rc

    # 容错测试（追加记录）
    agent.fault_injection_test()

    # 多轮：自动新增两个点位 + 修改一个点位
    added = []
    for nm in ("西亚斯学院体育馆", "新郑市第一人民医院"):
        loc = agent.add_marker(nm)
        if loc:
            added.append(loc)
            print(f"  ✓ 自动新增（多轮）：{loc.get('name_zh')}")

    # 重新读取当前地点集合（首轮 + 新增）并重建地图
    import json as _json
    import json_repair
    all_locs = []
    for t in agent.logger.turns:
        # 容错对抗测试那一轮是「解析器压力测试」，它返回的地点不属于正式地图数据，跳过
        if "容错" in t["phase"]:
            continue
        if t["parsed_ok"] and t["parsed_count"]:
            # 从原始输出重新解析，保证数据来源一致
            data, _ = json_repair.parse_model_json(t["raw_model_output"])
            if data:
                if isinstance(data, dict):
                    data = [data]
                good, _ = json_repair.drop_invalid_records(data)
                all_locs.extend(good)
    if all_locs:
        map_generator.generate_map(all_locs, output_path=config.OUTPUT_MAP_HTML)
        agent.save_ai_log(extra_header=build_ai_log_header(agent, all_locs, agent.stats()))
        print(f"\n[完成] 演示地图（{len(all_locs)} 点位）：{config.OUTPUT_MAP_HTML}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="C4D 本地大模型 Agent —— SIAS 交互式地图",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interactive", action="store_true", help="交互式多轮对话（Level 3）")
    ap.add_argument("--fault-test", action="store_true", help="容错对抗测试")
    ap.add_argument("--demo", action="store_true", help="演示模式（一次跑完全流程）")
    ap.add_argument("--no-verbose", action="store_true", help="静默模式（少打印）")
    args = ap.parse_args()

    print_banner()
    agent = SiasMapAgent(verbose=not args.no_verbose)

    print("[预检] 检查本地 Ollama 服务与模型 ...")
    hc = agent.client.health_check()
    if not hc["running"]:
        print(f"\n✗ {hc['error']}")
        print("\n修复步骤：")
        print("  1) 安装 Ollama：https://ollama.com/download")
        print("  2) 启动服务     ：ollama serve")
        print(f"  3) 拉取模型     ：ollama pull {config.MODEL_NAME}")
        return 1
    print(f"  ✓ Ollama v{hc['version']} 运行中 @ {hc['host']}")
    if not agent.client.model_exists():
        print(f"\n✗ 本地没有模型 {config.MODEL_NAME}")
        print(f"  请执行：ollama pull {config.MODEL_NAME}")
        return 1
    print(f"  ✓ 模型 {config.MODEL_NAME} 已在本地")

    try:
        if args.demo:
            rc = mode_demo(agent)
        elif args.interactive:
            rc = mode_interactive(agent)
        elif args.fault_test:
            rc = mode_fault_test(agent)
        else:
            rc = mode_once(agent)
        # 成功跑完就把地图与 AI 日志同步一份到工作区根目录
        if rc == 0:
            publish_to_workspace()
        return rc
    except OllamaNotRunningError as e:
        print(f"\n✗ Ollama 服务异常：{e}")
        return 1
    except ModelNotPulledError as e:
        print(f"\n✗ 模型未就绪：{e}")
        return 1
    except OllamaError as e:
        print(f"\n✗ 调用本地模型出错：{e}")
        return 1
    except KeyboardInterrupt:
        print("\n(用户中断)")
        return 130


if __name__ == "__main__":
    sys.exit(main())

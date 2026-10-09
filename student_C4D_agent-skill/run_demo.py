# -*- coding: utf-8 -*-
"""
run_demo.py —— 无人值守演示脚本（供录屏使用）
============================================

用途：一条命令跑完 Level 2 + 容错测试 + Level 3 多轮对话的完整流程，
      全程自动，不需要人工输入，适合录制演示视频。

流程：
    [0] 打印四项关键信息（截图/录屏取证点）
    [1] 首轮：模型生成 12 个地点 -> 建图
    [2] 容错测试：故意诱导脏输出 -> 验证五级容错
    [3] 多轮：新增 2 个点位 -> 重建地图
    [4] 汇总：tok/s、解析成功率、产物清单

用法：
    python run_demo.py

作者：student
日期：2026-10
"""

import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config                      # noqa: E402
import json_repair                 # noqa: E402
import map_generator               # noqa: E402
from agent import SiasMapAgent     # noqa: E402


def step(n: int, title: str) -> None:
    print(f"\n{'#'*76}")
    print(f"#  步骤 {n}：{title}")
    print(f"{'#'*76}")
    time.sleep(0.3)


def main() -> int:
    t_start = time.time()
    d = config.DEVICE_INFO

    print("=" * 76)
    print("  C4D 演示 —— 本地 Gemma 4 Agent 生成 SIAS 交互式地图")
    print("=" * 76)
    print(f"  演示开始时间 : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  [①] 模型      : {config.MODEL_NAME}")
    print(f"  [②] 量化      : {config.QUANTIZATION}")
    print(f"  [③] 运行工具  : {config.RUNTIME_TOOL} @ {config.OLLAMA_HOST}")
    print(f"  [③] 设备      : {d['cpu']['value']} / {d['ram']['value']} / {d['gpu']['value']}")
    print(f"  [④] 推理速度  : 下面每步实时打印 tok/s")
    print("=" * 76)

    agent = SiasMapAgent(verbose=True)

    # ---------- 预检 ----------
    step(0, "预检本地 Ollama 服务")
    hc = agent.client.health_check()
    if not hc["running"]:
        print(f"  ✗ {hc['error']}")
        return 1
    print(f"  ✓ Ollama v{hc['version']} 运行中 @ {hc['host']}")
    if not agent.client.model_exists():
        print(f"  ✗ 模型 {config.MODEL_NAME} 未下载，请先 ollama pull")
        return 1
    print(f"  ✓ 模型 {config.MODEL_NAME} 就绪")

    # ---------- 步骤 1：首轮生成 ----------
    step(1, "首轮：本地模型生成地点 JSON（Level 2 主链路）")
    locations = agent.generate_locations()
    if not locations:
        print("  ✗ 首轮失败，见 logs/raw_model_outputs/")
        return 1
    map_generator.generate_map(
        locations, output_path=config.OUTPUT_MAP_HTML,
        subtitle=f"模型 {config.MODEL_NAME}（{config.QUANTIZATION}）· Ollama · 本地推理")
    print(f"  ✓ 地图已生成：{config.OUTPUT_MAP_HTML}（{len(locations)} 个点位）")

    # ---------- 步骤 2：容错测试 ----------
    step(2, "容错测试：诱导模型输出多余文字，验证五级容错解析")
    parsed, m = agent.fault_injection_test()
    if parsed is not None:
        print(f"  ✓ 容错成功：命中策略「{m.get('json_strategy_hit')}」")
    else:
        print("  ! 五级容错未成功（失败现场已留档，这也是有效的复盘素材）")

    # ---------- 步骤 3：多轮对话 ----------
    step(3, "多轮对话：新增标记点（Level 3 加分）")
    new_locs = []
    for nm in ("西亚斯学院体育馆", "新郑市第一人民医院"):
        loc = agent.add_marker(nm)
        if loc:
            new_locs.append(loc)
            print(f"  ✓ 新增：{loc.get('name_zh')} "
                  f"({loc.get('latitude')}, {loc.get('longitude')})")
        else:
            print(f"  ! 新增「{nm}」失败，已留档")

    # ---------- 汇总所有点位 ----------
    step(4, "重建地图并汇总")
    all_locs = []
    for t in agent.logger.turns:
        # 容错对抗测试轮次属于解析器压力测试，其数据不进入正式地图
        if "容错" in t["phase"]:
            continue
        if t["parsed_ok"] and t["parsed_count"]:
            data, _ = json_repair.parse_model_json(t["raw_model_output"])
            if data:
                if isinstance(data, dict):
                    data = [data]
                good, _ = json_repair.drop_invalid_records(data)
                all_locs.extend(good)

    # 去重（按中英文名）
    seen, uniq = set(), []
    for loc in all_locs:
        key = (loc.get("name_zh"), loc.get("name"))
        if key not in seen:
            seen.add(key)
            uniq.append(loc)

    map_generator.generate_map(
        uniq, output_path=config.OUTPUT_MAP_HTML,
        subtitle=f"模型 {config.MODEL_NAME}（{config.QUANTIZATION}）· Ollama · 本地推理")
    print(f"  ✓ 最终地图：{config.OUTPUT_MAP_HTML}（{len(uniq)} 个点位）")

    agent.save_ai_log()
    st = agent.stats()

    # ---------- 总结 ----------
    print("\n" + "=" * 76)
    print("  演示结束 · 汇总")
    print("=" * 76)
    print(f"  总轮次        : {st['total_rounds']}")
    print(f"  解析成功轮次  : {st['parse_ok_rounds']}/{st['total_rounds']}"
          f"（{st['parse_success_rate']}%）")
    print(f"  推理速度      : {st['tok_s_min']} ~ {st['tok_s_max']} tok/s"
          f"（均值 {st['tok_s_avg']}）")
    print(f"  地图点位      : {len(uniq)}")
    print(f"  模型总推理耗时: {st['elapsed_total']} s")
    print(f"  演示总耗时    : {time.time() - t_start:.1f} s")
    print("\n  产物：")
    print(f"    · {config.OUTPUT_MAP_HTML}")
    print(f"    · {config.AI_LOG_MARKDOWN}")
    print(f"    · logs/agent_calls.jsonl")
    print(f"    · logs/raw_model_outputs/  （逐轮模型原文快照）")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())

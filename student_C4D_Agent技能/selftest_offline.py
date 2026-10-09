# -*- coding: utf-8 -*-
"""
selftest_offline.py —— 离线自检（不需要模型、不需要联网）
=======================================================

为什么要有这个脚本？
--------------------
C4D 的评审很可能在「没有拉模型」的环境下先看代码。如果所有验证都依赖模型，
评审就无法快速复现。本脚本把**不依赖模型**的那部分能力单独测一遍：

    1. 五级 JSON 容错解析器（9 个用例：8 个脏输入 + 1 个必须失败的输入）
    2. 地点字段校验器（缺字段 / 坐标越界 / 类型错误的检出能力）
    3. 本地工具集（haversine 距离、方位角、最近点对）的数值正确性
    4. Folium 地图渲染管线（用固定样例数据渲染，验证产物结构完整）

用法：
    python selftest_offline.py

输出：
    逐项 PASS/FAIL + 末尾汇总，退出码 0 表示全部通过。

作者：student
日期：2026-10
"""

import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json_repair            # noqa: E402
import tools                  # noqa: E402

PASS, FAIL = 0, 0
RESULTS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        RESULTS.append(("PASS", name, detail))
    else:
        FAIL += 1
        RESULTS.append(("FAIL", name, detail))


# ---------------------------------------------------------------------------
# 测试 1：五级容错解析器
# ---------------------------------------------------------------------------
GOOD_OBJ = ('{"name":"A","name_zh":"甲","latitude":34.402,"longitude":113.758,'
            '"description":"描述"}')
GOOD_ARR = f"[{GOOD_OBJ}]"

PARSE_CASES = [
    ("干净数组",            GOOD_ARR,                                    True),
    ("前言污染",            f"好的，以下是结果：\n{GOOD_ARR}\n希望对你有帮助。", True),
    ("markdown 围栏",       f"```json\n{GOOD_ARR}\n```",                  True),
    ("尾部多余逗号",        GOOD_ARR[:-1] + ",]",                        True),
    ("中文全角引号",        GOOD_ARR.replace('"', "“").replace("\u201d", "\u201d"), True),
    ("描述内裸换行",        GOOD_ARR.replace("描述", "第一行\n第二行"),     True),
    ("单对象非数组",        GOOD_OBJ,                                     True),
    ("前后都是废话+围栏",   f"思考过程...\n```\n{GOOD_ARR}\n```\n以上。",   True),
    ("无效输出（应失败）",  "抱歉，我无法完成这个请求。",                   False),
]


def test_parsers() -> None:
    print("\n[测试 1] 五级 JSON 容错解析器")
    for name, raw, expect_ok in PARSE_CASES:
        data, trace = json_repair.parse_model_json(raw)
        got_ok = data is not None
        hit = trace.hit_strategy()
        check(f"解析-{name}", got_ok == expect_ok,
              f"期望{'成功' if expect_ok else '失败'}，实际{'成功' if got_ok else '失败'}"
              + (f"，策略={hit}" if got_ok else ""))
        print(f"    {'√' if got_ok == expect_ok else '×'} {name:18s} "
              f"{'成功' if got_ok else '失败':4s} 策略={hit}")

    # 大小写/全角引号专项：确保「全角引号」用例真的是全角
    full_width = "[{“name”:“A”,“name_zh”:“甲”,“latitude”:34.402," \
                 "“longitude”:113.758,“description”:“描述”}]"
    data, trace = json_repair.parse_model_json(full_width)
    check("解析-真·全角引号专项", data is not None and len(data) == 1,
          f"策略={trace.hit_strategy()}")
    print(f"    {'√' if data is not None else '×'} 真·全角引号专项   "
          f"策略={trace.hit_strategy()}")


# ---------------------------------------------------------------------------
# 测试 2：字段与坐标校验
# ---------------------------------------------------------------------------
def test_validation() -> None:
    print("\n[测试 2] 地点字段与坐标校验器")
    good = {"name": "A", "name_zh": "甲", "latitude": 34.402,
            "longitude": 113.758, "description": "描述"}
    missing = {"name": "B", "name_zh": "乙"}                       # 缺坐标和描述
    out_of_range = {"name": "C", "name_zh": "丙", "latitude": 40.0,
                    "longitude": 113.7, "description": "越界"}
    wrong_type = {"name": "D", "name_zh": "丁", "latitude": "34.4",
                  "longitude": 113.7, "description": "坐标是字符串"}

    rep = json_repair.validate_locations([good, missing, out_of_range, wrong_type])
    check("校验-总数正确", rep["total"] == 4, f"total={rep['total']}")
    check("校验-仅 1 条合格", rep["valid"] == 1, f"valid={rep['valid']}")
    check("校验-检出越界", rep["out_of_range"] >= 1, f"out_of_range={rep['out_of_range']}")
    issues_all = " ".join(i for r in rep["records"] for i in r["issues"])
    check("校验-检出缺字段", "缺字段" in issues_all)
    check("校验-检出类型错误", "非数值" in issues_all)
    print(f"    {'√' if rep['valid']==1 else '×'} 4 条输入中 1 条合格，"
          f"越界 {rep['out_of_range']} 项，问题清单：{issues_all[:80]}...")

    good_list, bad_list = json_repair.drop_invalid_records(
        [good, missing, out_of_range, wrong_type])
    check("剔除-保留 1 条", len(good_list) == 1, f"good={len(good_list)}")
    check("剔除-剔除 3 条", len(bad_list) == 3, f"bad={len(bad_list)}")
    print(f"    {'√' if len(good_list)==1 and len(bad_list)==3 else '×'} "
          f"剔除后保留 {len(good_list)} 条，剔除 {len(bad_list)} 条")


# ---------------------------------------------------------------------------
# 测试 3：本地工具
# ---------------------------------------------------------------------------
def test_tools() -> None:
    print("\n[测试 3] 本地计算工具")
    # 已知距离校验：纬度差 0.001° ≈ 111.2 米（子午线方向）
    d = tools.haversine_distance(34.402, 113.758, 34.403, 113.758)
    ok = d["ok"] and 110 <= d["result"]["meters"] <= 112.5
    check("工具-haversine 精度", ok, f"{d['result']['meters'] if d['ok'] else 'N/A'} 米")
    print(f"    {'√' if ok else '×'} 纬度 0.001° 距离 = "
          f"{d['result']['meters'] if d['ok'] else 'N/A'} 米（理论约 111.2 米）")

    # 方位角：正东方向应为 90°
    b = tools.bearing(34.402, 113.758, 34.402, 113.768)
    ok_b = b["ok"] and 88 <= b["result"]["degrees"] <= 92
    check("工具-方位角正东", ok_b, f"{b['result'] if b['ok'] else 'N/A'}")
    print(f"    {'√' if ok_b else '×'} 正东方向方位角 = "
          f"{b['result']['degrees'] if b['ok'] else 'N/A'}°（{b['result']['compass'] if b['ok'] else ''}）")

    # 最近点对
    locs = [
        {"name_zh": "甲", "name": "A", "latitude": 34.4020, "longitude": 113.7580, "description": "d"},
        {"name_zh": "乙", "name": "B", "latitude": 34.4021, "longitude": 113.7581, "description": "d"},
        {"name_zh": "丙", "name": "C", "latitude": 34.4100, "longitude": 113.7700, "description": "d"},
    ]
    pair = tools.nearest_pair(locs)
    ok_p = pair is not None and pair[0]["name_zh"] == "甲" and pair[1]["name_zh"] == "乙"
    check("工具-最近点对", ok_p, f"{pair[2]:.1f} 米" if pair else "N/A")
    print(f"    {'√' if ok_p else '×'} 最近点对 = "
          f"{pair[0]['name_zh']}↔{pair[1]['name_zh']}（{pair[2]:.1f} 米）" if pair else "    × 无结果")

    # 预留工具应明确返回未实现，而不是假装成功
    w = tools.call_tool("weather_query", location="西亚斯学院")
    check("工具-预留接口明确未实现", w["ok"] is False and "NOT_IMPLEMENTED" in w["error"])
    print(f"    {'√' if not w['ok'] else '×'} 预留接口 weather_query 返回 "
          f"{'未实现（符合预期）' if not w['ok'] else '假装成功（不符合预期）'}")

    # 未知工具
    u = tools.call_tool("not_a_tool")
    check("工具-未知工具报错", u["ok"] is False)
    print(f"    {'√' if not u['ok'] else '×'} 未知工具调用被正确拒绝")


# ---------------------------------------------------------------------------
# 测试 4：Folium 渲染管线
# ---------------------------------------------------------------------------
def test_map_pipeline() -> None:
    print("\n[测试 4] Folium 地图渲染管线（用固定样例，与模型解耦）")
    sample = [
        {"name": "SIAS Library", "name_zh": "西亚斯学院图书馆",
         "latitude": 34.4021, "longitude": 113.7581, "description": "样例描述一"},
        {"name": "SIAS Gate", "name_zh": "西亚斯学院南门",
         "latitude": 34.3958, "longitude": 113.7644, "description": "样例描述二"},
        {"name": "Food Court", "name_zh": "第一学生食堂",
         "latitude": 34.4030, "longitude": 113.7592, "description": "样例描述三"},
    ]
    try:
        import map_generator
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "selftest_map.html")
            map_generator.generate_map(sample, output_path=out)
            html = open(out, encoding="utf-8").read()
            size = os.path.getsize(out)   # 必须在临时目录存在时统计
        check("地图-文件生成", size > 10_000, f"{size} 字节")
        check("地图-含 Leaflet", "leaflet" in html.lower())
        check("地图-含全部 3 个点名称", all(s["name_zh"] in html for s in sample))
        check("地图-含经纬度", "34.4021" in html and "113.7581" in html)
        check("地图-含图层控制", "L.control.layers" in html or "layers" in html.lower())
        check("地图-含弹窗绑定", "bindPopup" in html)
        stats = map_generator.map_stats(sample)
        check("地图-类别分类", stats["markers"] == 3, str(stats["categories"]))
        print(f"    ✓ 渲染 {len(sample)} 个点位，产物 {size} 字节，"
              f"类别分布 {stats['categories']}")
    except Exception as e:  # noqa: BLE001
        check("地图-渲染管线", False, repr(e))
        print(f"    × 渲染失败：{e}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    print("=" * 74)
    print("  student_C4D_Agent技能 · 离线自检（无需模型 / 无需联网）")
    print("=" * 74)
    test_parsers()
    test_validation()
    test_tools()
    test_map_pipeline()

    print("\n" + "=" * 74)
    print(f"  结果：{PASS} 项通过，{FAIL} 项失败，共 {PASS + FAIL} 项")
    print("=" * 74)
    if FAIL:
        print("  失败明细：")
        for status, name, detail in RESULTS:
            if status == "FAIL":
                print(f"    × {name} —— {detail}")
    else:
        print("  全部通过。")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

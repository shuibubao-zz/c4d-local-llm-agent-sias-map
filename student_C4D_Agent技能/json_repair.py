# -*- coding: utf-8 -*-
"""
json_repair.py —— 本地小模型输出 JSON 的多级容错解析器
=====================================================

为什么需要这个模块？
--------------------
本地量化模型（如 Gemma 4 E4B Q4_K_M）即使被系统提示词约束「只输出 JSON」，
在实践里仍会偶发以下情况：

  1. 在 JSON 前面写一句「好的，以下是……」（前言污染）
  2. 用 ```json ... ``` 代码块把 JSON 包起来（Markdown 污染）
  3. JSON 末尾多一个逗号（trailing comma）
  4. 中文全角引号 “ ” 混入 JSON 字符串（引号污染）
  5. 描述文本里有未转义的换行，导致字符串跨行
  6. 数字被模型加了引号（"latitude": "34.402"）
  7. 直接输出了对象 {} 而不是要求的数组 []

对应策略：**五级递进容错**，逐级放宽，任一级成功立即返回，
并把「用了哪一级策略」记录下来写进日志，便于复盘模型输出质量。

设计原则
--------
* 绝不静默伪造数据：全部策略都失败时返回 (None, 诊断信息)，由上层决定如何处理。
* 每一级都记录诊断信息，日志里能看到「模型原文 → 命中策略 → 修复结果」的完整链路。
* 允许修复「污染」和「格式瑕疵」，但**不替模型编造缺失的字段值**。

作者：student
日期：2026-10
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 诊断记录器：把解析过程完整暴露出来，供 AI 日志使用
# ----------------------------------------------------------------------------
class RepairTrace:
    """记录一次解析尝试的所有中间状态。"""

    def __init__(self) -> None:
        self.steps: List[Dict[str, Any]] = []

    def add(self, step: str, ok: bool, detail: str = "") -> None:
        self.steps.append({"step": step, "ok": ok, "detail": detail})

    def summary(self) -> str:
        """返回人类可读的逐级诊断文本（用于写入日志）。"""
        lines = []
        for i, s in enumerate(self.steps, 1):
            mark = "命中" if s["ok"] else "未命中"
            lines.append(f"    [{i}] {s['step']} -> {mark}" + (f"（{s['detail']}）" if s["detail"] else ""))
        return "\n".join(lines)

    def hit_strategy(self) -> Optional[str]:
        """返回第一个成功的策略名。"""
        for s in self.steps:
            if s["ok"]:
                return s["step"]
        return None


# ---------------------------------------------------------------------------
# 辅助清理函数
# ----------------------------------------------------------------------------
def _strip_markdown_fence(text: str) -> str:
    """去掉 ```json ... ``` / ``` ... ``` 代码块围栏。"""
    text = re.sub(r"```(?:json|JSON)?\s*", "", text)
    text = text.replace("```", "")
    return text.strip()


def _normalize_quotes(text: str) -> str:
    """
    把中文全角引号替换为 ASCII 双引号。
    仅当文本里存在全角引号时才处理，避免误伤正常中文描述中的引号。
    """
    return (text
            .replace("“", '"').replace("”", '"')
            .replace("‘", "'").replace("’", "'"))


def _remove_trailing_commas(text: str) -> str:
    """删除对象/数组尾部的多余逗号：{"a":1,} / [1,2,] -> {"a":1} / [1,2]"""
    return re.sub(r",\s*([\]}])", r"\1", text)


def _extract_bracketed(text: str, open_ch: str, close_ch: str) -> Optional[str]:
    """
    用「括号配对计数」的方式提取最外层的一对 [] 或 {}。
    比贪婪正则更可靠：能正确处理嵌套结构。
    """
    start = text.find(open_ch)
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _coerce_numeric_fields(obj: Any) -> Any:
    """
    修复模型把数字写成字符串的情况：
    "latitude": "34.402000" -> "latitude": 34.402
    只处理明确的经纬度字段，不碰其他字段，避免误改描述文本。
    """
    numeric_keys = {"latitude", "longitude", "lat", "lng", "lon"}
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in numeric_keys and isinstance(v, str):
                try:
                    out[k] = float(v.strip())
                except (ValueError, TypeError):
                    out[k] = v
            elif isinstance(v, (dict, list)):
                out[k] = _coerce_numeric_fields(v)
            else:
                out[k] = v
        return out
    if isinstance(obj, list):
        return [_coerce_numeric_fields(x) for x in obj]
    return obj


# ---------------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------------
def parse_model_json(raw_text: str) -> Tuple[Optional[Any], RepairTrace]:
    """
    五级递进容错解析。

    参数：
        raw_text: 模型返回的**原始文本**（未经任何预处理）

    返回：
        (data, trace)
        - data:  解析成功返回 list 或 dict；全部失败返回 None
        - trace: RepairTrace，记录每一级策略是否命中，供日志留档
    """
    trace = RepairTrace()
    if raw_text is None:
        trace.add("空输入检查", False, "模型返回 None")
        return None, trace

    text = raw_text.strip()
    if not text:
        trace.add("空输入检查", False, "模型返回空字符串")
        return None, trace

    # ---------------- 策略 1：直接 json.loads ----------------
    try:
        data = json.loads(text)
        trace.add("策略1-直接解析", True)
        return _coerce_numeric_fields(data), trace
    except json.JSONDecodeError as e:
        trace.add("策略1-直接解析", False, f"{e.msg} @pos {e.pos}")

    # ---------------- 策略 2：剥离 Markdown 围栏后重试 ----------------
    cleaned = _strip_markdown_fence(text)
    if cleaned != text:
        try:
            data = json.loads(cleaned)
            trace.add("策略2-剥离```围栏", True)
            return _coerce_numeric_fields(data), trace
        except json.JSONDecodeError as e:
            trace.add("策略2-剥离```围栏", False, e.msg)
    else:
        trace.add("策略2-剥离```围栏", False, "原文无 ``` 围栏，跳过")

    # ---------------- 策略 3：括号配对提取最外层 [...] ----------------
    # （这一步同时解决「前言/后记污染」问题）
    candidate3 = cleaned
    arr = _extract_bracketed(candidate3, "[", "]")
    if arr:
        try:
            data = json.loads(arr)
            trace.add("策略3-括号配对提取数组", True, f"提取 {len(arr)} 字符")
            return _coerce_numeric_fields(data), trace
        except json.JSONDecodeError as e:
            trace.add("策略3-括号配对提取数组", False, e.msg)
    else:
        trace.add("策略3-括号配对提取数组", False, "未找到成对的 []")

    # ---------------- 策略 4：全角引号归一 + 去尾逗号 + 再提取数组 ----------------
    fixed = _normalize_quotes(cleaned)
    fixed = _remove_trailing_commas(fixed)
    arr4 = _extract_bracketed(fixed, "[", "]")
    if arr4:
        try:
            data = json.loads(arr4)
            trace.add("策略4-引号归一+去尾逗号", True)
            return _coerce_numeric_fields(data), trace
        except json.JSONDecodeError as e:
            trace.add("策略4-引号归一+去尾逗号", False, e.msg)
    else:
        trace.add("策略4-引号归一+去尾逗号", False, "修正后仍无成对 []")

    # ---------------- 策略 5：单对象 {} 提升为数组 + 修补换行 ----------------
    # 5a. 模型只输出了一个对象 {}
    obj5 = _extract_bracketed(fixed, "{", "}")
    if obj5:
        try:
            data = json.loads(obj5)
            trace.add("策略5a-单对象提升为数组", True, "模型输出 {} 而非 []，已包装")
            return _coerce_numeric_fields([data]), trace
        except json.JSONDecodeError as e:
            trace.add("策略5a-单对象提升为数组", False, e.msg)
    else:
        trace.add("策略5a-单对象提升为数组", False, "无成对 {}")

    # 5b. 字符串内有裸换行：把 JSON 字符串内部的换行转义
    try:
        repaired = _escape_raw_newlines_in_strings(fixed)
        arr5 = _extract_bracketed(repaired, "[", "]") or repaired
        data = json.loads(arr5)
        trace.add("策略5b-转义字符串内裸换行", True)
        if isinstance(data, dict):
            data = [data]
        return _coerce_numeric_fields(data), trace
    except json.JSONDecodeError as e:
        trace.add("策略5b-转义字符串内裸换行", False, e.msg)
    except Exception as e:  # noqa: BLE001 - 兜底，任何异常都不应让主流程崩
        trace.add("策略5b-转义字符串内裸换行", False, repr(e))

    # ---------------- 全部失败 ----------------
    trace.add("全部策略", False, "五级容错均未成功，返回 None")
    return None, trace


def _escape_raw_newlines_in_strings(text: str) -> str:
    """
    把 JSON 字符串内部的裸换行替换成 \\n。
    仅在「处于字符串内部」时替换，字符串外的换行保留（JSON 允许）。
    """
    out = []
    in_str = False
    escape = False
    for ch in text:
        if escape:
            out.append(ch)
            escape = False
            continue
        if ch == "\\":
            out.append(ch)
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            out.append(ch)
            continue
        if in_str and ch in "\r\n":
            out.append("\\n")
            continue
        out.append(ch)
    return "".join(out)


# ---------------------------------------------------------------------------
# 结构化校验：字段完整性检查（不修值，只报告）
# ----------------------------------------------------------------------------
REQUIRED_FIELDS = ("name", "name_zh", "latitude", "longitude", "description")


def validate_locations(data: Any, lat_range: Tuple[float, float] = (34.30, 34.50),
                       lon_range: Tuple[float, float] = (113.65, 113.90)) -> Dict[str, Any]:
    """
    校验地点数据的字段完整性与坐标合理性。

    返回结构：
        {
          "total": 条目数,
          "valid": 完全合格的条目数,
          "records": [ {index, name_zh, ok, issues:[...]}, ... ],
          "out_of_range": 坐标越界条目数
        }

    注意：这里只做「体检」，不替换、不补齐任何字段值 ——
    数据必须来自模型，代码不能替模型编造。
    """
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return {"total": 0, "valid": 0, "records": [], "out_of_range": 0,
                "error": f"数据类型不是 list/dict，而是 {type(data).__name__}"}

    report = {"total": len(data), "valid": 0, "records": [], "out_of_range": 0}
    for i, item in enumerate(data):
        issues: List[str] = []
        if not isinstance(item, dict):
            report["records"].append({"index": i, "name_zh": "?", "ok": False,
                                      "issues": [f"元素不是对象，而是 {type(item).__name__}"]})
            continue
        for f in REQUIRED_FIELDS:
            if f not in item or item[f] in (None, ""):
                issues.append(f"缺字段 {f}")
        # 坐标类型与范围
        lat, lon = item.get("latitude"), item.get("longitude")
        if not isinstance(lat, (int, float)):
            issues.append(f"latitude 非数值({lat!r})")
        elif not (lat_range[0] <= float(lat) <= lat_range[1]):
            issues.append(f"latitude 越界({lat})")
            report["out_of_range"] += 1
        if not isinstance(lon, (int, float)):
            issues.append(f"longitude 非数值({lon!r})")
        elif not (lon_range[0] <= float(lon) <= lon_range[1]):
            issues.append(f"longitude 越界({lon})")
            report["out_of_range"] += 1

        ok = not issues
        if ok:
            report["valid"] += 1
        report["records"].append({
            "index": i,
            "name_zh": item.get("name_zh", "?"),
            "ok": ok,
            "issues": issues,
        })
    return report


def drop_invalid_records(data: Any) -> Tuple[List[Dict], List[Dict]]:
    """
    把校验不通过的条目「剔除」并单独返回，保证进入地图的数据是干净可用的。

    返回：
        (good_records, bad_records)
    注意：剔除 ≠ 编造。坏数据会被记录进日志，而不是被代码补一个假坐标。
    """
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return [], []
    good, bad = [], []
    for item in data:
        if not isinstance(item, dict):
            bad.append({"item": item, "reason": "非对象"})
            continue
        missing = [f for f in REQUIRED_FIELDS if f not in item]
        lat, lon = item.get("latitude"), item.get("longitude")
        if missing or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            bad.append({"item": item, "reason": f"缺字段{missing}或坐标非数值"})
            continue
        if not (34.30 <= float(lat) <= 34.50) or not (113.65 <= float(lon) <= 113.90):
            bad.append({"item": item, "reason": f"坐标越界({lat},{lon})"})
            continue
        good.append(item)
    return good, bad

# -*- coding: utf-8 -*-
"""
tools.py —— 多工具调用框架（Level 3 预留扩展接口）
=================================================

C4D 的 Level 3 列了五个扩展方向，其中「多工具调用」是最有工程价值的一个。
本模块提供**可运行的框架**：工具注册表 + 统一的调用协议 + 两个已实现的
「零外部依赖」示例工具，其余工具留出标准接口，便于后续按同一模式扩展。

设计约束（重要）：
    1. **不调用任何外部第三方地图 API** 获取点位信息 —— 地点数据只能来自本地模型。
       本文件里的工具都刻意做成「不联网」或「只做本地计算」的形式。
    2. 工具调用结果统一返回 dict：{"ok": bool, "tool": str, "result": Any, "error": str|None}
    3. 工具的「选择」可以交给模型（function calling），也可以由规则直接触发；
       本项目为了不引入额外复杂度，采用「模型可选 + 规则兜底」的混合方式。

已实现（零依赖、可离线跑通）：
    * haversine_distance : 计算两个坐标的球面距离（纯数学，本地计算）
    * bearing            : 计算方位角（纯数学，本地计算）
    * describe_route     : 基于上面两个工具，生成「从 A 到 B」的文字路线描述

预留（接口已定，实现留空并标注 TODO）：
    * weather_query      : 查天气（需要联网 API，本项目不做，原因见「拿来说明」）
    * rating_query       : 查评分（需要联网 API，同上）
    * image_recognition  : 校园照片识别（需要多模态输入，本项目不做）

作者：student
日期：2026-10
"""

import math
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 工具 1：球面距离（Haversine）
# ----------------------------------------------------------------------------
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> Dict[str, Any]:
    """
    计算两个经纬度点之间的球面距离（单位：米）。

    这是本地纯计算工具，不访问任何外部服务。
    用途：Agent 可以回答「图书馆离最近食堂多远」这类空间关系问题。
    """
    try:
        R = 6371000.0  # 地球平均半径（米）
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
        d = 2 * R * math.asin(math.sqrt(a))
        return {"ok": True, "tool": "haversine_distance",
                "result": {"meters": round(d, 1), "kilometers": round(d / 1000, 3)},
                "error": None}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "tool": "haversine_distance", "result": None, "error": repr(e)}


# ---------------------------------------------------------------------------
# 工具 2：方位角
# ----------------------------------------------------------------------------
_BEARING_NAMES = ["正北", "东北", "正东", "东南", "正南", "西南", "正西", "西北"]


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> Dict[str, Any]:
    """
    计算从点 1 指向点 2 的方位角（0~360 度）与八方位中文名。
    本地纯计算工具。
    """
    try:
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dl = math.radians(lon2 - lon1)
        y = math.sin(dl) * math.cos(p2)
        x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
        brg = (math.degrees(math.atan2(y, x)) + 360) % 360
        idx = int(((brg + 22.5) % 360) // 45)
        return {"ok": True, "tool": "bearing",
                "result": {"degrees": round(brg, 1), "compass": _BEARING_NAMES[idx]},
                "error": None}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "tool": "bearing", "result": None, "error": repr(e)}


# ---------------------------------------------------------------------------
# 工具 3：路线描述（组合上面两个工具 —— 体现「多步工具编排」）
# ----------------------------------------------------------------------------
def describe_route(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """
    给定两个地点 dict（含 name_zh / latitude / longitude），生成自然语言路线描述。
    这是对「工具调用工具」的演示：内部串联了距离与方位角两个工具。
    """
    try:
        d = haversine_distance(a["latitude"], a["longitude"], b["latitude"], b["longitude"])
        br = bearing(a["latitude"], a["longitude"], b["latitude"], b["longitude"])
        if not d["ok"] or not br["ok"]:
            raise RuntimeError("子工具调用失败")
        text = (f"从「{a.get('name_zh', a.get('name'))}」到「{b.get('name_zh', b.get('name'))}」："
                f"直线距离约 {d['result']['meters']} 米（{d['result']['kilometers']} 公里），"
                f"方向约 {br['result']['compass']}（{br['result']['degrees']}°）。")
        return {"ok": True, "tool": "describe_route",
                "result": {"text": text, "distance": d["result"], "bearing": br["result"]},
                "error": None}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "tool": "describe_route", "result": None, "error": repr(e)}


# ---------------------------------------------------------------------------
# 预留工具：接口已定义，实现留空（明确标注为「本轮不做」）
# ----------------------------------------------------------------------------
def weather_query(location: str) -> Dict[str, Any]:
    """
    [预留] 查询地点天气。

    ⚠️ 本轮不实现，原因：
      1) 天气必须调用外部网络 API，与本项目「全部走本地」的原则冲突；
      2) C4D 只要求「预留扩展接口」，不要求完整实现全部多工具。
    接入方式：填入一个天气 API（如和风天气），把返回值塞进 result 即可，
    调用协议与上面三个工具完全一致，上层无需改动。
    """
    return {"ok": False, "tool": "weather_query", "result": None,
            "error": "NOT_IMPLEMENTED：预留接口。本轮遵循『零外部依赖』原则，未接入天气 API。"}


def rating_query(location: str) -> Dict[str, Any]:
    """[预留] 查询地点评分。同上，需要外部 API，本轮不实现。"""
    return {"ok": False, "tool": "rating_query", "result": None,
            "error": "NOT_IMPLEMENTED：预留接口。需要外部点评类 API，本轮不实现。"}


def image_recognition(image_path: str) -> Dict[str, Any]:
    """
    [预留] 校园照片识别并标注到地图。

    ⚠️ 本轮不实现，原因：Gemma 4 支持多模态，但把图像送进 Ollama 需要额外的
    base64 编码与 /api/generate 的 images 字段适配，本轮聚焦文本 Agent 主链路。
    接入方式：读图 -> base64 -> messages 中附带 image_url -> 解析模型返回的 JSON。
    """
    return {"ok": False, "tool": "image_recognition", "result": None,
            "error": "NOT_IMPLEMENTED：预留接口。需要多模态输入适配，本轮不实现。"}


# ---------------------------------------------------------------------------
# 工具注册表 —— 统一入口，便于上层按名字调用 / 生成给模型的工具描述
# ----------------------------------------------------------------------------
TOOL_REGISTRY: Dict[str, Callable[..., Dict[str, Any]]] = {
    "haversine_distance": haversine_distance,
    "bearing": bearing,
    "describe_route": describe_route,
    "weather_query": weather_query,
    "rating_query": rating_query,
    "image_recognition": image_recognition,
}

# 给模型看的工具说明（未来接 function calling 时直接喂给 tools 参数）
TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "haversine_distance",
        "description": "计算两个经纬度坐标之间的球面直线距离，返回米与公里。",
        "implemented": True,
        "parameters": {"lat1": "number", "lon1": "number", "lat2": "number", "lon2": "number"},
    },
    {
        "name": "bearing",
        "description": "计算从一个坐标指向另一个坐标的方位角，返回角度与八方位名称。",
        "implemented": True,
        "parameters": {"lat1": "number", "lon1": "number", "lat2": "number", "lon2": "number"},
    },
    {
        "name": "describe_route",
        "description": "根据两个地点对象生成自然语言路线描述（内部串联距离与方位角）。",
        "implemented": True,
        "parameters": {"a": "location object", "b": "location object"},
    },
    {
        "name": "weather_query",
        "description": "[预留] 查询某地点天气。需要外部 API，本轮未实现。",
        "implemented": False,
        "parameters": {"location": "string"},
    },
    {
        "name": "rating_query",
        "description": "[预留] 查询某地点评分。需要外部 API，本轮未实现。",
        "implemented": False,
        "parameters": {"location": "string"},
    },
    {
        "name": "image_recognition",
        "description": "[预留] 识别校园照片并标注到地图。需要多模态适配，本轮未实现。",
        "implemented": False,
        "parameters": {"image_path": "string"},
    },
]


def call_tool(name: str, **kwargs) -> Dict[str, Any]:
    """
    统一的工具调用入口。

    参数：
        name   : 工具名（必须存在于 TOOL_REGISTRY）
        kwargs : 工具参数

    返回：统一的工具结果 dict。
    """
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return {"ok": False, "tool": name, "result": None,
                "error": f"未知工具 `{name}`。可用工具：{list(TOOL_REGISTRY.keys())}"}
    return fn(**kwargs)


def nearest_pair(locations: List[Dict[str, Any]]) -> Optional[Tuple[Dict, Dict, float]]:
    """
    在全部地点中找出距离最近的一对（用本地计算，不联网）。
    用途：给地图加一条「最近两点连线」的演示图层，同时展示工具被真实调用过。
    """
    best: Optional[Tuple[Dict, Dict, float]] = None
    for i in range(len(locations)):
        for j in range(i + 1, len(locations)):
            a, b = locations[i], locations[j]
            try:
                d = haversine_distance(a["latitude"], a["longitude"],
                                       b["latitude"], b["longitude"])
                if not d["ok"]:
                    continue
                meters = d["result"]["meters"]
                if best is None or meters < best[2]:
                    best = (a, b, meters)
            except Exception:  # noqa: BLE001
                continue
    return best

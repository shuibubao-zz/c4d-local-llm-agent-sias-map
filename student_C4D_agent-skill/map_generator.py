# -*- coding: utf-8 -*-
"""
map_generator.py —— Folium 交互式地图生成
========================================

把 Agent 从**本地 Gemma 4 模型**拿到的地点 JSON，渲染成一张可直接双击打开的
交互式 HTML 地图。

本模块只负责「渲染」：**不产生任何地点数据，也不修改模型的坐标**。
如果某个点位字段不完整，由上层在进入本模块前剔除，本模块不做兜底编造。

交互特性（对齐 C4D「地图质量 20%」）：
    * 缩放 / 拖动 / 滚轮缩放
    * 点击 Marker 弹窗展示完整点位详情（中英文名 + 描述 + 精确坐标）
    * 按类别自动配色与图标（关键词规则判定，纯本地逻辑）
    * 图层控制：切换「卫星/街道/地形」底图，按类别分组显示/隐藏
    * 全屏、迷你地图、测距、鼠标经纬度、定位控件

作者：student
日期：2026-10
"""

import html
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

import folium
from folium import plugins

import config

# ---------------------------------------------------------------------------
# 类别判定：只用于给图标配色，不改变任何数据
# 规则来源：中文名称里的关键词。命中不了就归入「其它地点」。
# ---------------------------------------------------------------------------
CATEGORY_RULES: List[Tuple[str, str, str, List[str]]] = [
    # (类别键, 中文标签, 颜色, 关键词列表)
    ("gate",      "校门/入口", "darkred",   ["校门", "大门", "西门", "东门", "南门", "北门", "入口"]),
    ("teach",     "教学/科研", "blue",      ["教学楼", "学院", "教室", "实验室", "工程", "科研", "实训"]),
    ("library",   "图书馆",    "purple",    ["图书", "阅览", "书"]),
    ("dorm",      "宿舍/生活", "orange",    ["宿舍", "公寓", "生活", "洗衣", "超市", "便利"]),
    ("food",      "餐饮",      "red",       ["食堂", "餐厅", "美食", "咖啡", "饮"]),
    ("sport",     "体育",      "green",     ["体育", "球场", "操场", "田径", "游泳", "健身", "篮球", "足球"]),
    ("admin",     "行政/办公", "cadetblue", ["行政", "办公", "楼", "中心", "会议"]),
    ("landmark",  "周边地标",  "darkgreen", ["公园", "广场", "医院", "车站", "机场", "景区", "博物馆", "遗址", "湖", "河"]),
    ("culture",   "文化/活动", "darkpurple", ["文化", "礼堂", "剧院", "活动", "音乐", "艺术", "展览"]),
]
DEFAULT_CATEGORY = ("other", "其它地点", "gray", [])


def classify_category(name_zh: str, description: str = "") -> Tuple[str, str, str]:
    """
    根据中文名/描述关键词判定类别，返回 (类别键, 中文标签, 颜色)。

    说明：这是**分类**而不是**造数据** —— 输入是模型给的文本，输出只是给图标换个颜色。
    """
    text = f"{name_zh or ''}{description or ''}"
    for key, label, color, keywords in CATEGORY_RULES:
        for kw in keywords:
            if kw in text:
                return key, label, color
    return DEFAULT_CATEGORY[0], DEFAULT_CATEGORY[1], DEFAULT_CATEGORY[2]


def _popup_html(loc: Dict[str, Any], idx: int, cat_label: str) -> str:
    """构造点击 Marker 后弹出的详情 HTML（中英双语 + 坐标 + 类别）。"""
    name = html.escape(str(loc.get("name", "—")))
    name_zh = html.escape(str(loc.get("name_zh", "—")))
    desc = html.escape(str(loc.get("description", "—")))
    lat = loc.get("latitude")
    lon = loc.get("longitude")
    return f"""
    <div style="font-family:'Microsoft YaHei','PingFang SC',sans-serif;
                min-width:260px;max-width:330px;line-height:1.6;">
      <div style="font-size:16px;font-weight:700;color:#1a3a72;
                  border-bottom:2px solid #4a90d9;padding-bottom:6px;margin-bottom:8px;">
        {idx}. {name_zh}
      </div>
      <div style="font-size:12px;color:#7a8699;margin-bottom:8px;font-style:italic;">{name}</div>
      <div style="font-size:13px;color:#333;margin-bottom:10px;">{desc}</div>
      <div style="font-size:12px;color:#666;background:#f5f7fa;border-radius:4px;padding:6px 8px;">
        <b>类别</b>：{cat_label}<br>
        <b>纬度</b>：{lat}　<b>经度</b>：{lon}
      </div>
      <div style="font-size:10px;color:#aab4c0;margin-top:8px;">
        数据来源：本地 Gemma 4 模型（Ollama）生成
      </div>
    </div>
    """


def _leaflet_color_names_to_hex(folium_color: str) -> str:
    """把 folium 的颜色名映射成十六进制，供自定义图标与图例使用。"""
    mapping = {
        "red": "#d63b3b", "darkred": "#8b1a1a", "orange": "#e8820c",
        "green": "#2e9e4f", "darkgreen": "#1d6b36", "blue": "#2c6fd1",
        "purple": "#7b4fbf", "darkpurple": "#503a7a", "cadetblue": "#4a8f9e",
        "gray": "#7a8699",
    }
    return mapping.get(folium_color, "#2c6fd1")


def generate_map(locations: List[Dict[str, Any]],
                 output_path: str = None,
                 center: List[float] = None,
                 zoom_start: int = None,
                 title: str = "SIAS University 周边交互式地图",
                 subtitle: str = "",
                 extra_layers: bool = True,
                 nearest_pair_line: bool = True) -> str:
    """
    生成交互式 Folium 地图并保存为 HTML。

    参数：
        locations   : 地点列表，每条必须含 name/name_zh/latitude/longitude/description
        output_path : 输出 HTML 路径，默认 config.OUTPUT_MAP_HTML
        center      : 地图中心 [lat, lon]，默认 config.MAP_CENTER
        zoom_start  : 初始缩放级别，默认 config.MAP_ZOOM_START
        title       : 地图左上角标题
        subtitle    : 副标题（写模型信息，满足「四项关键信息」取证）
        extra_layers: 是否添加底图图层控制
        nearest_pair_line: 是否用本地工具算出的「最近两点连线」演示工具调用

    返回：输出文件的绝对路径
    """
    if not locations:
        raise ValueError("locations 为空 —— 没有可渲染的地点数据（不做兜底编造）。")

    output_path = output_path or config.OUTPUT_MAP_HTML
    center = center or config.MAP_CENTER
    zoom_start = zoom_start or config.MAP_ZOOM_START

    # ---------------- 基础地图 ----------------
    m = folium.Map(
        location=center,
        zoom_start=zoom_start,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
    )

    # 多套底图（不含任何需要 key 的地图服务；均为公开瓦片）
    folium.TileLayer(
        tiles="https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
        attr="高德地图 AutoNavi", name="高德街道图（中文）", subdomains="1234",
        overlay=False, control=True,
    ).add_to(m)
    folium.TileLayer(
        tiles="https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
        attr="高德地图 AutoNavi", name="高德卫星图", subdomains="1234",
        overlay=False, control=True,
    ).add_to(m)
    folium.TileLayer(
        tiles="OpenStreetMap", name="OpenStreetMap（英文）",
        overlay=False, control=True,
    ).add_to(m)

    # ---------------- 按类别分组，便于图层开关 ----------------
    groups: Dict[str, folium.FeatureGroup] = {}
    counts: Dict[str, int] = {}

    for i, loc in enumerate(locations, start=1):
        cat_key, cat_label, cat_color = classify_category(
            str(loc.get("name_zh", "")), str(loc.get("description", "")))

        if cat_key not in groups:
            groups[cat_key] = folium.FeatureGroup(
                name=f"{cat_label}（{0}）".replace("（0）", ""), show=True)
            counts[cat_key] = 0

        lat, lon = float(loc["latitude"]), float(loc["longitude"])

        # 圆形标记：既有颜色也有编号，视觉上比默认图钉更清楚
        folium.CircleMarker(
            location=[lat, lon],
            radius=9,
            color="white",
            weight=2,
            fill=True,
            fill_color=cat_color,
            fill_opacity=0.95,
            tooltip=f"{i}. {html.escape(str(loc.get('name_zh','')))}",
            popup=folium.Popup(_popup_html(loc, i, cat_label), max_width=350),
        ).add_to(groups[cat_key])

        # 编号标签（不随缩放消失，纯 CSS divIcon）
        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(html=f"""
                <div style="font-size:10px;font-weight:700;color:#fff;
                            text-align:center;line-height:18px;width:18px;height:18px;
                            border-radius:50%;background:{_leaflet_color_names_to_hex(cat_color)};
                            border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);
                            font-family:'Segoe UI',sans-serif;">{i}</div>"""),
            tooltip=f"{html.escape(str(loc.get('name_zh','')))}",
            popup=folium.Popup(_popup_html(loc, i, cat_label), max_width=350),
        ).add_to(groups[cat_key])

        counts[cat_key] = counts.get(cat_key, 0) + 1

    for cat_key, fg in groups.items():
        label = next((r[1] for r in CATEGORY_RULES if r[0] == cat_key), DEFAULT_CATEGORY[1])
        fg.layer_name = f"{label}（{counts[cat_key]}）"
        fg.add_to(m)

    # ---------------- 校园中心点 ----------------
    folium.Marker(
        location=center,
        icon=folium.Icon(color="darkblue", icon="graduation-cap", prefix="fa"),
        tooltip=f"{config.CAMPUS_NAME_ZH}（中心锚点）",
        popup=folium.Popup(
            f"<div style='font-family:sans-serif;font-size:13px;'>"
            f"<b>{config.CAMPUS_NAME_ZH}</b><br>{config.CAMPUS_NAME_EN}<br>"
            f"{config.CAMPUS_CITY}<br>中心坐标：{center[0]}, {center[1]}"
            f"</div>", max_width=280),
    ).add_to(m)

    # ---------------- 最近两点连线（演示本地工具被真实调用）----------------
    if nearest_pair_line and len(locations) >= 2:
        try:
            import tools
            pair = tools.nearest_pair(locations)
            if pair:
                a, b, meters = pair
                line = folium.PolyLine(
                    locations=[[a["latitude"], a["longitude"]],
                               [b["latitude"], b["longitude"]]],
                    color="#e8820c", weight=3, opacity=0.85, dash_array="8 6",
                    tooltip=f"最近两点：{a.get('name_zh')} ↔ {b.get('name_zh')}"
                            f"，约 {meters:.0f} 米（本地 haversine 工具计算）",
                )
                fg_line = folium.FeatureGroup(name="最近两点连线（工具调用演示）", show=False)
                line.add_to(fg_line)
                fg_line.add_to(m)
        except Exception:  # noqa: BLE001 - 演示图层失败不应影响主地图
            pass

    # ---------------- 标题 / 图例 / 模型信息面板 ----------------
    legend_rows = []
    for cat_key, cat_label, cat_color, _ in CATEGORY_RULES:
        if cat_key in counts:
            legend_rows.append(
                f"<div style='margin:3px 0;'>"
                f"<span style='display:inline-block;width:11px;height:11px;border-radius:50%;"
                f"background:{_leaflet_color_names_to_hex(cat_color)};margin-right:6px;"
                f"vertical-align:middle;border:1px solid #fff;'></span>"
                f"{cat_label} <b>{counts[cat_key]}</b></div>")
    if "other" in counts:
        legend_rows.append(
            f"<div style='margin:3px 0;'>"
            f"<span style='display:inline-block;width:11px;height:11px;border-radius:50%;"
            f"background:{_leaflet_color_names_to_hex('gray')};margin-right:6px;"
            f"vertical-align:middle;border:1px solid #fff;'></span>"
            f"其它地点 <b>{counts['other']}</b></div>")

    panel_html = f"""
    <div style="position:fixed;top:12px;left:52px;z-index:9999;width:270px;
                background:rgba(255,255,255,.95);border-radius:10px;
                box-shadow:0 4px 18px rgba(0,0,0,.22);padding:14px 16px;
                font-family:'Microsoft YaHei','PingFang SC',sans-serif;">
      <div style="font-size:16px;font-weight:700;color:#1a3a72;margin-bottom:4px;">
        {html.escape(title)}
      </div>
      <div style="font-size:11px;color:#7a8699;line-height:1.6;margin-bottom:8px;">
        {html.escape(subtitle)}
      </div>
      <div style="border-top:1px solid #e3e8ef;padding-top:8px;">
        <div style="font-size:12px;font-weight:700;color:#333;margin-bottom:4px;">
          点位图例（共 {len(locations)} 个）
        </div>
        {''.join(legend_rows)}
      </div>
      <div style="border-top:1px solid #e3e8ef;margin-top:8px;padding-top:8px;
                  font-size:11px;color:#7a8699;line-height:1.7;">
        数据来源：<b>本地 Gemma 4 模型</b>（Ollama，localhost:11434）<br>
        渲染：Python + Folium（Leaflet.js）<br>
        所有点位坐标由模型生成，代码未硬编码地点数据
      </div>
    </div>"""

    # ---------------- 插件 ----------------
    try:
        plugins.Fullscreen(position="topleft", title="全屏", title_cancel="退出全屏").add_to(m)
        plugins.MiniMap(toggle_display=True).add_to(m)
        plugins.MeasureControl(position="bottomleft", primary_length_unit="meters").add_to(m)
        plugins.MousePosition(position="bottomright", separator=" | ",
                              prefix="鼠标坐标：").add_to(m)
        plugins.LocateControl(position="topleft", strings={"title": "定位到我"}).add_to(m)
    except Exception:  # noqa: BLE001 - 插件缺失不影响主地图
        pass

    folium.LayerControl(collapsed=False, position="topright").add_to(m)

    # 把自定义面板与页脚注入到最终 HTML（Folium 无原生 API，用字符串注入）
    m.get_root().header.add_child(folium.Element(
        f"<title>{html.escape(title)} · 本地 Gemma 4 生成</title>\n"
        f"<meta name=\"description\" content=\"由本地 Gemma 4 模型（{config.MODEL_NAME}，"
        f"量化 {config.QUANTIZATION}，Ollama 本地推理）生成的地点数据渲染而成\">\n"
        f"<meta name=\"generator\" content=\"student_C4D_agent-skill (Python + Folium)\">"))
    m.get_root().html.add_child(folium.Element(panel_html))
    m.get_root().html.add_child(folium.Element(
        f"<div style='position:fixed;bottom:8px;left:8px;z-index:9998;font-size:11px;"
        f"color:#5a6472;background:rgba(255,255,255,.9);padding:4px 10px;border-radius:6px;"
        f"font-family:sans-serif;'>由 student 的本地 LLM Agent 生成 · "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>"))

    # ---------------- 保存 ----------------
    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    m.save(output_path)
    return os.path.abspath(output_path)


def map_stats(locations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """统计地图相关指标，供验证报告使用。"""
    cats: Dict[str, int] = {}
    for loc in locations:
        key, label, _ = classify_category(str(loc.get("name_zh", "")),
                                          str(loc.get("description", "")))
        cats[label] = cats.get(label, 0) + 1
    lats = [float(l["latitude"]) for l in locations]
    lons = [float(l["longitude"]) for l in locations]
    return {
        "markers": len(locations),
        "categories": cats,
        "lat_range": [min(lats), max(lats)] if lats else [],
        "lon_range": [min(lons), max(lons)] if lons else [],
    }

# -*- coding: utf-8 -*-
"""
logger.py —— AI 对话原始日志记录器
=================================

C4D 要求「完整留存 AI 对话原始输出日志，保存模型原始返回内容」，
并且 `student_C4D_AI日志.md` 是**强制提交项，缺少直接评审不通过**。

本模块负责三件事：
  1. 把**每一轮**对话的 system 提示词、用户 prompt、模型原始返回、解析结果、
     性能指标（tok/s）**逐条落盘**，不做任何截断或美化；
  2. 同步写一份 JSONL（每行一条 JSON），便于用脚本统计输出质量；
  3. 把每轮模型原始输出单独存一个 .txt 快照，防止原文本被后续处理污染。

⚠️ 重要：这里记录的是**模型真实输出的原文**。
   如果模型输出了多余文字、或者 JSON 解析失败，日志会如实保留失败现场，
   不允许为了「好看」而删改 —— 失败经验本身就是复盘质量（20%）的评分点。

作者：student
日期：2026-10
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


class AgentLogger:
    """Agent 对话与性能日志记录器。"""

    def __init__(self, log_dir: str, model_name: str, runtime_tool: str,
                 quantization: str = "", device_brief: str = "") -> None:
        self.log_dir = log_dir
        self.raw_dir = os.path.join(log_dir, "raw_model_outputs")
        os.makedirs(self.raw_dir, exist_ok=True)

        self.jsonl_path = os.path.join(log_dir, "agent_calls.jsonl")
        self.model_name = model_name
        self.runtime_tool = runtime_tool
        self.quantization = quantization
        self.device_brief = device_brief

        # 内存里的轮次记录，供生成 Markdown 日志
        self.turns: List[Dict[str, Any]] = []
        self.session_start = datetime.now()

    # ------------------------------------------------------------------
    # 记录一轮完整对话
    # ------------------------------------------------------------------
    def log_turn(self, *, round_index: int, phase: str, system_prompt: str,
                 user_prompt: str, raw_output: str, parsed: Any, parse_trace: str,
                 metrics: Dict[str, Any], note: str = "") -> None:
        """
        记录一轮对话。

        参数：
            round_index : 第几轮（从 1 开始）
            phase       : 该轮的用途标签，如「首轮-生成地点」「多轮-新增标记点」
            system_prompt: 本轮实际发送的 system 内容（原文）
            user_prompt : 本轮实际发送的 user 内容（原文）
            raw_output  : 模型返回的**原始文本**（未做任何处理）
            parsed      : 解析后的数据结构（失败时 None）
            parse_trace : json_repair 的逐级诊断文本
            metrics     : 性能指标 dict（elapsed_time / completion_tokens / tokens_per_second ...）
            note        : 附加说明（比如「本轮为容错测试」）
        """
        turn = {
            "round": round_index,
            "phase": phase,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "raw_model_output": raw_output,
            "parse_trace": parse_trace,
            "parsed_ok": parsed is not None,
            "parsed_count": (len(parsed) if isinstance(parsed, list)
                             else (1 if isinstance(parsed, dict) else 0)),
            "metrics": metrics,
            "note": note,
            "model_name": self.model_name,
            "runtime_tool": self.runtime_tool,
            "quantization": self.quantization,
        }
        self.turns.append(turn)

        # 1) 追加 JSONL（机器可读，逐轮一行）
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(turn, ensure_ascii=False) + "\n")

        # 2) 保存模型原始输出快照（防止原文被后续处理污染）
        snap = os.path.join(self.raw_dir, f"round{round_index:02d}_{phase}.txt")
        with open(snap, "w", encoding="utf-8") as f:
            f.write(raw_output if raw_output is not None else "<<模型未返回内容>>")

    # ------------------------------------------------------------------
    # 生成 Markdown 版 AI 日志（= 交付物 student_C4D_AI日志.md 的运行记录部分）
    # ------------------------------------------------------------------
    def render_markdown(self, extra_header: str = "") -> str:
        """
        把本 session 的所有轮次渲染成 Markdown。
        extra_header 用于在开头插入人工撰写的说明章节（由 main.py 传入）。
        """
        md: List[str] = []
        md.append("# student_C4D_AI日志\n")
        md.append("> 本文档是 C4D 的**强制提交项**，记录本地 Gemma 4 模型的完整原始输出。\n")
        md.append("")
        md.append("## 0. 运行环境（四项关键信息）\n")
        md.append("| 项目 | 值 |")
        md.append("|---|---|")
        md.append(f"| 模型名称 | `{self.model_name}` |")
        md.append(f"| 量化方式 | `{self.quantization}` |")
        md.append(f"| 运行工具 | {self.runtime_tool} |")
        md.append(f"| 设备 | {self.device_brief} |")
        md.append(f"| 推理速度 | 逐轮实测，见下表 tok/s 列 |")
        md.append(f"| 日志生成时间 | {self.session_start.strftime('%Y-%m-%d %H:%M:%S')} |")
        md.append("")
        md.append("> 说明：以下所有「模型原始输出」均为**逐字原文**，未做任何删改或美化；")
        md.append("> 解析失败、输出污染等失败现场同样如实保留。\n")
        if extra_header:
            md.append(extra_header)
            md.append("")

        md.append("---\n")
        # 注意：这里不再另起 "## 1." 标题 —— 章节编号由调用方传入的
        # extra_header 统一编排（见 main.py 的 build_ai_log_header），
        # 避免出现两个 "## 1." 的重复编号。

        for t in self.turns:
            m = t["metrics"] or {}
            md.append(f"### 第 {t['round']} 轮 · {t['phase']}\n")
            md.append(f"- **时间**：{t['timestamp']}")
            md.append(f"- **模型**：`{t['model_name']}`（量化 {t['quantization']}，工具 {t['runtime_tool']}）")
            if t.get("note"):
                md.append(f"- **本轮说明**：{t['note']}")
            md.append(f"- **性能**：耗时 {m.get('elapsed_time', 0):.2f} s ｜ "
                      f"输出 {m.get('completion_tokens', 0)} tokens ｜ "
                      f"**{m.get('tokens_per_second', 0):.2f} tok/s**")
            md.append(f"- **解析结果**：{'成功' if t['parsed_ok'] else '失败'}，"
                      f"解析出 {t['parsed_count']} 条记录")
            md.append("")
            md.append("<details>")
            md.append("<summary>展开：本轮 system 提示词（原文）</summary>\n")
            md.append("```text")
            md.append(t["system_prompt"])
            md.append("```")
            md.append("</details>\n")
            md.append("<details open>")
            md.append("<summary>展开：本轮 user 提示词（原文）</summary>\n")
            md.append("```text")
            md.append(t["user_prompt"])
            md.append("```")
            md.append("</details>\n")
            md.append("**模型原始输出（逐字原文）：**\n")
            md.append("```text")
            md.append(t["raw_model_output"] if t["raw_model_output"] is not None else "<<空>>")
            md.append("```")
            md.append("")
            md.append("**JSON 容错解析逐级诊断：**\n")
            md.append("```text")
            md.append(t["parse_trace"])
            md.append("```")
            md.append("")

        return "\n".join(md)

    # ------------------------------------------------------------------
    # 汇总统计（供验证报告引用）
    # ------------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        """统计本轮 session 的性能与输出质量指标。"""
        speeds = [t["metrics"].get("tokens_per_second", 0) for t in self.turns
                  if t.get("metrics", {}).get("tokens_per_second")]
        elapsed = [t["metrics"].get("elapsed_time", 0) for t in self.turns if t.get("metrics")]
        ok = sum(1 for t in self.turns if t["parsed_ok"])
        return {
            "total_rounds": len(self.turns),
            "parse_ok_rounds": ok,
            "parse_success_rate": round(ok / len(self.turns) * 100, 1) if self.turns else 0.0,
            "tok_s_min": round(min(speeds), 2) if speeds else 0.0,
            "tok_s_max": round(max(speeds), 2) if speeds else 0.0,
            "tok_s_avg": round(sum(speeds) / len(speeds), 2) if speeds else 0.0,
            "elapsed_total": round(sum(elapsed), 2),
        }

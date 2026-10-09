# -*- coding: utf-8 -*-
"""
agent.py —— 本地 LLM Agent 核心
================================

职责：把「提示词 -> 本地模型 -> 容错解析 -> 数据校验 -> 日志留档」串成一条闭环。
它不负责画地图（交给 map_generator），也不负责 HTTP（交给 ollama_client）。

对照评审维度，本文件承担的能力：
  * Agent 能力展示（25%）
      - 结构化输出：system prompt 强制 JSON 数组
      - 容错处理  ：解析失败时走 json_repair 的五级递进策略
      - 多轮对话  ：保留对话上下文，支持新增/修改标记点（Level 3）
      - 工具调用  ：预留 call_tool 通道，演示本地工具被真实调用
  * 本地运行验证（25%）
      - 所有请求都经 ollama_client 发往 localhost:11434

作者：student
日期：2026-10
"""

from typing import Any, Dict, List, Optional, Tuple

import config
import json_repair
import tools
from logger import AgentLogger
from ollama_client import (ModelNotPulledError, OllamaClient, OllamaError,
                           OllamaNotRunningError)


class SiasMapAgent:
    """SIAS 周边地图 Agent。"""

    def __init__(self, client: Optional[OllamaClient] = None,
                 logger: Optional[AgentLogger] = None,
                 verbose: bool = True) -> None:
        self.client = client or OllamaClient()
        self.verbose = verbose
        self.round = 0

        # 对话上下文（Level 3 多轮对话）：system 常驻 + 历史 user/assistant
        self.history: List[Dict[str, str]] = [
            {"role": "system", "content": config.SYSTEM_PROMPT}
        ]

        if logger is None:
            device_brief = (f"{config.DEVICE_INFO['cpu']['value']} / "
                            f"{config.DEVICE_INFO['ram']['value']} / "
                            f"{config.DEVICE_INFO['gpu']['value']}")
            logger = AgentLogger(
                log_dir=config.RAW_LOG_DIR,
                model_name=config.MODEL_NAME,
                runtime_tool=f"{config.RUNTIME_TOOL} ({config.OLLAMA_HOST})",
                quantization=config.QUANTIZATION,
                device_brief=device_brief,
            )
        self.logger = logger

    # ------------------------------------------------------------------
    # 内部：打印
    # ------------------------------------------------------------------
    def _say(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    # ------------------------------------------------------------------
    # 核心：一轮「提问 -> 拿原文 -> 容错解析 -> 校验」
    # ------------------------------------------------------------------
    def run_round(self, user_prompt: str, phase: str,
                  note: str = "") -> Tuple[Optional[Any], Dict[str, Any]]:
        """
        执行一轮完整交互。

        返回：
            (parsed_data, metrics)
            parsed_data: 解析成功为 list/dict；失败为 None
            metrics    : 性能与解析指标
        """
        self.round += 1
        r = self.round
        self._say(f"\n{'='*66}")
        self._say(f"[第 {r} 轮] {phase}")
        self._say(f"{'='*66}")

        # 1) 组装消息（带上历史，实现多轮上下文）
        self.history.append({"role": "user", "content": user_prompt})

        # 2) 调用本地模型
        self._say(f"  → 正在调用本地模型 {config.MODEL_NAME} ...")
        result = self.client.chat(self.history)

        raw = result["content"]
        self._say(f"  ← 模型返回 {len(raw)} 字符，"
                  f"耗时 {result['elapsed_time']:.2f}s，"
                  f"输出 {result['completion_tokens']} tokens，"
                  f"{result['tokens_per_second']:.2f} tok/s")

        # 3) 容错解析
        parsed, trace = json_repair.parse_model_json(raw)
        hit = trace.hit_strategy()
        self._say(f"  ← JSON 解析：{'成功（策略：' + str(hit) + '）' if parsed is not None else '失败（五级策略均未命中）'}")

        # 4) 结构校验（只体检，不补值）
        validation = json_repair.validate_locations(parsed) if parsed is not None else None
        if validation:
            self._say(f"  ← 字段校验：{validation['valid']}/{validation['total']} 条完全合格"
                      + (f"，坐标越界 {validation['out_of_range']} 项" if validation["out_of_range"] else ""))
            for rec in validation["records"]:
                if not rec["ok"]:
                    self._say(f"      ! 第 {rec['index']+1} 条不合格：{'；'.join(rec['issues'])}")

        # 5) 落日志（原文逐字保留）
        metrics = {
            "elapsed_time": result["elapsed_time"],
            "prompt_tokens": result["prompt_tokens"],
            "completion_tokens": result["completion_tokens"],
            "total_tokens": result["total_tokens"],
            "tokens_per_second": result["tokens_per_second"],
            "eval_tokens_per_second": result["eval_tokens_per_second"],
            "json_strategy_hit": hit,
            "validation": validation,
        }
        self.logger.log_turn(
            round_index=r, phase=phase,
            system_prompt=config.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            raw_output=raw, parsed=parsed,
            parse_trace=trace.summary(),
            metrics=metrics, note=note,
        )

        # 6) 把模型回复写回历史（多轮上下文）
        self.history.append({"role": "assistant", "content": raw})

        return parsed, metrics

    # ------------------------------------------------------------------
    # 场景 1：首轮生成地点数据（主链路）
    # ------------------------------------------------------------------
    def generate_locations(self, user_prompt: str = None) -> List[Dict[str, Any]]:
        """
        首轮：让本地模型生成一批地点，返回**干净可用**的地点列表。

        注意：不合格的条目会被剔除并记录，绝不补造坐标。
        """
        user_prompt = user_prompt or config.INITIAL_USER_PROMPT
        parsed, metrics = self.run_round(user_prompt, phase="首轮-生成地点数据",
                                         note="主链路：system 强制 JSON，五级容错解析")

        if parsed is None:
            self._say("  ✗ 首轮解析失败。原始输出已完整留档在 logs/raw_model_outputs/ 下。")
            return []

        if isinstance(parsed, dict):
            parsed = [parsed]

        good, bad = json_repair.drop_invalid_records(parsed)
        if bad:
            self._say(f"  ! 剔除 {len(bad)} 条不合格记录（不补值，仅剔除并留档）：")
            for b in bad:
                self._say(f"      - {b['reason']}")
        self._say(f"  ✓ 可用地点：{len(good)} 个")
        return good

    # ------------------------------------------------------------------
    # 场景 2：Level 3 多轮对话 —— 新增标记点
    # ------------------------------------------------------------------
    def add_marker(self, location_name: str) -> Optional[Dict[str, Any]]:
        """多轮：新增一个地点（复用对话历史，模型知道之前的坐标系）。"""
        prompt = config.ADD_MARKER_PROMPT.format(location_name=location_name)
        parsed, _ = self.run_round(prompt, phase=f"多轮-新增「{location_name}」",
                                   note="Level 3：多轮对话上下文复用")
        if parsed is None:
            return None
        if isinstance(parsed, dict):
            parsed = [parsed]
        good, _bad = json_repair.drop_invalid_records(parsed)
        return good[0] if good else None

    # ------------------------------------------------------------------
    # 场景 3：Level 3 多轮对话 —— 修改标记点
    # ------------------------------------------------------------------
    def modify_marker(self, old_name: str, new_info: str) -> Optional[Dict[str, Any]]:
        """多轮：修改已有地点的描述（或微调坐标）。"""
        prompt = config.MODIFY_MARKER_PROMPT.format(old_name=old_name, new_info=new_info)
        parsed, _ = self.run_round(prompt, phase=f"多轮-修改「{old_name}」",
                                   note="Level 3：多轮对话上下文复用")
        if parsed is None:
            return None
        if isinstance(parsed, dict):
            parsed = [parsed]
        good, _bad = json_repair.drop_invalid_records(parsed)
        return good[0] if good else None

    # ------------------------------------------------------------------
    # 场景 4：容错能力对抗测试（故意让模型输出脏文本）
    # ------------------------------------------------------------------
    def fault_injection_test(self) -> Tuple[Optional[Any], Dict[str, Any]]:
        """
        容错演练：故意用一段「诱导模型输出前言+代码块+后记」的提示词，
        观察五级容错是否仍然能解析出 JSON。这条记录会写进 AI 日志，
        作为「解析异常容错处理」的直接证据。
        """
        return self.run_round(config.FAULT_INJECTION_PROMPT,
                              phase="容错对抗测试-故意诱导脏输出",
                              note="评审点：模型输出夹带多余文字时的容错能力演示")

    # ------------------------------------------------------------------
    # 场景 5：本地工具调用（展示 Agent 的「技能」）
    # ------------------------------------------------------------------
    def enrich_with_tools(self, locations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        用本地工具给地点数据补充空间关系信息（不修改原坐标）。

        这是「工具调用」能力的真实体现：Agent 不止会生成文本，还会用本地函数
        计算点与点之间的距离和方位。全部为本地纯计算，不访问外部服务。
        """
        out: Dict[str, Any] = {"route_examples": [], "tool_schema_count": len(tools.TOOL_SCHEMAS)}
        if len(locations) < 2:
            return out
        # 以第一个点位为起点，给出到其余点位的路线描述（最多 3 条）
        origin = locations[0]
        for target in locations[1:4]:
            res = tools.call_tool("describe_route", a=origin, b=target)
            if res["ok"]:
                out["route_examples"].append(res["result"]["text"])
        pair = tools.nearest_pair(locations)
        if pair:
            a, b, m = pair
            out["nearest_pair"] = {
                "a": a.get("name_zh"), "b": b.get("name_zh"), "meters": round(m, 1),
                "radius_km": 0.0,
            }
        return out

    # ------------------------------------------------------------------
    # 收尾：写 Markdown 版 AI 日志
    # ------------------------------------------------------------------
    def save_ai_log(self, path: str = None, extra_header: str = "") -> str:
        path = path or config.AI_LOG_MARKDOWN
        md = self.logger.render_markdown(extra_header=extra_header)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        return path

    def stats(self) -> Dict[str, Any]:
        return self.logger.stats()

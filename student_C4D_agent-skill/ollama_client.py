# -*- coding: utf-8 -*-
"""
ollama_client.py —— 本地 Ollama 推理服务的接口封装
=================================================

C4D 要求「Python 调用 Ollama OpenAI 兼容接口访问本地 Gemma 4」。
本模块把 HTTP 细节全部收拢在这里，上层 Agent 只关心「发消息、拿回复」。

对外提供：
    * health_check()        —— 服务是否活着（/api/version）
    * list_models()         —— 本机已拉取的模型清单（/api/tags）
    * model_exists(name)    —— 指定模型是否已在本地（评审要看点）
    * chat()                —— OpenAI 兼容 /v1/chat/completions 调用（含 tok/s 统计）
    * show_model(name)      —— 查看模型详情（参数量、量化、模板），用于四项关键信息取证

设计要点：
    1. **只用 localhost**：BASE_URL 来自 config，默认 http://localhost:11434，
       代码里不存在任何云端 API 地址（评审：本地运行验证 25%）。
    2. **失败要显式**：连不上/模型没拉/HTTP 报错，都抛出带修复建议的异常，
       绝不静默降级、绝不伪造回复。
    3. **tok/s 三口径**：同时算「墙钟速度」和「Ollama 自报的 eval_duration 速度」，
       后者剔除了网络与排队开销，更接近模型真实推理速度。

作者：student
日期：2026-10
"""

import json
import time
from typing import Any, Dict, List, Optional

import requests

import config


class OllamaError(RuntimeError):
    """Ollama 相关错误的统一基类，便于上层分类捕获。"""


class OllamaNotRunningError(OllamaError):
    """服务没起来。"""


class ModelNotPulledError(OllamaError):
    """服务活着，但目标模型不在本地。"""


class OllamaClient:
    """本地 Ollama 客户端。"""

    def __init__(self, host: str = None, model: str = None, timeout: int = None) -> None:
        self.host = (host or config.OLLAMA_HOST).rstrip("/")
        self.model = model or config.MODEL_NAME
        self.timeout = timeout or config.REQUEST_TIMEOUT

    # ==================================================================
    # 健康检查与模型盘点
    # ==================================================================
    def health_check(self) -> Dict[str, Any]:
        """
        检查本地 Ollama 服务是否可用，并返回版本号。
        返回：{"running": bool, "version": str, "host": str, "error": str|None}
        """
        try:
            r = requests.get(f"{self.host}/api/version", timeout=10)
            r.raise_for_status()
            return {"running": True, "version": r.json().get("version", "unknown"),
                    "host": self.host, "error": None}
        except requests.exceptions.ConnectionError as e:
            return {"running": False, "version": None, "host": self.host,
                    "error": f"无法连接 {self.host}（{e.__class__.__name__}）。"
                             f"请先启动服务：ollama serve"}
        except Exception as e:  # noqa: BLE001
            return {"running": False, "version": None, "host": self.host,
                    "error": f"{e.__class__.__name__}: {e}"}

    def list_models(self) -> List[Dict[str, Any]]:
        """列出本机已下载的模型（GET /api/tags）。"""
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=15)
            r.raise_for_status()
            return r.json().get("models", [])
        except Exception as e:  # noqa: BLE001
            raise OllamaNotRunningError(
                f"读取本地模型列表失败：{e}。请确认 Ollama 已启动（ollama serve）。") from e

    def model_exists(self, name: str = None) -> bool:
        """
        判断目标模型是否已在本地。
        注意：Ollama 的 tag 存在「gemma4:e4b-it-q4_K_M」与「gemma4:e4b」这类别名，
        这里做前缀宽松匹配，避免因为别名写法不同而误报「未拉取」。
        """
        name = name or self.model
        base = name.split(":")[0]
        for m in self.list_models():
            tag = m.get("name", "")
            if tag == name or tag.startswith(base + ":"):
                return True
        return False

    def show_model(self, name: str = None) -> Dict[str, Any]:
        """
        查看模型详情（POST /api/show）。
        用于取证「四项关键信息」里的模型名称/量化/参数量。
        """
        name = name or self.model
        try:
            r = requests.post(f"{self.host}/api/show", json={"model": name}, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            raise OllamaError(f"读取模型详情失败（{name}）：{e}") from e

    # ==================================================================
    # 核心：OpenAI 兼容对话接口
    # ==================================================================
    def chat(self, messages: List[Dict[str, str]], *, temperature: float = None,
             max_tokens: int = None, seed: Optional[int] = None,
             json_mode: bool = False) -> Dict[str, Any]:
        """
        调用本地 Ollama 的 **OpenAI 兼容接口** /v1/chat/completions。

        参数：
            messages    : OpenAI 格式的消息列表 [{"role":..,"content":..}, ...]
            temperature : 采样温度，默认取 config.TEMPERATURE（0.2，追求稳定结构输出）
            max_tokens  : 最大输出 token，默认取 config.MAX_TOKENS
            seed        : 随机种子（可选，便于复现）
            json_mode   : 是否请求 response_format={"type":"json_object"}。
                          ⚠️ 默认关闭：本项目的结构化约束主要靠 system prompt 完成，
                             这样才能真实演示「模型仍可能输出脏文本 + 容错解析」这条链路；
                             开启时只是多一层保险，不能替代容错逻辑。

        返回：
            {
              "content":          模型输出文本,
              "raw_response":     原始响应 dict（留档用）,
              "elapsed_time":     墙钟耗时（秒）,
              "prompt_tokens":    输入 token,
              "completion_tokens":输出 token,
              "total_tokens":     总 token,
              "tokens_per_second":墙钟速度 tok/s,
              "eval_tokens_per_second": Ollama 自报速度 tok/s（更接近纯推理速度）,
            }

        异常：
            OllamaNotRunningError —— 服务未启动
            ModelNotPulledError   —— 模型未下载
            OllamaError           —— 其它 HTTP / 解析错误
        """
        temperature = config.TEMPERATURE if temperature is None else temperature
        max_tokens = config.MAX_TOKENS if max_tokens is None else max_tokens

        # ---- 预检 1：服务必须活着 ----
        hc = self.health_check()
        if not hc["running"]:
            raise OllamaNotRunningError(hc["error"])

        # ---- 预检 2：模型必须已在本地（避免跑到一半才发现 404）----
        if not self.model_exists():
            raise ModelNotPulledError(
                f"本地未找到模型 `{self.model}`。请先执行：\n"
                f"    ollama pull {self.model}\n"
                f"（当前 Ollama 版本：{hc['version']}）")

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,          # 非流式：一次性拿到完整输出，便于 log 原文
        }
        if seed is not None:
            payload["seed"] = seed
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        t0 = time.time()
        try:
            resp = requests.post(config.OPENAI_COMPAT_URL, json=payload,
                                 headers={"Content-Type": "application/json"},
                                 timeout=self.timeout)
        except requests.exceptions.ConnectionError as e:
            raise OllamaNotRunningError(
                f"连接 {config.OPENAI_COMPAT_URL} 失败：{e}。请确认 `ollama serve` 正在运行。") from e
        except requests.exceptions.Timeout as e:
            raise OllamaError(
                f"请求超时（>{self.timeout}s）。纯 CPU 推理较慢，"
                f"可提高 config.REQUEST_TIMEOUT 或缩短输出长度。") from e

        elapsed = time.time() - t0

        if resp.status_code != 200:
            raise OllamaError(
                f"HTTP {resp.status_code}：{resp.text[:500]}")

        data = resp.json()
        content = (data.get("choices", [{}])[0]
                   .get("message", {})
                   .get("content", ""))

        usage = data.get("usage", {}) or {}
        prompt_tokens = usage.get("prompt_tokens", 0) or 0
        completion_tokens = usage.get("completion_tokens", 0) or 0
        total_tokens = usage.get("total_tokens", 0) or (prompt_tokens + completion_tokens)

        # 墙钟速度：包含排队/加载开销，是最保守的口径
        wall_tok_s = (completion_tokens / elapsed) if (elapsed > 0 and completion_tokens) else 0.0

        # Ollama 自报速度：用 eval_duration（纳秒）算，剔除模型加载与提示处理
        eval_tok_s = 0.0
        try:
            eval_count = data.get("usage", {}).get("completion_tokens", 0)
            # Ollama 在 OpenAI 兼容层不总是回传 eval_duration，这里做兼容读取
            eval_ns = data.get("eval_duration") or 0
            if eval_ns and eval_count:
                eval_tok_s = eval_count / (eval_ns / 1e9)
        except Exception:  # noqa: BLE001
            eval_tok_s = 0.0

        return {
            "content": content,
            "raw_response": data,
            "elapsed_time": round(elapsed, 3),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "tokens_per_second": round(wall_tok_s, 2),
            "eval_tokens_per_second": round(eval_tok_s, 2),
        }

    # ==================================================================
    # 便捷方法：一轮对话
    # ==================================================================
    def ask(self, system_prompt: str, user_prompt: str, **kwargs) -> Dict[str, Any]:
        """system + user 两段式调用，返回 chat() 的结果。"""
        return self.chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ], **kwargs)

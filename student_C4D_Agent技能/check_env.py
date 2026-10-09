# -*- coding: utf-8 -*-
"""
check_env.py —— 环境自检与「四项关键信息」取证
=============================================

C4D 评审硬性要求：截图/录屏必须清晰显示
    ① 模型名称及版本  ② 运行工具（Ollama）
    ③ 设备信息（CPU/GPU/内存/OS）  ④ 推理速度 tok/s

本脚本一条命令把四项信息全部打印出来，并**实测**一次最小推理算出真实 tok/s，
输出可直接作为截图素材。同时把结果写入 logs/env_report.json 供文档引用。

用法：
    python check_env.py

作者：student
日期：2026-10
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime

# 允许直接用 python check_env.py 运行（无需包结构）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
from ollama_client import OllamaClient, OllamaError  # noqa: E402


LINE = "=" * 74


def _hr(title: str = "") -> None:
    if title:
        print(f"\n{LINE}\n  {title}\n{LINE}")
    else:
        print(LINE)


def detect_hardware() -> dict:
    """
    自动探测硬件信息。
    Windows 下用 wmic/PowerShell 可能被限制，这里做「多路探测 + 优雅降级」：
    能探测到就填实际值，探测不到就保留 config 里的值并标注为「需人工确认」。
    """
    info = {}
    info["os"] = f"{platform.system()} {platform.release()} ({platform.version()})"
    info["python"] = sys.version.split()[0]
    info["machine"] = platform.machine()

    # CPU
    cpu = platform.processor() or platform.machine()
    cores = os.cpu_count()
    info["cpu"] = cpu
    info["cpu_logical"] = cores

    # 精确型号：读注册表（Windows，无需管理员）
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        info["cpu"] = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        winreg.CloseKey(key)
    except Exception:  # noqa: BLE001
        pass

    # 内存（Windows 用 ctypes 读 GlobalMemoryStatusEx，零依赖）
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        info["ram_total_gb"] = round(stat.ullTotalPhys / 1024 ** 3, 2)
        info["ram_free_gb"] = round(stat.ullAvailPhys / 1024 ** 3, 2)
        info["ram_load_pct"] = stat.dwMemoryLoad
    except Exception:  # noqa: BLE001
        info["ram_total_gb"] = None

    # GPU：优先用 nvidia-smi（独显），否则读注册表/系统描述（核显）
    gpu_list = []
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                                  "--format=csv,noheader"],
                                 capture_output=True, text=True, timeout=15)
            for line in out.stdout.strip().splitlines():
                gpu_list.append(line.strip())
        except Exception:  # noqa: BLE001
            pass
    if not gpu_list:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"SYSTEM\CurrentControlSet\Control\Class"
                                 r"\{4d36e968-e325-11ce-bfc1-08002be10318}")
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, i)
                    sk = winreg.OpenKey(key, sub)
                    desc = winreg.QueryValueEx(sk, "DriverDesc")[0]
                    gpu_list.append(desc)
                    i += 1
                except OSError:
                    break
        except Exception:  # noqa: BLE001
            pass
    info["gpu"] = gpu_list or ["未探测到（请手动补全）"]

    # 磁盘剩余
    try:
        total, used, free = shutil.disk_usage(os.path.abspath(os.sep))
        info["disk_free_gb"] = round(free / 1024 ** 3, 1)
    except Exception:  # noqa: BLE001
        info["disk_free_gb"] = None

    return info


def main() -> int:
    report = {"checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    _hr("C4D 环境自检 —— 四项关键信息取证")
    print(f"  检查时间：{report['checked_at']}")

    # ---------------- ① 硬件 ----------------
    _hr("[③ 设备信息]")
    hw = detect_hardware()
    report["hardware"] = hw
    print(f"  操作系统    : {hw.get('os')}")
    print(f"  Python      : {hw.get('python')}")
    print(f"  CPU         : {hw.get('cpu')}")
    print(f"  CPU 逻辑核  : {hw.get('cpu_logical')}")
    ram = hw.get("ram_total_gb")
    print(f"  内存        : {ram} GB（可用 {hw.get('ram_free_gb')} GB，"
          f"占用 {hw.get('ram_load_pct')}%）" if ram else "  内存        : 探测失败")
    print(f"  GPU         : {'; '.join(hw.get('gpu', []))}")
    print(f"  磁盘剩余    : {hw.get('disk_free_gb')} GB")
    if not shutil.which("nvidia-smi"):
        print("  → 未检测到 NVIDIA 独显，本机走 **CPU 推理**（llama.cpp CPU backend）")

    # ---------------- ② 运行工具 ----------------
    _hr("[② 运行工具 Ollama]")
    client = OllamaClient()
    hc = client.health_check()
    report["ollama"] = hc
    if not hc["running"]:
        print(f"  ✗ Ollama 未运行：{hc['error']}")
        print("\n  请先启动服务：")
        print("      ollama serve")
        print("  再重新运行本脚本。")
        _save(report)
        return 1
    print(f"  ✓ Ollama 正在运行")
    print(f"  服务地址    : {hc['host']}")
    print(f"  版本        : {hc['version']}")

    # ---------------- ③ 模型清单 ----------------
    _hr("[① 模型名称及版本]")
    try:
        models = client.list_models()
    except OllamaError as e:
        print(f"  ✗ 读取模型列表失败：{e}")
        _save(report)
        return 1

    if not models:
        print("  ✗ 本地还没有任何模型。请执行：")
        print(f"      ollama pull {config.MODEL_NAME}")
        _save(report)
        return 1

    print(f"  本机已下载 {len(models)} 个模型：")
    for m in models:
        size_gb = m.get("size", 0) / 1024 ** 3
        print(f"    - {m.get('name','?'):<34} {size_gb:6.2f} GB   "
              f"量化={m.get('details',{}).get('quantization_level','?')}")

    target_ok = client.model_exists()
    report["target_model"] = config.MODEL_NAME
    report["target_model_present"] = target_ok
    print()
    if target_ok:
        print(f"  ✓ 目标模型已在本地：{config.MODEL_NAME}")
    else:
        print(f"  ✗ 目标模型 {config.MODEL_NAME} 不在本地，请执行："
              f" ollama pull {config.MODEL_NAME}")
        _save(report)
        return 1

    # 模型详情：参数量 / 量化 / 参数
    try:
        detail = client.show_model()
        report["model_detail_keys"] = list(detail.keys())
        det = detail.get("details", {})
        print(f"  模型家族    : {det.get('family','?')}")
        print(f"  参数规模    : {det.get('parameter_size','?')}")
        print(f"  量化级别    : {det.get('quantization_level','?')}")
        print(f"  模型格式    : {det.get('format','?')}")
        report["model_details"] = det
    except OllamaError as e:
        print(f"  (模型详情读取失败：{e})")

    # ---------------- ④ 推理速度实测 ----------------
    _hr("[④ 推理速度实测 tok/s]")
    print("  正在发送一条最小请求实测速度（首次会包含模型加载时间，请稍候）...")
    print("  提示：纯 CPU 推理首次加载可能需要 30~120 秒。\n")
    try:
        t0 = time.time()
        res = client.chat(
            [{"role": "system", "content": "你是测试助手，只回答 JSON。"},
             {"role": "user",
              "content": '请只输出一个 JSON：{"status":"ok","model":"gemma4"}，不要有任何其他文字。'}],
            temperature=0.0, max_tokens=64)
        load_note = time.time() - t0
        print(f"  模型输出    : {res['content'].strip()[:200]}")
        print(f"  总耗时      : {res['elapsed_time']:.2f} s（含首次加载）")
        print(f"  输出 token  : {res['completion_tokens']}")
        print(f"  墙钟速度    : {res['tokens_per_second']:.2f} tok/s")
        if res["eval_tokens_per_second"]:
            print(f"  纯推理速度  : {res['eval_tokens_per_second']:.2f} tok/s"
                  f"（Ollama 自报，剔除加载开销）")
        report["speed_test"] = res
    except OllamaError as e:
        print(f"  ✗ 实测失败：{e}")
        report["speed_test"] = {"error": str(e)}

    # ---------------- 汇总 ----------------
    _hr("四项关键信息汇总（截图时请确保这四项都可见）")
    print(f"  ① 模型      : {config.MODEL_NAME}")
    print(f"  ② 运行工具  : {config.RUNTIME_TOOL} v{hc['version']}  @ {hc['host']}")
    print(f"  ③ 设备      : {hw.get('cpu')} / {hw.get('ram_total_gb')}GB / "
          f"{'; '.join(hw.get('gpu', []))}")
    sp = report.get("speed_test", {})
    if isinstance(sp, dict) and sp.get("tokens_per_second"):
        print(f"  ④ 推理速度  : {sp['tokens_per_second']:.2f} tok/s（墙钟）"
              + (f" / {sp['eval_tokens_per_second']:.2f} tok/s（纯推理）"
                 if sp.get("eval_tokens_per_second") else ""))
    else:
        print(f"  ④ 推理速度  : <<未测出，请查看上面的错误信息>>")
    print()

    _save(report)
    return 0


def _save(report: dict) -> None:
    os.makedirs(config.RAW_LOG_DIR, exist_ok=True)
    path = os.path.join(config.RAW_LOG_DIR, "env_report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  自检报告已保存：{path}")


if __name__ == "__main__":
    sys.exit(main())

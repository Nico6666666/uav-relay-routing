"""
性能调度 —— 硬件探测 + 成本模型 + 自适应并行决策。

定位
----
「根据当前电脑配置自适应规划并行」的唯一入口。三件事：

    1. 探测当前机器硬件（逻辑核 / 物理核 / 内存 / 平台 / Python 版本）；
    2. 实测并缓存「单次评估冷/热成本 + 子进程重建开销」——这些是机器相关的，不能写死；
    3. 给出自适应建议：并行进程数 P、是否值得并行、（可选）墙钟估计。

原则（与《联合调度与中继进度与待办.md》§七.5 一致）
----------------------------------------
    * 并行只许改「怎么算得快」，不许改「算什么」：进程数 / 块大小 / 档位都不影响结果，
      结果逐位一致由 `联合调度求解.并行一致性检查` 回归。
    * 探测 / 校准失败一律回退保守默认（串行），绝不因本模块崩溃。
    * 本模块不 import 任何物理 / 通信 / 评价公式；校准用的重对象一律惰性导入。

成本模型（对一批 N 次独立评价）
------------------------------
    串行  T_serial ≈ N × T_hot
    并行  T_par    ≈ T_init + N × T_hot / P          （T_init 为 spawn 池固定开销）
    并行划算 ⇔  N > T_init / (T_hot × (1 − 1/P))

实测先验（2026-09-25，24 逻辑核 / Windows / study_py311）：
    T_cold ≈ 5.44 s，T_hot ≈ 0.44 s，T_init(4 进程) ≈ 1.5 s。
    串行 vs 并行(6 进程) 在 48 次评价上实测 1.75×；6~12 进程基本饱和、20 进程退到 1.56×
    ⇒ 默认进程数上限取 8（物理核通常 ≪ 逻辑核，超线程下用满逻辑核会争抢）。

调用方约定
----------
    探测失败或 psutil 缺失时自动降级：物理核按「逻辑核 // 2」估计、内存视为充足。
    校准应只在主程序启动时显式调用一次（`校准性能`），缓存命中后零额外开销。
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


# ===================== 成本常量 =====================
@dataclass(frozen=True)
class 成本常量:
    """一批独立评价的成本模型参数（机器相关，宜由 `校准性能` 实测覆盖）。"""

    单次评估冷_s: float = 5.44
    单次评估热_s: float = 0.44
    子进程重建_s: float = 1.5       # spawn 池 + worker 重建场景/剖面表的固定开销
    进程数上限: int = 8             # CPU 密集纯 Python 不宜用满逻辑核（超线程争抢）
    并行批量阈值: int = 8           # 批量低于该值不值得付固定开销


默认常量 = 成本常量()


# ===================== 硬件探测 =====================
@dataclass(frozen=True)
class 硬件:
    逻辑核: int
    物理核: int
    内存总量_GB: float
    内存可用_GB: float
    平台: str
    python版本: str
    psutil可用: bool


def _可选物理核(逻辑核: int) -> int:
    """优先 psutil 的物理核；缺失时按「超线程 ≈ 2 倍」估计。"""
    try:
        import psutil

        物理 = psutil.cpu_count(logical=False)
        if 物理 and 物理 >= 1:
            return int(物理)
    except Exception:
        pass
    return max(1, 逻辑核 // 2)


def _可选内存() -> tuple[float, float]:
    try:
        import psutil

        内存 = psutil.virtual_memory()
        return 内存.total / 2**30, 内存.available / 2**30
    except Exception:
        return -1.0, -1.0


def 探测硬件() -> 硬件:
    """返回当前机器硬件画像。全程 stdlib 兜底，psutil 可选。"""
    逻辑核 = os.cpu_count() or 1
    总量, 可用 = _可选内存()
    try:
        import psutil  # noqa: F401

        psutil可用 = True
    except Exception:
        psutil可用 = False
    return 硬件(
        逻辑核=逻辑核,
        物理核=_可选物理核(逻辑核),
        内存总量_GB=总量,
        内存可用_GB=可用,
        平台=sys.platform,
        python版本=f"{sys.version_info.major}.{sys.version_info.minor}",
        psutil可用=psutil可用,
    )


def 硬件签名(h: 硬件) -> tuple:
    """用于校准缓存失效判定的硬件指纹。"""
    return (h.逻辑核, h.物理核, h.平台, h.python版本, round(h.内存总量_GB, 1))


# ===================== 决策 =====================
def 建议进程数(
    批量: int,
    h: 硬件 | None = None,
    常量: 成本常量 | None = None,
    上限: int | None = None,
) -> tuple[int, bool]:
    """返回 `(进程数 P, 是否并行)`。

    `批量` = 一批要评价的独立染色体数（遗传算法每代一批 = 种群规模）。
    仅当批量大到足以摊薄 spawn 固定开销时才建议 `P > 1`。
    """
    h = h or 探测硬件()
    c = 常量 or 默认常量
    上限 = 上限 if 上限 is not None else c.进程数上限

    P = max(1, h.物理核 - 1)          # 给主进程留 1 核
    P = min(P, 上限)
    if P <= 1 or 批量 <= 0:
        return 1, False

    # 并行划算阈值（令 T_par < T_serial），再叠加一个保守下限
    阈值 = c.子进程重建_s / max(c.单次评估热_s * (1.0 - 1.0 / P), 1e-9)
    阈值 = max(阈值, float(c.并行批量阈值))
    return (P if 批量 >= 阈值 else 1), 批量 >= 阈值


def 估计墙钟_秒(总评价数: int, 进程数: int, 常量: 成本常量 | None = None) -> float:
    """按成本模型粗估一批评价的墙钟（秒）。"""
    c = 常量 or 默认常量
    if 总评价数 <= 0:
        return 0.0
    if 进程数 <= 1:
        return 总评价数 * c.单次评估热_s
    return c.子进程重建_s + 总评价数 * c.单次评估热_s / 进程数


# ===================== 校准（实测 + 缓存）====================
def 校准性能(
    h: 硬件 | None = None,
    缓存路径: Path | None = None,
    强制: bool = False,
) -> 成本常量:
    """实测并缓存机器相关常数，返回 `成本常量`。

    已缓存且硬件签名不变时直接读缓存（零额外开销）；否则做一次秒级校准：
      * T_rebuild    装载场景 + 通信环境 + 剖面表（子进程重建的主成分）
      * T_cold/T_hot 单次「运输+中继」联合评估的冷 / 热成本
      * 子进程重建_s = T_rebuild × 1.5（重建 + spawn 解释器启动/导入的余量）

    ⚠️ 校准**不真正 spawn**：spawn 要求调用方带 `if __name__ == "__main__"` 保护，
    而校准应是副作用无关、可从任意上下文调用的，故只测进程内重建再留余量。
    """
    h = h or 探测硬件()
    if 缓存路径 is None:
        缓存路径 = Path(__file__).resolve().parents[1] / ".性能校准.json"
    签 = 硬件签名(h)

    if not 强制 and 缓存路径.exists():
        try:
            存 = json.loads(缓存路径.read_text(encoding="utf-8"))
            if tuple(存.get("签名", [])) == 签 and "常量" in 存:
                c = 存["常量"]
                return 成本常量(
                    单次评估冷_s=float(c["单次评估冷_s"]),
                    单次评估热_s=float(c["单次评估热_s"]),
                    子进程重建_s=float(c["子进程重建_s"]),
                    进程数上限=int(c.get("进程数上限", 默认常量.进程数上限)),
                    并行批量阈值=int(c.get("并行批量阈值", 默认常量.并行批量阈值)),
                )
        except Exception:
            pass  # 缓存损坏则重新校准

    # —— 实测 ——
    import time

    from 源代码.公共库.通信中继.中继排程 import 评估
    from 源代码.公共库.通信中继.场景装配 import 装载场景
    from 源代码.公共库.通信中继.构造启发式 import 构造种子, 解码
    from 源代码.公共库.通信中继.通信剖面 import 构造剖面
    from 源代码.公共库.通信中继.通信模型 import 由场景装配

    t0 = time.perf_counter()
    场景 = 装载场景()
    环境 = 由场景装配(场景)
    剖面表 = 构造剖面(场景, 环境)
    T_rebuild = time.perf_counter() - t0

    种子 = 构造种子(场景)
    架次列表 = 解码(场景, 种子[0][1])
    缓存: dict = {}
    t0 = time.perf_counter()
    评估(剖面表, 环境, 架次列表, None, 缓存)
    T_cold = time.perf_counter() - t0
    t0 = time.perf_counter()
    评估(剖面表, 环境, 架次列表, None, 缓存)
    T_hot = time.perf_counter() - t0

    # 子进程重建固定开销 = 进程内重建 × 1.5（重建 + spawn 解释器启动/导入的余量）。
    # 不在此处真正 spawn —— 见 docstring。
    c = 成本常量(
        单次评估冷_s=round(T_cold, 3),
        单次评估热_s=round(T_hot, 3),
        子进程重建_s=round(T_rebuild * 1.5, 3),
        进程数上限=默认常量.进程数上限,
        并行批量阈值=默认常量.并行批量阈值,
    )
    try:
        缓存路径.write_text(
            json.dumps(
                {"签名": 签, "常量": c.__dict__},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass  # 写缓存失败不影响决策
    return c

"""
并行评价 —— 多点多架次调度遗传算法的多进程评价驱动。

背景
----
`多目标求解` 已支持「生成染色体」与「评价」解耦（`批量评价器` 注入），
本模块提供 spawn 进程池 + 批量评价器，把每代的一批染色体评价并行化。

原则
----
    * 并行只改墙钟、不改结果：评价不消耗随机数，故随机序列与串行逐位一致。
    * 场景对象不可 pickle（`eq=False` 且被 `lru_cache` 当作键），故子进程从数据文件
      **重建场景**、长期复用（spawn 下每个 worker 各持一份）。
    * 探测/建池失败一律回退串行，绝不因本模块崩溃。

与联合调度与中继的关系
------------------
联合调度与中继的 `通信中继/性能调度.py` 有更完整的「硬件探测 + 校准缓存 + 成本模型」。
本模块是多点多架次调度侧的精简等价（按任务目录自包含、各自维护的惯例），
仅保留「逻辑核/物理核估计 → 进程数」这一步，不含校准。
"""
from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path

# 经验先验（2026-09-25，24 逻辑核 / Windows / study_py311 实测）：6~12 进程饱和、20 进程
# 反而更慢（超线程争抢）⇒ 默认上限 8。并行只对「批量 >= 阈值」划算。
进程数上限 = 8
并行批量阈值 = 8


def 建议进程数(批量: int, 上限: int | None = None) -> tuple[int, bool]:
    """按逻辑核与批量规模自适应决定并行进程数 `(P, 是否并行)`。

    无 psutil ⇒ 物理核按「逻辑核 // 2」估计（超线程 ≈ 2×），并给主进程留 1 核。
    """
    逻辑核 = os.cpu_count() or 1
    物理核 = max(1, 逻辑核 // 2)
    上限 = 上限 if 上限 is not None else 进程数上限
    P = min(max(1, 物理核 - 1), 上限)
    if P <= 1 or 批量 < 并行批量阈值:
        return 1, False
    return P, True


# ===================== 子进程 =====================
_子进程状态: dict = {}


def _子进程初始化() -> None:
    """在子进程内重建多点多架次调度场景（不可 pickle，须从数据文件重建）。"""
    from 源代码.公共库.运输调度.场景装配 import 装载场景

    _子进程状态["场景"] = 装载场景()


def _子进程评价(染色体: tuple) -> object:
    """`染色体 -> 个体`，评价器在子进程内长期复用。"""
    from 源代码.公共库.运输调度.多目标求解 import 评价染色体

    return 评价染色体(_子进程状态["场景"], 染色体)


def _确认主模块保护() -> None:
    """建池前确认调用方带 `if __name__ == "__main__":` 保护（spawn 子进程会重新导入主模块）。"""
    import __main__

    if getattr(__main__, "__spec__", None) is not None:
        return
    文件 = getattr(__main__, "__file__", None)
    if not 文件:
        return
    try:
        源 = Path(文件).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    有保护 = any(
        行.strip().startswith("if __name__") and "__main__" in 行
        for 行 in 源.splitlines()
    )
    if not 有保护:
        raise RuntimeError(
            "多点多架次调度多进程评价要求主模块带 `if __name__ == \"__main__\":` 保护，"
            f"但 {文件} 里没有找到。请把入口语句放进保护之内（或改传 `进程数=1` 用串行）。"
        )


def 建并行池(进程数: int):
    """返回 `(池, 批量评价器)`；`进程数 <= 1` 时返回 `(None, None)`。"""
    if 进程数 <= 1:
        return None, None
    _确认主模块保护()
    池 = mp.get_context("spawn").Pool(进程数, initializer=_子进程初始化)

    def 批量(染色体表: list) -> list:
        return 池.map(_子进程评价, 染色体表)

    return 池, 批量


def _子进程打磨(任务: tuple) -> object:
    """`(包序列, 权重, 归一, 迭代次数, 随机种子) -> 个体`（多点多架次调度四目标打磨）。"""
    from 源代码.公共库.运输调度.多目标求解 import 局部打磨

    包序列, 权重, 归一, 迭代次数, 随机种子 = 任务
    return 局部打磨(
        _子进程状态["场景"], 包序列, 权重, 归一,
        迭代次数=迭代次数, 随机种子=随机种子,
    )


def 建批量打磨器(池):
    """把 `池.map` 包装成 `批量打磨器(任务表) -> list[个体]`；`池` 为 None 时返回 None。"""
    if 池 is None:
        return None

    def 批量(任务表: list) -> list:
        return 池.map(_子进程打磨, 任务表)

    return 批量

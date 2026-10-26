"""E1a：小规模运输组批的精确基准。

实例：3 个服务区 × 每区 2 个货箱 = 6 个货箱；每型 1 架无人机。
方法：
1. 枚举全部可行架次模板（路线、箱集合、机型）；
2. 用集合划分 MILP（HiGHS，`scipy.optimize.milp`）求解若干加权目标；
3. 用“枚举全部集合划分”求精确 Pareto 前沿（架次数、能耗、最大架次时间）；
4. 比较 MILP 最优值与精确前沿的最小加权值。

说明：该基准只验证组批/模板层，不含通信与中继；集成层的精确基准见后续 E1b/E1c。
"""
from __future__ import annotations

import itertools
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 实验.实例.构造小实例 import 小实例, 截断货箱  # noqa: E402
from 实验.定理验证.公共 import 非支配, 写CSV  # noqa: E402
from 源代码.公共库.通信中继.多点飞行模型 import 多点架次代价  # noqa: E402

结果目录 = 项目根 / "结果" / "精确基准"
结果目录.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class 模板:
    编号: int
    服务区序列: tuple[str, ...]
    机型: str
    箱集合: frozenset[str]
    能耗: float
    时间: float


def 枚举模板(场景) -> list[模板]:
    模板表: list[模板] = []
    货箱索引 = {b["货箱编号"]: b for b in 场景.货箱}
    编号 = 0
    for 长度 in range(1, len(场景.编号顺序) + 1):
        for 序列 in itertools.permutations(场景.编号顺序, 长度):
            每区候选 = []
            for 区 in 序列:
                本区 = sorted(场景.货箱归属.get(区, []), key=lambda b: b["货箱编号"])
                if not 本区:
                    每区候选 = []
                    break
                子集 = []
                for k in range(1, len(本区) + 1):
                    for combo in itertools.combinations(本区, k):
                        子集.append(list(combo))
                每区候选.append(子集)
            if not 每区候选:
                continue
            for 组合 in itertools.product(*每区候选):
                for 型, 机 in 场景.机型表.items():
                    箱列表 = [list(x) for x in 组合]
                    try:
                        代价 = 多点架次代价(场景, 机, 序列, 箱列表)
                    except Exception:
                        continue
                    if not 代价.满足返航余量:
                        continue
                    if 代价.总载质量 > 机.最大载货质量 + 1e-9:
                        continue
                    if 代价.总装载体积 > 机.可用装载体积 + 1e-9:
                        continue
                    箱集合 = frozenset(b["货箱编号"] for 段 in 箱列表 for b in 段)
                    if not 箱集合:
                        continue
                    模板表.append(
                        模板(
                            编号=编号,
                            服务区序列=tuple(序列),
                            机型=型,
                            箱集合=箱集合,
                            能耗=float(代价.总能耗),
                            时间=float(代价.作业时间),
                        )
                    )
                    编号 += 1
    return 模板表


def 精确前沿(箱编号: tuple[str, ...], 模板表: list[模板]) -> set:
    包含 = {b: [t for t in 模板表 if b in t.箱集合] for b in 箱编号}
    出: list[tuple[int, float, float]] = []

    def 递归(剩余: frozenset[str], 架次: int, 能耗: float, 时间: float) -> None:
        if not 剩余:
            出.append((架次, 能耗, 时间))
            return
        首 = min(剩余)
        for t in 包含[首]:
            if not t.箱集合 <= 剩余:
                continue
            递归(剩余 - t.箱集合, 架次 + 1, 能耗 + t.能耗, max(时间, t.时间))

    递归(frozenset(箱编号), 0, 0.0, 0.0)
    return 非支配(出)


def 解MILP(模板表: list[模板], 箱编号: tuple[str, ...], 权重: tuple[float, float, float]):
    索引 = {b: i for i, b in enumerate(箱编号)}
    n = len(模板表)
    # 变量：x_0..x_{n-1}（模板是否选择）+ T（最大架次时间）
    A箱 = np.zeros((len(箱编号), n + 1), dtype=float)
    for j, t in enumerate(模板表):
        for b in t.箱集合:
            A箱[索引[b], j] = 1.0
    # T - t_j x_j >= 0
    A时 = np.zeros((n, n + 1), dtype=float)
    for j, t in enumerate(模板表):
        A时[j, j] = -t.时间
        A时[j, n] = 1.0

    c = np.array(
        [权重[0] + 权重[1] * t.能耗 for t in 模板表] + [权重[2]],
        dtype=float,
    )
    约束 = [
        LinearConstraint(A箱, np.ones(len(箱编号)), np.ones(len(箱编号))),
        LinearConstraint(A时, np.zeros(n), np.full(n, np.inf)),
    ]
    结果 = milp(
        c=c,
        integrality=np.array([1] * n + [0]),
        bounds=Bounds(np.zeros(n + 1), np.concatenate([np.ones(n), [np.inf]])),
        constraints=约束,
        options={"time_limit": 60},
    )
    return 结果


def main() -> None:
    实例 = 小实例()
    场景 = 截断货箱(实例.场景, 2)
    箱编号 = tuple(b["货箱编号"] for b in 场景.货箱)
    模板表 = 枚举模板(场景)
    前沿 = 精确前沿(箱编号, 模板表)

    能耗尺 = max((e for _, e, _ in 前沿), default=1.0) or 1.0
    时间尺 = max((t for _, _, t in 前沿), default=1.0) or 1.0
    权重集 = [
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 1.0 / 能耗尺, 1.0 / 时间尺),
        (1.0, 2.0 / 能耗尺, 0.5 / 时间尺),
        (0.5, 1.0 / 能耗尺, 2.0 / 时间尺),
    ]

    行 = []
    for 权重 in 权重集:
        结果 = 解MILP(模板表, 箱编号, 权重)
        精确值 = min(
            (权重[0] * n + 权重[1] * e + 权重[2] * t for n, e, t in 前沿),
            default=float("inf"),
        )
        MILP值 = float(结果.fun) if 结果.success else float("nan")
        gap = "" if not np.isfinite(MILP值) else f"{MILP值 - 精确值:.6e}"
        行.append({
            "箱数": len(箱编号),
            "模板数": len(模板表),
            "精确前沿大小": len(前沿),
            "权重": 权重,
            "MILP状态": int(结果.status),
            "MILP目标": "" if not np.isfinite(MILP值) else f"{MILP值:.9f}",
            "精确最小值": f"{精确值:.9f}",
            "差": gap,
        })
        print(
            f"权重 {权重}：MILP={MILP值:.6f} 精确={精确值:.6f} "
            f"状态={结果.status} 前沿={len(前沿)} 模板={len(模板表)}"
        )

    写CSV(
        结果目录 / "e1a_运输组批.csv",
        行,
        ["箱数", "模板数", "精确前沿大小", "权重", "MILP状态", "MILP目标", "精确最小值", "差"],
    )

    # 前沿摘要
    前沿行 = [{"架次数": n, "能耗_kWh": f"{e:.6f}", "最大架次时间_s": f"{t:.3f}"} for n, e, t in sorted(前沿)]
    写CSV(
        结果目录 / "e1a_精确前沿.csv",
        前沿行,
        ["架次数", "能耗_kWh", "最大架次时间_s"],
    )
    print(f"E1a 完成：箱数 {len(箱编号)}，模板 {len(模板表)}，前沿 {len(前沿)}")
    print(f"结果写入 {结果目录}")


if __name__ == "__main__":
    main()

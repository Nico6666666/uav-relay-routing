"""E1b：小规模中继覆盖的精确基准。

抽象模型：
- n 个通信缺口，m 个候选驻留点；
- 每个驻留点可覆盖一部分缺口（整窗覆盖）；
- 一个“中继出动模板”= 一个驻留点 + 它覆盖的缺口子集；
- 模板代价 = 1（架次）+ 0.01×服务窗长度；
- 目标 = 模板代价 + 未覆盖缺口罚（大 M）。

方法：
1. 枚举全部模板；
2. 用集合覆盖 MILP（HiGHS）求最优；
3. 用“按最低未覆盖缺口分支”的精确动态规划求最优；
4. 比较两者目标值。

说明：该基准验证中继覆盖/模板层，不含三维链路与中继飞行能耗；真实链路由 V5/V6 与标准档自检覆盖。
"""
from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 实验.定理验证.公共 import 写CSV  # noqa: E402

结果目录 = 项目根 / "结果" / "精确基准"
结果目录.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class 模板:
    驻留点: int
    覆盖: int          # 位掩码
    代价: float


def 枚举模板(覆盖表: list[int], 时间窗: list[tuple[float, float]]) -> list[模板]:
    出 = []
    for c, 覆盖 in enumerate(覆盖表):
        位 = [i for i in range(len(时间窗)) if 覆盖 >> i & 1]
        for 子集 in range(1, 1 << len(位)):
            选中 = [位[k] for k in range(len(位)) if 子集 >> k & 1]
            窗 = (min(时间窗[i][0] for i in 选中), max(时间窗[i][1] for i in 选中))
            代价 = 1.0 + 0.01 * (窗[1] - 窗[0])
            掩码 = 0
            for i in 选中:
                掩码 |= 1 << i
            出.append(模板(驻留点=c, 覆盖=掩码, 代价=代价))
    return 出


def 精确DP(模板表: list[模板], n: int, 罚: float) -> float:
    覆盖到 = [[] for _ in range(n)]
    for t in 模板表:
        for g in range(n):
            if t.覆盖 >> g & 1:
                覆盖到[g].append(t)

    @lru_cache(maxsize=None)
    def 最优(mask: int) -> float:
        if mask == 0:
            return 0.0
        首 = (mask & -mask).bit_length() - 1
        候选 = [罚 + 最优(mask & ~(1 << 首))]
        for t in 覆盖到[首]:
            if t.覆盖 & mask:
                候选.append(t.代价 + 最优(mask & ~t.覆盖))
        return min(候选)

    return 最优((1 << n) - 1)


def 解MILP(模板表: list[模板], n: int, 罚: float):
    m = len(模板表)
    # 变量 x_0..x_{m-1} + u_0..u_{n-1}
    A = np.zeros((n, m + n), dtype=float)
    for j, t in enumerate(模板表):
        for g in range(n):
            if t.覆盖 >> g & 1:
                A[g, j] = 1.0
    for g in range(n):
        A[g, m + g] = 1.0
    c = np.array([t.代价 for t in 模板表] + [罚] * n, dtype=float)
    结果 = milp(
        c=c,
        integrality=np.ones(m + n),
        bounds=Bounds(np.zeros(m + n), np.ones(m + n)),
        constraints=LinearConstraint(A, np.ones(n), np.full(n, np.inf)),
        options={"time_limit": 60},
    )
    return 结果


def main() -> None:
    rng = random.Random(20261025)
    行 = []
    失败 = 0
    for 例 in range(300):
        n = rng.randint(4, 8)
        m = rng.randint(2, 5)
        时间窗 = []
        t = 0.0
        for _ in range(n):
            起 = t + rng.uniform(0, 5)
            长 = rng.uniform(5, 30)
            时间窗.append((起, 起 + 长))
            t = 起 + 长
        覆盖表 = []
        for _ in range(m):
            概率 = rng.uniform(0.3, 0.9)
            掩码 = 0
            for g in range(n):
                if rng.random() < 概率:
                    掩码 |= 1 << g
            覆盖表.append(掩码)
        模板表 = 枚举模板(覆盖表, 时间窗)
        罚 = 100.0
        DP值 = 精确DP(模板表, n, 罚)
        结果 = 解MILP(模板表, n, 罚)
        MILP值 = float(结果.fun) if 结果.success else float("nan")
        if not np.isfinite(MILP值) or abs(MILP值 - DP值) > 1e-6:
            失败 += 1
            行.append({
                "例号": 例, "缺口数": n, "驻留点数": m, "模板数": len(模板表),
                "MILP状态": int(结果.status), "MILP目标": f"{MILP值:.9f}",
                "DP目标": f"{DP值:.9f}", "差": f"{MILP值 - DP值:.3e}", "结论": "失败",
            })
            if 失败 <= 3:
                print("反例：", 例, MILP值, DP值)
            if 失败 >= 10:
                break
    if not 行:
        行.append({"例号": "全部", "结论": "通过", "说明": "300 个随机小实例，MILP 与 DP 目标一致"})
    写CSV(
        结果目录 / "e1b_中继覆盖.csv",
        行,
        ["例号", "缺口数", "驻留点数", "模板数", "MILP状态", "MILP目标", "DP目标", "差", "结论", "说明"],
    )
    print(f"E1b 完成：失败 {失败} 例；结果写入 {结果目录 / 'e1b_中继覆盖.csv'}")


if __name__ == "__main__":
    main()

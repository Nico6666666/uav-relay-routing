"""V2：覆盖下界（定理 3）的随机小实例验证。

抽象模型：
- 缺口有半开时间窗 [s,e)；
- 每个驻留点可覆盖一部分缺口（整窗覆盖）；
- 至多 M=2 条中继线。

比较：
A. 下界 L（定理 3 的公式）；
B. 穷举所有 ≤M 个驻留点的组合，求真实最小未覆盖缺口数。

若定理 3 成立，恒有 L ≤ B。
"""
from __future__ import annotations

import itertools
import random
import sys
from pathlib import Path

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 实验.定理验证.公共 import 写CSV, 结果目录  # noqa: E402


def 真实最小未覆盖(缺口数: int, 驻留点: list[set[int]], M: int = 2) -> int:
    最优 = 缺口数
    for 规模 in range(0, min(M, len(驻留点)) + 1):
        for 组合 in itertools.combinations(驻留点, 规模):
            并 = set()
            for 点 in 组合:
                并 |= 点
            最优 = min(最优, 缺口数 - len(并))
    return 最优


def 下界(缺口: list[tuple[float, float]], 驻留点: list[set[int]], M: int = 2) -> int:
    if not 缺口:
        return 0
    事件 = sorted({t for s, e in 缺口 for t in (s, e)})
    积分 = 0.0
    for a, b in zip(事件, 事件[1:]):
        if b - a <= 1e-12:
            continue
        中点 = (a + b) / 2.0
        活跃 = [i for i, (s, e) in enumerate(缺口) if s <= 中点 < e]
        if not 活跃:
            continue
        覆盖数 = sorted(
            (len(点 & set(活跃)) for 点 in 驻留点),
            reverse=True,
        )
        m_m = min(len(活跃), sum(覆盖数[:M]))
        积分 += max(0, len(活跃) - m_m) * (b - a)
    if 积分 <= 1e-12:
        return 0
    时长 = sorted((e - s for s, e in 缺口), reverse=True)
    累计 = 0.0
    for k, d in enumerate(时长, start=1):
        累计 += d
        if 累计 >= 积分 - 1e-12:
            return k
    return len(时长)


def main() -> None:
    rng = random.Random(20261025)
    行 = []
    失败 = 0
    for 例 in range(20000):
        n = rng.randint(1, 12)
        缺口 = []
        时刻 = 0.0
        for _ in range(n):
            起 = 时刻 + rng.uniform(0.0, 5.0)
            长 = rng.uniform(1.0, 20.0)
            缺口.append((起, 起 + 长))
            时刻 = 起 + 长 + rng.uniform(0.0, 2.0)
        m = rng.randint(1, 8)
        驻留点 = []
        for _ in range(m):
            概率 = rng.uniform(0.2, 0.9)
            驻留点.append({i for i in range(n) if rng.random() < 概率})
        a = 下界(缺口, 驻留点)
        b = 真实最小未覆盖(n, 驻留点)
        if a > b:
            失败 += 1
            行.append({
                "例号": 例,
                "缺口数": n,
                "驻留点数": m,
                "下界": a,
                "真实最小未覆盖": b,
                "结论": "失败",
            })
            if 失败 <= 5:
                print("反例：", 例, "下界", a, "真实", b)
            if 失败 >= 10:
                break
    if not 行:
        行.append({"例号": "全部", "结论": "通过", "说明": "20000 个随机实例，下界 ≤ 真实最小未覆盖"})
    写CSV(
        结果目录 / "v2_下界有效性.csv",
        行,
        ["例号", "缺口数", "驻留点数", "下界", "真实最小未覆盖", "结论", "说明"],
    )
    print(f"V2 完成：失败 {失败} 例；结果写入 {结果目录 / 'v2_下界有效性.csv'}")


if __name__ == "__main__":
    main()

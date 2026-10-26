"""V4：组批动态规划（定理 5）的随机小实例验证。

抽象模型：
- T 种同型货箱，计数 n_t；
- 一个架次由计数向量 c 表示，可行当且仅当 Σc ≤ 容量；
- 架次代价：能耗 E(c)、作业时间 T(c)；
- 目标：(架次数, 总能耗, 区内最大架次作业时间)。

比较 DP 前沿与“枚举全部计数向量划分”的暴力前沿。
"""
from __future__ import annotations

import itertools
import random
import sys
from pathlib import Path

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 实验.定理验证.公共 import 非支配, 写CSV, 结果目录  # noqa: E402


def 全部状态(计数: tuple[int, ...]):
    return itertools.product(*(range(n + 1) for n in 计数))


def 可行架次(计数: tuple[int, ...], 容量: int):
    出 = []
    for c in 全部状态(计数):
        if sum(c) == 0:
            continue
        if sum(c) <= 容量:
            出.append(c)
    return 出


def 跑DP(计数: tuple[int, ...], 容量: int, 能耗: dict, 时间: dict) -> set:
    表 = {r: set() for r in 全部状态(计数)}
    表[(0,) * len(计数)] = {(0, 0.0, 0.0)}
    for r in sorted(表, key=sum):
        if sum(r) == 0:
            continue
        候选 = []
        for c in 可行架次(计数, 容量):
            if any(ci > ri for ci, ri in zip(c, r)):
                continue
            余 = tuple(ri - ci for ri, ci in zip(r, c))
            for n, e, t in 表[余]:
                候选.append((n + 1, e + 能耗[c], max(t, 时间[c])))
        表[r] = 非支配(候选)
    return 表[计数]


def 暴力(计数: tuple[int, ...], 容量: int, 能耗: dict, 时间: dict) -> set:
    出 = []

    def 递归(r: tuple[int, ...], n: int, e: float, t: float):
        if sum(r) == 0:
            出.append((n, e, t))
            return
        for c in 可行架次(计数, 容量):
            if any(ci > ri for ci, ri in zip(c, r)):
                continue
            余 = tuple(ri - ci for ri, ci in zip(r, c))
            递归(余, n + 1, e + 能耗[c], max(t, 时间[c]))

    递归(计数, 0, 0.0, 0.0)
    return 非支配(出)


def main() -> None:
    rng = random.Random(20261025)
    行 = []
    失败 = 0
    for 例 in range(500):
        T = rng.randint(2, 3)
        计数 = tuple(rng.randint(1, 4) for _ in range(T))
        if sum(计数) > 7:
            continue
        容量 = rng.randint(1, 4)
        可行 = 可行架次(计数, 容量)
        能耗 = {c: round(rng.uniform(1, 10), 3) for c in 可行}
        时间 = {c: round(rng.uniform(10, 100), 3) for c in 可行}
        a = 跑DP(计数, 容量, 能耗, 时间)
        b = 暴力(计数, 容量, 能耗, 时间)
        if a != b:
            失败 += 1
            行.append({
                "例号": 例, "计数": 计数, "容量": 容量,
                "DP前沿大小": len(a), "暴力前沿大小": len(b),
                "只在DP": len(a - b), "只在暴力": len(b - a),
                "结论": "失败",
            })
            if 失败 <= 3:
                print("反例：", 例, "计数", 计数, "容量", 容量, "只在DP", a - b, "只在暴力", b - a)
            if 失败 >= 10:
                break
    if not 行:
        行.append({"例号": "全部", "结论": "通过", "说明": "500 个随机小实例，DP 与暴力前沿逐点相等"})
    写CSV(
        结果目录 / "v4_组批DP.csv",
        行,
        ["例号", "计数", "容量", "DP前沿大小", "暴力前沿大小", "只在DP", "只在暴力", "结论", "说明"],
    )
    print(f"V4 完成：失败 {失败} 例；结果写入 {结果目录 / 'v4_组批DP.csv'}")


if __name__ == "__main__":
    main()

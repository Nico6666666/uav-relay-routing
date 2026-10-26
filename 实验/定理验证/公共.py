"""定理验证公共工具：非支配过滤、结果写出、路径。"""
from __future__ import annotations

import csv
from pathlib import Path

项目根 = Path(__file__).resolve().parents[2]
结果目录 = 项目根 / "结果" / "定理验证"
结果目录.mkdir(parents=True, exist_ok=True)


def 支配(甲: tuple, 乙: tuple) -> bool:
    """甲是否 Pareto 支配乙（全部 ≤，且至少一个 <）。"""
    return all(a <= b for a, b in zip(甲, 乙)) and any(a < b for a, b in zip(甲, 乙))


def 非支配(点集) -> set:
    """返回点集的非支配子集（去重）。"""
    点列 = sorted(set(tuple(round(float(x), 9) for x in p) for p in 点集))
    出 = []
    for p in 点列:
        if not any(支配(q, p) for q in 点列 if q != p):
            出.append(p)
    return set(出)


def 写CSV(路径: Path, 行: list[dict], 列: list[str]) -> None:
    路径.parent.mkdir(parents=True, exist_ok=True)
    with 路径.open("w", newline="", encoding="utf-8-sig") as f:
        写 = csv.DictWriter(f, fieldnames=列)
        写.writeheader()
        for r in 行:
            写.writerow({k: r.get(k, "") for k in 列})

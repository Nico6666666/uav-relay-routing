"""V3：区间图资源需求（定理 4）的随机验证。

验证：
1. 峰值并发 == 贪心着色数 == 最大团（区间图中三者相等）；
2. 对随机分组，Σ 组峰值 ≥ 全局峰值，Δ ≥ 0。
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 实验.定理验证.公共 import 写CSV, 结果目录  # noqa: E402


def 峰值(区间: list[tuple[float, float]]) -> int:
    事件 = []
    for s, e in 区间:
        事件.append((s, 1))
        事件.append((e, -1))
    事件.sort(key=lambda x: (x[0], x[1]))  # 同一时刻先 -1 后 +1（半开区间）
    当前 = 0
    最大 = 0
    for _, d in 事件:
        当前 += d
        最大 = max(最大, 当前)
    return 最大


def 贪心着色数(区间: list[tuple[float, float]]) -> int:
    颜色末端: list[float] = []
    for s, e in sorted(区间):
        可用 = None
        for i, 末 in enumerate(颜色末端):
            if 末 <= s + 1e-12:
                可用 = i
                break
        if 可用 is None:
            颜色末端.append(e)
        else:
            颜色末端[可用] = e
    return len(颜色末端)


def main() -> None:
    rng = random.Random(20261025)
    行 = []
    失败 = 0
    for 例 in range(20000):
        n = rng.randint(1, 30)
        区间 = []
        for _ in range(n):
            s = rng.uniform(0, 100)
            e = s + rng.uniform(0.5, 20)
            区间.append((s, e))
        p = 峰值(区间)
        c = 贪心着色数(区间)
        # 随机分成 k 组
        k = rng.randint(1, 4)
        组 = [[] for _ in range(k)]
        for 段 in 区间:
            组[rng.randrange(k)].append(段)
        组峰值 = [峰值(g) for g in 组]
        和 = sum(组峰值)
        delta = 和 - p
        结论 = "通过" if (p == c and delta >= 0) else "失败"
        if 结论 == "失败":
            失败 += 1
            行.append({
                "例号": 例, "区间数": n, "峰值": p, "着色数": c,
                "组数": k, "组峰值和": 和, "Δ": delta, "结论": 结论,
            })
            if 失败 <= 5:
                print("反例：", 例, "峰值", p, "着色", c, "Δ", delta)
            if 失败 >= 10:
                break
    if not 行:
        行.append({"例号": "全部", "结论": "通过", "说明": "20000 个随机区间族，峰值=着色数且 Δ≥0"})
    写CSV(
        结果目录 / "v3_区间图.csv",
        行,
        ["例号", "区间数", "峰值", "着色数", "组数", "组峰值和", "Δ", "结论", "说明"],
    )
    print(f"V3 完成：失败 {失败} 例；结果写入 {结果目录 / 'v3_区间图.csv'}")


if __name__ == "__main__":
    main()

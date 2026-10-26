"""V1：无损分解（定理 1）的随机有限实例验证。

构造随机的“运输方案 → 中继方案集合”结构：
- 运输向量 (f1, T_T, E_T, f4)；
- 中继向量 (T_R, E_R, N_R)；
- 联合向量 (f1, max(T_T,T_R), E_T+E_R, f4, N_R)。

比较：
A. 直接对所有联合方案做非支配过滤；
B. 对每个运输方案先做中继子问题的非支配过滤，再做联合非支配过滤。

若定理 1 成立，A 与 B 应逐点相等。
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 实验.定理验证.公共 import 非支配, 写CSV, 结果目录  # noqa: E402


def 联合向量(运输: tuple, 中继: tuple) -> tuple:
    f1, t_t, e_t, f4 = 运输
    t_r, e_r, n_r = 中继
    return (f1, max(t_t, t_r), e_t + e_r, f4, n_r)


def 直接前沿(实例: list[tuple[tuple, list[tuple]]]) -> set:
    return 非支配([联合向量(运输, 中继) for 运输, 中继列 in 实例 for 中继 in 中继列])


def 分解前沿(实例: list[tuple[tuple, list[tuple]]]) -> set:
    候选 = []
    for 运输, 中继列 in 实例:
        for 中继 in 非支配(中继列):
            候选.append(联合向量(运输, 中继))
    return 非支配(候选)


def main() -> None:
    rng = random.Random(20261025)
    行 = []
    失败 = 0
    for 例 in range(20000):
        实例 = []
        for _ in range(rng.randint(1, 6)):
            运输 = (
                round(rng.uniform(0, 1000), 3),
                round(rng.uniform(1, 100), 3),
                round(rng.uniform(1, 100), 3),
                rng.randint(1, 10),
            )
            中继列 = [
                (
                    round(rng.uniform(1, 100), 3),
                    round(rng.uniform(1, 100), 3),
                    rng.randint(1, 8),
                )
                for _ in range(rng.randint(1, 6))
            ]
            实例.append((运输, 中继列))
        a = 直接前沿(实例)
        b = 分解前沿(实例)
        if a != b:
            失败 += 1
            行.append({
                "例号": 例,
                "直接前沿大小": len(a),
                "分解前沿大小": len(b),
                "只在前者": len(a - b),
                "只在后者": len(b - a),
                "结论": "失败",
            })
            if 失败 <= 3:
                print("反例：", 例, "只在前者", a - b, "只在后者", b - a)
            if 失败 >= 10:
                break
    if not 行:
        行.append({"例号": "全部", "结论": "通过", "说明": "20000 个随机实例，A 与 B 逐点相等"})
    写CSV(
        结果目录 / "v1_分解等价.csv",
        行,
        ["例号", "直接前沿大小", "分解前沿大小", "只在前者", "只在后者", "结论", "说明"],
    )
    print(f"V1 完成：失败 {失败} 例；结果写入 {结果目录 / 'v1_分解等价.csv'}")


if __name__ == "__main__":
    main()

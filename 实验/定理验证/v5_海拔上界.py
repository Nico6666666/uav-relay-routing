"""V5：悬停海拔上界（引理 2）与高度消除（定理 2）的数值验证。

验证：
1. 对随机平面点与位姿集，计算 H_max = min(地面+离地上限, min_p(h_p+sqrt(D_u^2-d_p^2)))；
   在 H_max 之上（且不超过离地上限）任取海拔，位姿集应不可行。
2. 对可行悬停海拔 H_min 与 H_min+50，比较中继航段飞行能耗；应相等。
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 源代码.公共库.通信中继.场景装配 import 装载场景  # noqa: E402
from 源代码.公共库.通信中继.通信模型 import 由场景装配, 运输机端点  # noqa: E402
from 源代码.公共库.通信中继.地理计算 import 水平距离_m  # noqa: E402
from 源代码.公共库.通信中继.悬停高度 import (  # noqa: E402
    接入上限_无遮挡_km,
    位姿集可行,
    最优悬停高度,
    覆盖任务,
)
from 源代码.公共库.通信中继.中继模型 import 读取中继机, 中继航段代价  # noqa: E402
from 实验.定理验证.公共 import 写CSV, 结果目录  # noqa: E402


def main() -> None:
    rng = random.Random(20261025)
    场景 = 装载场景()
    环境 = 由场景装配(场景)
    机 = 读取中继机()
    网关 = 环境.网关端点(场景)
    纬度 = 环境._纬度升序
    经度 = 环境.经度向量
    D_u = 接入上限_无遮挡_km * 1000.0
    O = 场景.调度中心

    行 = []
    违反 = 0
    能耗不等 = 0
    for 例 in range(60):
        # 随机悬停平面点
        c_lon = rng.uniform(float(经度[0]), float(经度[-1]))
        c_lat = rng.uniform(float(纬度[0]), float(纬度[-1]))
        地面 = 环境.地面高程_at(c_lon, c_lat)
        if not math.isfinite(地面):
            continue
        # 1–3 个运输机位姿
        位姿 = []
        for _ in range(rng.randint(1, 3)):
            p_lon = rng.uniform(float(经度[0]), float(经度[-1]))
            p_lat = rng.uniform(float(纬度[0]), float(纬度[-1]))
            p_ground = 环境.地面高程_at(p_lon, p_lat)
            if not math.isfinite(p_ground):
                continue
            p_alt = p_ground + rng.uniform(30.0, 150.0)
            位姿.append(运输机端点(p_lon, p_lat, p_alt))
        if not 位姿:
            continue

        # 引理 2 的上界
        上界 = 地面 + 机.最大悬停离地高度_m
        for p in 位姿:
            d = 水平距离_m(c_lon, c_lat, p.经度, p.纬度)
            if d > D_u:
                上界 = None
                break
            上界 = min(上界, p.海拔 + math.sqrt(max(0.0, D_u * D_u - d * d)))
        if 上界 is None:
            continue

        # 在 H_max 之上检查不可行
        越界可行 = 0
        for Δ in (1.0, 10.0, 50.0):
            H = 上界 + Δ
            if H > 地面 + 机.最大悬停离地高度_m + 1e-9:
                continue
            if 位姿集可行(环境, c_lon, c_lat, H, 位姿, 网关):
                越界可行 += 1
        if 越界可行:
            违反 += 1

        # 定理 2：可行海拔上的航段飞行能耗
        差 = None
        任务 = 覆盖任务(运输机位姿=tuple(位姿), 说明="V5")
        果 = 最优悬停高度(环境, c_lon, c_lat, 任务, 机.最大悬停离地高度_m, 网关)
        if 果.可行 and 果.最优海拔 is not None:
            H0 = 果.最优海拔
            H1 = min(H0 + 50.0, 地面 + 机.最大悬停离地高度_m)
            段0 = 中继航段代价(
                环境, 机, "O01", "P", O["经度"], O["纬度"], O["海拔"], c_lon, c_lat, H0
            )
            段1 = 中继航段代价(
                环境, 机, "O01", "P", O["经度"], O["纬度"], O["海拔"], c_lon, c_lat, H1
            )
            差 = abs(段0.能耗 - 段1.能耗)
            if 差 > 1e-9:
                能耗不等 += 1

        行.append({
            "例号": 例,
            "位姿数": len(位姿),
            "地面": round(地面, 3),
            "H_max": round(上界, 3),
            "越界可行数": 越界可行,
            "能耗差": "" if 差 is None else f"{差:.3e}",
            "结论": "通过" if (越界可行 == 0 and (差 is None or 差 <= 1e-9)) else "失败",
        })

    写CSV(
        结果目录 / "v5_海拔上界.csv",
        行,
        ["例号", "位姿数", "地面", "H_max", "越界可行数", "能耗差", "结论"],
    )
    print(
        f"V5 完成：越界可行 {违反} 例；能耗不等 {能耗不等} 例；"
        f"结果写入 {结果目录 / 'v5_海拔上界.csv'}"
    )


if __name__ == "__main__":
    main()

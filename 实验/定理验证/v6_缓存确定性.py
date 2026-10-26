"""V6：缓存无关性与评价确定性（命题 3）的数值验证。

验证：
- 同一批端点对，在“新环境（空缓存）”与“热环境（已缓存）”下的
  链路可用性与视线遮挡判定逐位一致；
- 同一环境下重复计算两次，结果一致。
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
from 源代码.公共库.通信中继.通信模型 import 由场景装配, 中继端点, 运输机端点  # noqa: E402
from 实验.定理验证.公共 import 写CSV, 结果目录  # noqa: E402


def main() -> None:
    rng = random.Random(20261025)
    场景 = 装载场景()
    环境1 = 由场景装配(场景)
    环境2 = 由场景装配(场景)
    纬度 = 环境1._纬度升序
    经度 = 环境1.经度向量

    对 = []
    for _ in range(300):
        lon1 = rng.uniform(float(经度[0]), float(经度[-1]))
        lat1 = rng.uniform(float(纬度[0]), float(纬度[-1]))
        g1 = 环境1.地面高程_at(lon1, lat1)
        lon2 = rng.uniform(float(经度[0]), float(经度[-1]))
        lat2 = rng.uniform(float(纬度[0]), float(纬度[-1]))
        g2 = 环境1.地面高程_at(lon2, lat2)
        if not (math.isfinite(g1) and math.isfinite(g2)):
            continue
        甲 = 运输机端点(lon1, lat1, g1 + rng.uniform(30, 200))
        乙 = 中继端点(lon2, lat2, g2 + rng.uniform(30, 300))
        对.append((甲, 乙))

    # 冷算
    冷 = [(环境1.链路可用(甲, 乙), 环境1.视线遮挡(甲, 乙)) for 甲, 乙 in 对]
    # 同一环境再算（热缓存）
    热1 = [(环境1.链路可用(甲, 乙), 环境1.视线遮挡(甲, 乙)) for 甲, 乙 in 对]
    # 新环境第一次算（冷），第二次算（热）
    新冷 = [(环境2.链路可用(甲, 乙), 环境2.视线遮挡(甲, 乙)) for 甲, 乙 in 对]
    新热 = [(环境2.链路可用(甲, 乙), 环境2.视线遮挡(甲, 乙)) for 甲, 乙 in 对]

    不一致 = sum(1 for a, b in zip(冷, 热1) if a != b)
    不一致 += sum(1 for a, b in zip(冷, 新冷) if a != b)
    不一致 += sum(1 for a, b in zip(冷, 新热) if a != b)

    行 = [{
        "样本数": len(对),
        "不一致数": 不一致,
        "结论": "通过" if 不一致 == 0 else "失败",
    }]
    写CSV(
        结果目录 / "v6_缓存确定性.csv",
        行,
        ["样本数", "不一致数", "结论"],
    )
    print(f"V6 完成：样本 {len(对)}，不一致 {不一致}；结果写入 {结果目录 / 'v6_缓存确定性.csv'}")


if __name__ == "__main__":
    main()

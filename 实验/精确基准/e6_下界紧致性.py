"""E6：覆盖下界紧致性（非零下界）。

在 E1c 的真实缺口与覆盖表上，逐步限制可用驻留点集合：
- 对每个子集，精确集合覆盖 MILP 求最小未覆盖缺口数；
- 用 `中继驻留排程.覆盖下界` 求严格下界；
- 比较 LB 与精确值；LB 必须 ≤ 精确值，差值衡量紧致性。
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 实验.精确基准.e1c_集成中继覆盖 import (  # noqa: E402
    构造运输方案,
    解集合覆盖,
)
from 实验.实例.构造小实例 import 小实例  # noqa: E402
from 实验.定理验证.公共 import 写CSV  # noqa: E402
from 源代码.公共库.通信中继.场景装配 import 装载场景  # noqa: E402
from 源代码.公共库.通信中继.通信模型 import 由场景装配  # noqa: E402
from 源代码.公共库.通信中继.通信剖面 import 构造剖面  # noqa: E402
from 源代码.公共库.通信中继.缺口解析 import 解析缺口  # noqa: E402
from 源代码.公共库.通信中继.中继覆盖求解 import 生成候选点  # noqa: E402
from 源代码.公共库.通信中继.中继覆盖关系 import 覆盖表, 候选覆盖表  # noqa: E402
from 源代码.公共库.通信中继.中继驻留排程 import 覆盖下界  # noqa: E402

结果目录 = 项目根 / "结果" / "精确基准"
结果目录.mkdir(parents=True, exist_ok=True)


def 子覆盖表(全表: 覆盖表, 点序: tuple[int, ...]) -> 覆盖表:
    点集 = set(点序)
    点集表 = tuple(tuple(p for p in 列 if p in 点集) for 列 in 全表.点集表)
    掩码 = {}
    for i, 列 in enumerate(点集表):
        for p in 列:
            掩码[p] = 掩码.get(p, 0) | (1 << i)
    掩码组: dict[int, list[int]] = {}
    for p in sorted(掩码):
        掩码组.setdefault(掩码[p], []).append(p)
    return 覆盖表(
        候选点表=全表.候选点表,
        驻留点序=tuple(sorted(点集)),
        点集表=点集表,
        海拔表={k: v for k, v in 全表.海拔表.items() if k[0] in 点集},
        掩码=掩码,
        掩码组={k: tuple(v) for k, v in 掩码组.items()},
        统计=dict(全表.统计),
    )


def 主函数() -> None:
    rng = random.Random(20261025)
    实例 = 小实例()
    场景 = 实例.场景
    环境 = 由场景装配(场景)
    剖面表 = 构造剖面(场景, 环境)
    方案 = 构造运输方案(场景)
    缺口集合 = 解析缺口(剖面表, 方案)
    候选点表 = 生成候选点(场景, 环境, 剖面表.网关)
    全表 = 候选覆盖表(剖面表, 环境, 缺口集合, 候选点表, {})
    缺口表 = list(缺口集合.缺口列表)
    全部点 = list(全表.驻留点序)

    行 = []
    规模集 = [1, 2, 4, 8, 12, 16, 24, 32, 48, len(全部点)]
    for 规模 in 规模集:
        次数 = 1 if 规模 == len(全部点) else 12
        for _ in range(次数):
            点序 = tuple(sorted(rng.sample(全部点, min(规模, len(全部点)))))
            子表 = 子覆盖表(全表, 点序)
            结果, 点列 = 解集合覆盖(子表)
            if 结果.success:
                值 = np.asarray(结果.x)
                m = len(点列)
                精确未覆盖 = int(round(float(值[m:].sum())))
                精确驻留点 = int(round(float(值[:m].sum())))
            else:
                精确未覆盖 = -1
                精确驻留点 = -1
            LB, _ = 覆盖下界(子表, 缺口表)
            if 精确未覆盖 >= 0:
                差 = LB - 精确未覆盖
                结论 = "通过" if 差 <= 0 else "失败"
            else:
                差 = ""
                结论 = "MILP失败"
            行.append({
                "点集规模": len(点序),
                "缺口数": len(缺口表),
                "精确最少驻留点": 精确驻留点,
                "精确未覆盖": 精确未覆盖,
                "下界": LB,
                "下界-精确": 差,
                "结论": 结论,
            })
            print(行[-1])

    写CSV(
        结果目录 / "e6_下界紧致性.csv",
        行,
        ["点集规模", "缺口数", "精确最少驻留点", "精确未覆盖", "下界", "下界-精确", "结论"],
    )
    print(f"E6 完成：结果写入 {结果目录}")


if __name__ == "__main__":
    主函数()

"""E3：搜索组件消融（小实例）。

配置：
1. 完整：12 种群 × 4 代 × 3 步长 + 打磨 + 全部种子；
2. 无打磨；
3. 单步长（0 s）；
4. 单种子（只用第一类种子）；
5. 仅贪心种子（不进化）。

指标：前沿规模、可行数、零中断数、HV、IGD（并集非支配前沿为参考）、墙钟。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from pymoo.indicators.hv import HV
from pymoo.indicators.igd import IGD

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 实验.实例.构造小实例 import 子场景, 截断货箱  # noqa: E402
from 实验.定理验证.公共 import 非支配, 写CSV  # noqa: E402
from 源代码.公共库.通信中继.场景装配 import 装载场景  # noqa: E402
from 源代码.公共库.通信中继.通信模型 import 由场景装配  # noqa: E402
from 源代码.公共库.通信中继.通信剖面 import 构造剖面  # noqa: E402
from 源代码.公共库.通信中继.构造启发式 import 构造种子  # noqa: E402
from 源代码.公共库.通信中继.中继覆盖求解 import 生成候选点  # noqa: E402
from 源代码.公共库.通信中继.多目标求解 import 搜索参数  # noqa: E402
from 源代码.公共库.通信中继.联合调度求解 import (  # noqa: E402
    构造联合评价器,
    求解联合,
)

结果目录 = 项目根 / "结果" / "集成实验"
结果目录.mkdir(parents=True, exist_ok=True)

服务区 = ["S009", "S010", "S011", "S014"]
种群 = 8
代数 = 3
步长表 = (0.0, 900.0, 1800.0)


def 建环境():
    全 = 装载场景()
    场景 = 子场景(全, 服务区, 每型无人机数=1, 每型电池数=2)
    场景 = 截断货箱(场景, 3)
    环境 = 由场景装配(场景)
    剖面表 = 构造剖面(场景, 环境)
    候选点表 = 生成候选点(场景, 环境, 剖面表.网关)
    return 场景, 环境, 剖面表, 候选点表


def 主函数() -> None:
    场景, 环境, 剖面表, 候选点表 = 建环境()
    缓存: dict = {}
    种子 = 构造种子(场景)
    评价器 = 构造联合评价器(剖面表, 环境, 候选点表, 缓存, 0.0)

    配置 = [
        ("完整", dict(种子包序列=种子, 错峰步长表=步长表, 打磨=True)),
        ("无打磨", dict(种子包序列=种子, 错峰步长表=步长表, 打磨=False)),
        ("单步长", dict(种子包序列=种子, 错峰步长表=(0.0,), 打磨=True)),
        ("单种子", dict(种子包序列=[种子[0]], 错峰步长表=步长表, 打磨=True)),
    ]

    结果 = {}
    for 名, 参数 in 配置:
        开始 = time.time()
        果 = 求解联合(
            剖面表, 环境, 候选点表=候选点表, 缓存=缓存,
            参数=搜索参数(种群规模=种群, 迭代代数=代数),
            进程数=1, **参数,
        )
        结果[名] = (果.存档, time.time() - 开始)

    # 仅贪心种子
    开始 = time.time()
    结果["仅贪心种子"] = ([评价器(场景, 包列) for _, 包列 in 种子], time.time() - 开始)

    # 参考前沿
    全部 = []
    for 个列, _ in 结果.values():
        for x in 个列:
            if x.是否可行:
                全部.append(tuple(float(v) for v in x.评价.目标向量))
    参考 = np.array(sorted(非支配(全部)), dtype=float)
    尺度 = np.maximum(参考.max(axis=0), 1e-9)
    参考n = 参考 / 尺度
    参考点 = np.maximum(参考n.max(axis=0) * 1.5, 0.5)
    hv = HV(ref_point=参考点)
    igd = IGD(参考n)

    行 = []
    for 名, (个列, 耗时) in 结果.items():
        可行 = [x for x in 个列 if x.是否可行]
        零 = [x for x in 可行 if getattr(x.评价, "零中断", False)]
        向量 = np.array(sorted({tuple(float(v) for v in x.评价.目标向量) for x in 可行}), dtype=float)
        向量n = 向量 / 尺度 if len(向量) else np.zeros((0, 5))
        行.append({
            "配置": 名,
            "前沿规模": len(个列),
            "可行数": len(可行),
            "零中断数": len(零),
            "HV": f"{hv(向量n):.6f}" if len(向量n) else "0",
            "IGD": f"{igd(向量n):.6f}" if len(向量n) else "inf",
            "墙钟_s": f"{耗时:.2f}",
        })
        print(行[-1])

    写CSV(
        结果目录 / "e3_消融.csv",
        行,
        ["配置", "前沿规模", "可行数", "零中断数", "HV", "IGD", "墙钟_s"],
    )
    print(f"E3 完成：结果写入 {结果目录}")


if __name__ == "__main__":
    主函数()

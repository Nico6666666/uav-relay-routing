"""E2b：集成层算法对比（小实例）。

对照四种策略（同一评价器、同一实例）：
1. 本文：分层 NSGA-II + 确定性中继 oracle（含局部打磨）；
2. 无打磨：同一搜索，关闭局部打磨；
3. 贪心种子：只评价 7 类确定性种子，不进化；
4. 随机重启：在确定性种子上随机打乱包序与访问顺序，评价同等次数。

指标：可行解数、零中断解数、HV、IGD（以四种策略的并集非支配前沿为参考）。
"""
from __future__ import annotations

import copy
import json
import random
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
from 源代码.公共库.通信中继.构造启发式 import 构造种子, 载荷包  # noqa: E402
from 源代码.公共库.通信中继.中继覆盖求解 import 生成候选点  # noqa: E402
from 源代码.公共库.通信中继.多目标求解 import 搜索参数  # noqa: E402
from 源代码.公共库.通信中继.联合调度求解 import (  # noqa: E402
    构造联合评价器,
    求解联合,
)

结果目录 = 项目根 / "结果" / "集成实验"
结果目录.mkdir(parents=True, exist_ok=True)

服务区 = ["S009", "S010", "S011", "S014"]
每区箱数 = 3
种群 = 12
代数 = 4
步长表 = (0.0, 900.0, 1800.0)


def 建环境():
    全 = 装载场景()
    场景 = 子场景(全, 服务区, 每型无人机数=1, 每型电池数=2)
    场景 = 截断货箱(场景, 每区箱数)
    环境 = 由场景装配(场景)
    剖面表 = 构造剖面(场景, 环境)
    候选点表 = 生成候选点(场景, 环境, 剖面表.网关)
    return 场景, 环境, 剖面表, 候选点表


def 收集(个体列表):
    可行 = [x for x in 个体列表 if x.是否可行]
    零中断 = [x for x in 可行 if getattr(x.评价, "零中断", False)]
    return 可行, 零中断


def 评价种子(评价器, 场景, 种子):
    return [评价器(场景, 包列) for _, 包列 in 种子]


def 随机重启(评价器, 场景, 种子, 次数, rng):
    出 = []
    for _ in range(次数):
        名, 包列 = 种子[rng.randrange(len(种子))]
        新列 = []
        for 包 in 包列:
            顺序 = list(包.访问顺序)
            rng.shuffle(顺序)
            新列.append(载荷包(箱表=包.箱表, 访问顺序=tuple(顺序)))
        rng.shuffle(新列)
        出.append(评价器(场景, 新列))
    return 出


def 主函数() -> None:
    rng = random.Random(20261025)
    场景, 环境, 剖面表, 候选点表 = 建环境()
    缓存: dict = {}
    种子 = 构造种子(场景)
    评价器 = 构造联合评价器(剖面表, 环境, 候选点表, 缓存, 0.0)

    结果 = {}

    # 1. 本文（含打磨）
    开始 = time.time()
    本文 = 求解联合(
        剖面表, 环境, 种子包序列=种子, 错峰步长表=步长表,
        参数=搜索参数(种群规模=种群, 迭代代数=代数),
        候选点表=候选点表, 缓存=缓存, 打磨=True, 进程数=1,
    )
    结果["本文"] = (本文.存档, time.time() - 开始)

    # 2. 无打磨
    开始 = time.time()
    无打磨 = 求解联合(
        剖面表, 环境, 种子包序列=种子, 错峰步长表=步长表,
        参数=搜索参数(种群规模=种群, 迭代代数=代数),
        候选点表=候选点表, 缓存=缓存, 打磨=False, 进程数=1,
    )
    结果["无打磨"] = (无打磨.存档, time.time() - 开始)

    # 3. 贪心种子
    开始 = time.time()
    个体 = 评价种子(评价器, 场景, 种子)
    结果["贪心种子"] = (个体, time.time() - 开始)

    # 4. 随机重启（同等评价次数）
    次数 = 种群 * 代数 * len(步长表)
    开始 = time.time()
    个体 = 随机重启(评价器, 场景, 种子, 次数, rng)
    结果["随机重启"] = (个体, time.time() - 开始)

    # 参考前沿：四种策略的并集
    全部向量 = []
    for 个列, _ in 结果.values():
        for x in 个列:
            if x.是否可行:
                全部向量.append(tuple(float(v) for v in x.评价.目标向量))
    参考 = np.array(sorted(非支配(全部向量)), dtype=float)
    尺度 = np.maximum(参考.max(axis=0), 1e-9) if len(参考) else np.ones(5)
    参考n = 参考 / 尺度
    参考点 = np.maximum(参考n.max(axis=0) * 1.5, 0.5) if len(参考) else np.ones(5)
    hv = HV(ref_point=参考点)
    igd = IGD(参考n) if len(参考) else None

    行 = []
    for 名, (个列, 耗时) in 结果.items():
        可行, 零中断 = 收集(个列)
        向量 = np.array(sorted({tuple(float(v) for v in x.评价.目标向量) for x in 可行}), dtype=float)
        向量n = 向量 / 尺度 if len(向量) else np.zeros((0, 5))
        (结果目录 / f"e2b_{名}_前沿.json").write_text(
            json.dumps(向量.tolist(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        行.append({
            "策略": 名,
            "评价数": 次数 if 名 == "随机重启" else "",
            "前沿规模": len(个列),
            "可行数": len(可行),
            "零中断数": len(零中断),
            "HV": f"{hv(向量n):.6f}" if len(向量n) else "0",
            "IGD": f"{igd(向量n):.6f}" if (len(向量n) and igd is not None) else "inf",
            "墙钟_s": f"{耗时:.2f}",
        })
        print(行[-1])

    写CSV(
        结果目录 / "e2b_集成对比.csv",
        行,
        ["策略", "评价数", "前沿规模", "可行数", "零中断数", "HV", "IGD", "墙钟_s"],
    )
    (结果目录 / "e2b_参考前沿.json").write_text(
        json.dumps({"参考前沿": 参考.tolist(), "尺度": 尺度.tolist()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"E2b 完成：结果写入 {结果目录}")


if __name__ == "__main__":
    主函数()

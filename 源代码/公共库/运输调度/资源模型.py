"""
资源模型 —— 实体无人机与共享电池的占用状态、以及两阶段等效充电周转。

《电池与能源组件充电周转规则》原文：

    "运输无人机共享电池……均作为独立能源资源记录荷电状态（SOC）……
     同一机型的共享电池可在该机型不同实体无人机之间调度使用，不同机型之间不可混用。
     初始时刻 SOC 均为 100%，任务结束后的剩余 SOC 根据可用能量和实际能耗计算，
     且不得低于返航电量下限；再次投入任务前应充至 100%。"

    "两类能源资源统一采用两阶段等效充电模型：SOC 低于 90% 时为快速阶段，
     0% 至 90% 阶段占等效完全充电时间的 65%；SOC 达到 90% 后进入慢速阶段，
     90% 至 100% 阶段占等效完全充电时间的 35%，各阶段按 SOC 增量线性折算。"

由此得到"从 SOC = s 充至 100%"的时长（T = 等效完全充电时间）：

    s ≥ 0.9 :  充 = T · 0.35 · (1 − s) / 0.10
    s < 0.9 :  充 = T · [ 0.65 · (0.9 − s) / 0.9 + 0.35 ]

两式在 s = 0.9 处连续（同为 0.35T），在 s = 0 处等于 T，在 s = 1 处等于 0。

**同一资源的任务占用与充电时段不得重叠，不同资源可并行充电**（问题设定）。
因此本模块把电池的"可用时刻"定义为 `max(释放时刻, 充电完成时刻)`。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from 源代码.公共库.基础内核.飞行模型 import 机型
from 源代码.公共库.运输调度.配置 import (
    快慢充分界SOC,
    电池目标SOC,
    初始时刻_s,
    快充阶段时间占比,
    慢充阶段时间占比,
    数值容差,
)


# ===================== 充电周转 =====================
def 充电时长(等效完全充电时间: float, 起始SOC: float) -> float:
    """从 `起始SOC` 充至 100% 所需时间（s）。

    两阶段线性折算，在 SOC = 0.9 处连续。
    """
    if 起始SOC >= 电池目标SOC - 数值容差:
        return 0.0
    s = max(起始SOC, 0.0)

    if s >= 快慢充分界SOC - 数值容差:
        # 全程处于慢速阶段
        比例 = 慢充阶段时间占比 * (电池目标SOC - s) / (电池目标SOC - 快慢充分界SOC)
        return 等效完全充电时间 * 比例

    # 快速阶段（s → 0.9）占 0.65，慢速阶段（0.9 → 1.0）占 0.35
    比例 = (
        快充阶段时间占比 * (快慢充分界SOC - s) / 快慢充分界SOC
        + 慢充阶段时间占比
    )
    return 等效完全充电时间 * 比例


def 结束SOC(机: 机型, 能耗: float) -> float:
    """架次结束后的剩余 SOC = 1 − E_trip / E^use。

    它必须 ≥ ρ（返航电量下限）——这与"架次能耗 ≤ 架次能量上限 = (1−ρ)·E^use"
    是**同一个约束**的两种等价写法。
    """
    if 机.电池可用能量 <= 0:
        return 0.0
    return 1.0 - 能耗 / 机.电池可用能量


def 是否低于返航下限(机: 机型, 结束SOC: float) -> bool:
    return 结束SOC < 机.返航安全余量比例 - 数值容差


# ===================== 资源状态 =====================
@dataclass
class 无人机状态:
    """一架实体运输无人机的占用与统计。"""

    编号: str
    机型编号: str
    可用时刻: float = 初始时刻_s
    架次数: int = 0
    累计作业时间: float = 0.0
    累计飞行时间: float = 0.0
    累计能耗: float = 0.0
    最后返回时刻: float = 初始时刻_s


@dataclass
class 电池状态:
    """一组共享电池的占用、SOC 与充电周转。"""

    编号: str
    机型编号: str
    可用时刻: float = 初始时刻_s
    SOC: float = 电池目标SOC
    使用次数: int = 0
    累计放电量: float = 0.0

    def 释放(self, 时刻: float, 结束SOC: float, 等效完全充电时间: float) -> float:
        """任务在 `时刻` 结束、剩余 `结束SOC`：记录状态并返回充至 100% 的时刻。"""
        self.SOC = max(结束SOC, 0.0)
        self.使用次数 += 1
        完成时刻 = 时刻 + 充电时长(等效完全充电时间, self.SOC)
        self.可用时刻 = 完成时刻
        return 完成时刻


@dataclass
class 资源池:
    """多点多架次调度的全部实体无人机与共享电池。"""

    无人机: dict[str, 无人机状态] = field(default_factory=dict)
    电池: dict[str, 电池状态] = field(default_factory=dict)
    机型无人机: dict[str, list[str]] = field(default_factory=dict)
    机型电池: dict[str, list[str]] = field(default_factory=dict)
    电池等效时间: dict[str, float] = field(default_factory=dict)   # 机型 -> 等效完全充电时间（s）

    def 机型无人机列表(self, 机型编号: str) -> list[str]:
        return self.机型无人机.get(机型编号, [])

    def 机型电池列表(self, 机型编号: str) -> list[str]:
        return self.机型电池.get(机型编号, [])

    def 等效完全充电时间(self, 机型编号: str) -> float:
        return self.电池等效时间[机型编号]

    @property
    def 全部无人机(self) -> list[无人机状态]:
        return [self.无人机[k] for k in sorted(self.无人机)]

    @property
    def 全部电池(self) -> list[电池状态]:
        return [self.电池[k] for k in sorted(self.电池)]


def 构造资源池(场景) -> 资源池:
    """按数据中的库存构造资源池：无人机 4A/2B/2C，共享电池 6/4/4，初始 SOC 均为 100%。"""
    池 = 资源池()
    for 编号, 记录 in sorted(场景.无人机表.items()):
        池.无人机[编号] = 无人机状态(编号=编号, 机型编号=记录["机型编号"])
        池.机型无人机.setdefault(记录["机型编号"], []).append(编号)
    for 机型编号, 清单 in 场景.电池清单.items():
        池.机型电池[机型编号] = list(清单)
        池.电池等效时间[机型编号] = 场景.电池表[机型编号]["等效完全充电时间"]
        for 电池编号 in 清单:
            池.电池[电池编号] = 电池状态(编号=电池编号, 机型编号=机型编号)
    for 机型编号 in 池.机型无人机:
        池.机型无人机[机型编号].sort()
    return 池


def 资源容量摘要(场景) -> dict:
    """库存摘要，供论文与自检引用。"""
    return {
        "无人机": {
            机型编号: len(编号列表) for 机型编号, 编号列表 in 场景.无人机清单.items()
        },
        "共享电池": {
            机型编号: 场景.电池表[机型编号]["组数"] for 机型编号 in sorted(场景.电池表)
        },
        "等效完全充电时间_s": {
            机型编号: 场景.电池表[机型编号]["等效完全充电时间"]
            for 机型编号 in sorted(场景.电池表)
        },
    }

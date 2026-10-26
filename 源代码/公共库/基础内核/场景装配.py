"""
场景装配 —— 把输入数据 + 几何量 + 最大安全载荷的载荷能力组装成一个可直接消费的场景对象。

单点往返与组批各子任务（单点往返与组批各子任务）统一从这里取场景，避免各自重复读取与计算导致口径漂移。
"""
from __future__ import annotations

from dataclasses import dataclass

from 源代码.公共库.基础内核 import 地理计算 as 地理计算
from 源代码.公共库.基础内核 import 数据读取 as 数据读取
from 源代码.公共库.基础内核.载荷求解 import 单元结果, 求解单元
from 源代码.公共库.基础内核.配置 import 巡航净空_m
from 源代码.公共库.基础内核.飞行模型 import 机型


@dataclass
class 场景项:
    """一个服务区的几何与需求信息。"""

    服务区: dict
    水平距离: float
    沿线最高地面高程: float
    巡航海拔: float
    DEM采样地面高程: float
    货箱: list[dict]

    @property
    def 编号(self) -> str:
        return self.服务区["编号"]

    @property
    def 地面海拔(self) -> float:
        return self.服务区["海拔"]


@dataclass
class 场景:
    调度中心: dict
    机型表: dict[str, 机型]
    各项: list[场景项]
    地面高程: object = None            # np.ndarray，仅诊断用
    纬度向量: object = None
    经度向量: object = None

    @property
    def 编号顺序(self) -> list[str]:
        return [项.编号 for 项 in self.各项]

    def 取项(self, 服务区编号: str) -> 场景项:
        for 项 in self.各项:
            if 项.编号 == 服务区编号:
                return 项
        raise KeyError(服务区编号)


def 装载场景() -> 场景:
    """读取全部输入数据并算好几何量。"""
    调度中心 = 数据读取.读取调度中心()
    服务区列表 = 数据读取.读取服务区()
    机型表 = {k: 机型.由字典(v) for k, v in 数据读取.读取机型().items()}
    货箱分组 = 数据读取.按服务区归组货箱(数据读取.读取货箱())
    地面高程, 纬度向量, 经度向量 = 数据读取.读取DEM()

    各项 = []
    for 区 in 服务区列表:
        距离 = 地理计算.水平距离_m(调度中心["经度"], 调度中心["纬度"], 区["经度"], 区["纬度"])
        沿线最高 = 地理计算.沿线最高地面高程(
            调度中心["经度"], 调度中心["纬度"], 区["经度"], 区["纬度"], 地面高程, 纬度向量, 经度向量
        )
        各项.append(
            场景项(
                服务区=区,
                水平距离=距离,
                沿线最高地面高程=沿线最高,
                巡航海拔=沿线最高 + 巡航净空_m,
                DEM采样地面高程=地理计算.节点地面高程(区["经度"], 区["纬度"], 地面高程, 纬度向量, 经度向量),
                货箱=货箱分组.get(区["编号"], []),
            )
        )
    return 场景(
        调度中心=调度中心,
        机型表=机型表,
        各项=各项,
        地面高程=地面高程,
        纬度向量=纬度向量,
        经度向量=经度向量,
    )


def 计算最大载荷(场景: 场景, 余量比例: float | None = None) -> list[单元结果]:
    """对全部 (机型, 服务区) 组合求解最大安全载荷 q*。

    `余量比例` 为 None 时取机型表给定的 20%；显式给出时覆盖之（供余量灵敏度灵敏度分析）。
    """
    结果: list[单元结果] = []
    for 项 in 场景.各项:
        for 机编号 in sorted(场景.机型表):
            结果.append(
                求解单元(
                    机=场景.机型表[机编号],
                    服务区=项.服务区,
                    O01地面海拔=场景.调度中心["海拔"],
                    水平距离=项.水平距离,
                    巡航海拔=项.巡航海拔,
                    货箱列表=项.货箱,
                    余量比例=余量比例,
                )
            )
    return 结果


def 载荷字典(结果列表: list[单元结果]) -> dict[str, dict[str, float]]:
    """{(机型, 服务区) -> q*} 的嵌套字典。"""
    出: dict[str, dict[str, float]] = {}
    for r in 结果列表:
        出.setdefault(r.机型编号, {})[r.服务区编号] = r.最大安全载荷
    return 出

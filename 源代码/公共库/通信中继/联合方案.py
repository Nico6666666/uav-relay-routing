"""
联合方案 —— 联合调度与中继的完整解：**运输方案 ⊕ 中继方案 ⊕ 保障关系**。

为什么不扩展 `方案结构.py`
--------------------------
`方案结构.py` 是**逐字搬运**自多点多架次调度的运输侧数据结构（来源头注载明哈希）。
把中继字段塞进去会破坏"逐字保留"的可核验性，且让运输结构与中继结构纠缠。
故**新建本模块**承载联合调度与中继新增的层次：

    中继方案    若干中继架次 + 能源组件周转台账
    联合方案    运输 `全局方案` + `中继方案` + 保障关系

这也是《联合调度与中继编码行动方案》§3.2 中"扩展三个既有模块"的第一项的等价替代
（另两项——`可行性检验` 与 `评价`——仍按原计划就地扩展，因为它们的既有函数
必须保持签名不变才能被复用）。

向分区与资源核算的接口（问题设定要求）
------------------------------
问题明确分区与资源核算"**保持联合调度与中继已经确定的货箱组批、服务区访问顺序、
运输与中继任务安排及通信保障关系不变**"。故本模块的落盘结构必须包含：

| 字段 | 用途 |
|---|---|
| 每个运输架次的**服务区集合** | 分区与资源核算分区时，同架次的服务区必须同组 |
| 每个架次的运输机 / 电池 / 开始时刻 | 分区后按组核算资源 |
| **每个中继架次的保障对象集合** | 中继资源按组核算 |
| 每个中继架次使用的能源组件 | 同上 |
| **通信保障关系**（哪个站保障哪个架次的哪个时段） | 分区后不得跨组调配 |

以上字段全部为**可机读的结构化字段**（dataclass 字段，可直接序列化）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from 源代码.公共库.通信中继.中继模型 import 中继架次


# ===================== 保障关系 =====================
@dataclass(frozen=True)
class 保障记录:
    """一条通信保障关系：某个悬停站在某个时段保障某个运输架次的某个缺口。"""

    中继架次序号: int
    中继机编号: str
    站序: int                    # 该站在本架次内的序号（1 起）
    运输架次序号: int
    缺口序号: int
    起时刻: float
    终时刻: float
    悬停经度: float
    悬停纬度: float
    悬停海拔: float

    @property
    def 时长(self) -> float:
        return self.终时刻 - self.起时刻


# ===================== 中继方案 =====================
@dataclass(eq=False)
class 中继方案:
    """联合调度与中继的中继侧完整解。"""

    架次列表: tuple[中继架次, ...] = ()
    保障记录: tuple[保障记录, ...] = ()
    能源组件使用: tuple[dict, ...] = ()      # 逐次使用的台账（组件编号 / 占用 / SOC / 充电完成）
    未覆盖缺口: tuple[int, ...] = ()          # 未能覆盖的缺口序号（诊断；零中断时应为空）
    统计: dict = field(default_factory=dict)

    # ---------- 聚合 ----------
    @property
    def 架次数(self) -> int:
        return len(self.架次列表)

    @property
    def 总能耗(self) -> float:
        return sum(架.总能耗 for 架 in self.架次列表)

    @property
    def 总服务时长(self) -> float:
        return sum(架.代价.服务时长 for 架 in self.架次列表)

    @property
    def 总飞行时间(self) -> float:
        return sum(架.代价.飞行时间 for 架 in self.架次列表)

    @property
    def 总等待时长(self) -> float:
        return sum(架.代价.等待时长 for 架 in self.架次列表)

    @property
    def 完成时间(self) -> float:
        """全部中继完成最后一个架次并返回 O01 的最晚时刻。"""
        return max((架.返回时刻 for 架 in self.架次列表), default=0.0)

    @property
    def 站数(self) -> int:
        return sum(架.站数 for 架 in self.架次列表)

    @property
    def 一次出动的站数分布(self) -> dict[int, int]:
        出: dict[int, int] = {}
        for 架 in self.架次列表:
            出[架.站数] = 出.get(架.站数, 0) + 1
        return dict(sorted(出.items()))

    @property
    def 零中断(self) -> bool:
        """全部缺口都被覆盖（通信前置条件的最终判据）。"""
        return not self.未覆盖缺口

    def 按中继机(self) -> dict[str, list[中继架次]]:
        出: dict[str, list[中继架次]] = {}
        for 架 in self.架次列表:
            出.setdefault(架.中继机编号, []).append(架)
        for 编号 in 出:
            出[编号].sort(key=lambda 架: 架.起飞时刻)
        return 出

    def 架次的站序列摘要(self) -> list[dict]:
        """逐架次逐站的摘要（供输出表使用）。"""
        出 = []
        for 架 in self.架次列表:
            for 位, 站 in enumerate(架.站序列, start=1):
                出.append(
                    {
                        "中继架次序号": 架.序号,
                        "中继机编号": 架.中继机编号,
                        "能源组件编号": 架.能源组件编号,
                        "架次起飞时刻_s": round(架.起飞时刻, 2),
                        "架次返回时刻_s": round(架.返回时刻, 2),
                        "站序": 位,
                        "悬停经度": round(站.经度, 6),
                        "悬停纬度": round(站.纬度, 6),
                        "地面海拔_m": round(站.地面海拔, 2),
                        "悬停海拔_m": round(站.悬停海拔, 2),
                        "悬停离地_m": round(站.离地高度, 2),
                        "建链起_s": round(站.服务起 - 30.0, 2),
                        "服务起_s": round(站.服务起, 2),
                        "服务终_s": round(站.服务终, 2),
                        "服务时长_s": round(站.服务时长, 2),
                        "保障运输架次": ",".join(str(x) for x in 站.保障架次),
                        "保障缺口数": len(站.保障缺口),
                    }
                )
        return 出


# ===================== 联合方案 =====================
@dataclass(eq=False)
class 联合方案:
    """联合调度与中继的一个完整解：运输方案 + 中继方案。

    `运输方案` 为多点多架次调度的 `全局方案`（`方案结构.全局方案`），
    本模块**不重复定义**它的结构，只做组合。
    """

    运输方案: object                                  # 方案结构.全局方案
    中继方案: 中继方案 = field(default_factory=中继方案)
    检验记录: tuple = ()
    评价记录: object | None = None

    @property
    def 架次数(self) -> int:
        return self.运输方案.架次数

    @property
    def 中继架次数(self) -> int:
        return self.中继方案.架次数

    @property
    def 总能耗(self) -> float:
        """运输与中继总能耗（目标 f3）。"""
        return self.运输方案.总能耗 + self.中继方案.总能耗

    @property
    def 完成时间(self) -> float:
        """联合任务完成时间（目标 f2）：运输与中继完成最后一个架次并返回 O01 的最晚时刻。"""
        return max(self.运输方案.完成时间, self.中继方案.完成时间)

    @property
    def 零中断(self) -> bool:
        return self.中继方案.零中断

    def 逐箱送达(self):
        return self.运输方案.逐箱送达()

    # ---------- 向分区与资源核算的传递 ----------
    def 分区基线(self) -> dict:
        """分区与资源核算所需的可机读基线：架次结构 + 中继保障关系 + 资源占用。"""
        运输架次 = []
        for 架 in self.运输方案.架次列表:
            记录 = self.运输方案.调度表.get(架.序号)
            运输架次.append(
                {
                    "架次序号": 架.序号,
                    "服务区集合": list(架.服务区序列),
                    "各区箱编号": [list(区) for 区 in 架.各区箱编号],
                    "机型": 架.机型编号,
                    "无人机": None if 记录 is None else 记录.无人机编号,
                    "共享电池": None if 记录 is None else 记录.电池编号,
                    "开始时刻_s": None if 记录 is None else 记录.开始时刻,
                    "返回时刻_s": None if 记录 is None else 记录.返回时刻,
                    "能耗_kWh": 架.能耗,
                }
            )
        中继架次 = []
        for 架 in self.中继方案.架次列表:
            中继架次.append(
                {
                    "中继架次序号": 架.序号,
                    "中继机": 架.中继机编号,
                    "能源组件": 架.能源组件编号,
                    "起飞时刻_s": 架.起飞时刻,
                    "返回时刻_s": 架.返回时刻,
                    "能耗_kWh": 架.总能耗,
                    "保障运输架次": list(架.保障架次),
                    "站": [
                        {
                            "经度": 站.经度,
                            "纬度": 站.纬度,
                            "悬停海拔_m": 站.悬停海拔,
                            "服务起_s": 站.服务起,
                            "服务终_s": 站.服务终,
                            "保障缺口": list(站.保障缺口),
                        }
                        for 站 in 架.站序列
                    ],
                }
            )
        return {
            "运输架次": 运输架次,
            "中继架次": 中继架次,
            "保障关系": [
                 {
                    "中继架次序号": 条.中继架次序号,
                    "中继机": 条.中继机编号,
                    "站序": 条.站序,
                    "运输架次序号": 条.运输架次序号,
                    "缺口序号": 条.缺口序号,
                    "起时刻_s": 条.起时刻,
                    "终时刻_s": 条.终时刻,
                }
                for 条 in self.中继方案.保障记录
            ],
        }

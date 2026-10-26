# ============================================================================
# 【搬运模块】来源：源代码/公共库/运输调度/方案结构.py
# 搬运日期：2026-09-24（2026-09-26 术语统一后重新搬运）
# 源文件 SHA-256：9eb5261c8cf8004603d452577bea05c39bcc097c11c53bc366544b18518fbfef
# 改动范围：**仅 import 路径与模块编号引用**（公共库 / 运输调度 → 通信中继；
#           m13/m14/m21/m22/m23/m92 → m31/m32/m33/m34/m35/m91）。
#           正文逻辑逐字保留，未做任何改动。
# 一致性由 文档/使用说明.md《搬运登记表》与上列哈希共同保证。
# ============================================================================
"""
方案结构 —— 架次、调度记录与全局方案的数据结构。

层次：

    架次        一个运输任务单元：机型 + 访问顺序 + 各区箱集 + 代价
    调度记录    把某个架次指派到 (无人机, 电池, 开始时刻) 的结果
    全局方案    全部架次 + 全部调度记录 = 多点多架次调度的完整解

设计的取舍：`架次` 内**缓存**由 `多点飞行模型` 算出的 `架次代价`，
使评价/检验/绘图都只需读缓存，不重复做 DEM 与能耗计算。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from 源代码.公共库.通信中继.多点飞行模型 import 多点架次代价, 架次代价, 逐箱送达时刻


# ===================== 架次的硬时限压力 =====================
def 硬截止时间(箱: dict) -> float | None:
    """一个货箱的硬截止时间：首批截止 与 医疗期望时间 取较紧者；都没有则 None。"""
    候选 = []
    if 箱["是否首批保障"] and 箱["首批截止时间"] is not None:
        候选.append(float(箱["首批截止时间"]))
    if 箱["物资类型"] == "医疗物资" and 箱["期望送达时间"] is not None:
        候选.append(float(箱["期望送达时间"]))
    return min(候选) if 候选 else None


# ===================== 架次 =====================
@dataclass(frozen=True)
class 架次:
    """一个 `O01 → s₁ → … → s_k → O01` 的运输架次。"""

    序号: int
    机型编号: str
    服务区序列: tuple[str, ...]
    各区箱编号: tuple[tuple[str, ...], ...]
    代价: 架次代价
    最紧硬截止: float | None = None

    # ---------- 委托给代价 ----------
    @property
    def 总载质量(self) -> float:
        return self.代价.总载质量

    @property
    def 总装载体积(self) -> float:
        return self.代价.总装载体积

    @property
    def 总箱数(self) -> int:
        return self.代价.总箱数

    @property
    def 能耗(self) -> float:
        return self.代价.总能耗

    @property
    def 飞行时间(self) -> float:
        return self.代价.飞行时间

    @property
    def 作业时间(self) -> float:
        return self.代价.作业时间

    @property
    def 访问服务区数(self) -> int:
        return len(self.服务区序列)

    @property
    def 货箱编号列表(self) -> list[str]:
        return [编号 for 区 in self.各区箱编号 for 编号 in 区]


def 构造架次(
    场景,
    序号: int,
    机型编号: str,
    服务区序列: tuple[str, ...] | list[str],
    各区箱列表: list[list[dict]],
) -> 架次:
    """由"访问顺序 + 逐区箱集"装配一个架次（含完整代价与硬时限压力）。"""
    机 = 场景.机型表[机型编号]
    代价 = 多点架次代价(场景, 机, 服务区序列, 各区箱列表)

    截止候选 = [
        硬截止时间(箱) for 区 in 各区箱列表 for 箱 in 区
    ]
    截止候选 = [d for d in 截止候选 if d is not None]

    return 架次(
        序号=序号,
        机型编号=机型编号,
        服务区序列=tuple(服务区序列),
        各区箱编号=tuple(tuple(b["货箱编号"] for b in 区) for 区 in 各区箱列表),
        代价=代价,
        最紧硬截止=min(截止候选) if 截止候选 else None,
    )


# ===================== 调度记录 =====================
@dataclass(frozen=True)
class 调度记录:
    """一个架次在资源与时间轴上的落位。"""

    架次序号: int
    机型编号: str
    无人机编号: str
    电池编号: str
    开始时刻: float                 # 开始工位准备（= 离开 O01 的作业起点）
    返回时刻: float                 # 完成最后一个架次返回 O01
    起始SOC: float                  # 恒为 1.0（"再次投入任务前应充至 100%"）
    结束SOC: float                  # 1 − E_trip / E^use；约束为 结束SOC ≥ ρ（返航电量下限）
    电池可用时刻: float             # 充至 100% 的时刻（= 该电池下次可用时刻）

    @property
    def 作业时间(self) -> float:
        return self.返回时刻 - self.开始时刻

    @property
    def 充电时长(self) -> float:
        return self.电池可用时刻 - self.返回时刻


# ===================== 全局方案 =====================
@dataclass
class 全局方案:
    """多点多架次调度的一个完整解。"""

    架次列表: list[架次] = field(default_factory=list)
    调度表: dict[int, 调度记录] = field(default_factory=dict)

    # ---------- 聚合 ----------
    @property
    def 架次数(self) -> int:
        return len(self.架次列表)

    @property
    def 总能耗(self) -> float:
        return sum(a.能耗 for a in self.架次列表)

    @property
    def 总飞行时间(self) -> float:
        return sum(a.飞行时间 for a in self.架次列表)

    @property
    def 完成时间(self) -> float:
        """全部任务完成时间 = 所有运输无人机完成最后一个架次并返回 O01 的最晚时刻。"""
        return max((r.返回时刻 for r in self.调度表.values()), default=0.0)

    @property
    def 最紧截止(self) -> float | None:
        候选 = [a.最紧硬截止 for a in self.架次列表 if a.最紧硬截止 is not None]
        return min(候选) if 候选 else None

    @property
    def 按机型架次数(self) -> dict[str, int]:
        出: dict[str, int] = {}
        for a in self.架次列表:
            出[a.机型编号] = 出.get(a.机型编号, 0) + 1
        return 出

    @property
    def 按机型能耗(self) -> dict[str, float]:
        出: dict[str, float] = {}
        for a in self.架次列表:
            出[a.机型编号] = 出.get(a.机型编号, 0.0) + a.能耗
        return 出

    def 取架次(self, 序号: int) -> 架次:
        for a in self.架次列表:
            if a.序号 == 序号:
                return a
        raise KeyError(序号)

    # ---------- 派生视图 ----------
    def 逐箱送达(self) -> list[tuple[str, str, float]]:
        """全部货箱的 (货箱编号, 服务区编号, 送达时刻)。"""
        出 = []
        for a in self.架次列表:
            记录 = self.调度表[a.序号]
            出.extend(逐箱送达时刻(a.代价, [list(x) for x in a.各区箱编号], 记录.开始时刻))
        return 出

    def 箱归属表(self) -> dict[str, int]:
        """{货箱编号: 架次序号}。"""
        出: dict[str, int] = {}
        for a in self.架次列表:
            for 箱编号 in a.货箱编号列表:
                出[箱编号] = a.序号
        return 出

    def 各无人机架次(self) -> dict[str, list[架次]]:
        出: dict[str, list[架次]] = {}
        for a in self.架次列表:
            记录 = self.调度表[a.序号]
            出.setdefault(记录.无人机编号, []).append(a)
        for 编号 in 出:
            出[编号].sort(key=lambda x: self.调度表[x.序号].开始时刻)
        return 出

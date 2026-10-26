"""
飞行模型 —— 时间与能源规则内核（F1–F7、F10）。

    F1  水平航段距离      d                 （地理计算.水平距离_m）
    F2  计划巡航海拔      H = 沿线DEM最高地面高程 + 50
    F3  作业高度          O01 = 地面海拔；服务区 = 地面海拔 + 30
    F4  四段高差          去程 (Δh+_out, Δh-_out)，回程 (Δh+_ret, Δh-_ret)
    F5  等效航程          L_g(q) = L0 - (L0 - LF) * (q/Q)^(3/2)
    F6  航段能耗          E = E^hor + E^up
                          E^hor = E^use * d / L_g(q)
                          E^up  = (m0 + q) * g * Δh+ / (η_up * 3.6e6)
    F7  架次总能耗        E_trip(q) = E_seg(q, Δh+_out) + E_seg(0, Δh+_ret)
    F10 航段时间          t = Δh+/v↑ + d/v^c + Δh-/v↓

关键口径（务必与论文一致）：
    * 返航段（Si→O01）的起点作业高度是 **服务区地面海拔 + 30 m**，
      因为"每次投送后均从30米作业高度重新爬升"（时间与能源规则原文）。
      故 Δh+ 与 Δh- 在去/回两段互换。
    * 下降能耗效率取 0 ⇒ 不单独计算下降附加能耗，下降阶段只计水平巡航项。
    * E_trip(q) 关于 q 严格单调递增 ⇒ 能量可行域 [0, q_energy] 是区间，q_energy 唯一。
"""
from __future__ import annotations

from dataclasses import dataclass

from 源代码.公共库.基础内核.配置 import (
    服务区作业高度增量_m,
    焦耳每千瓦时,
    调度中心作业高度增量_m,
    重力加速度,
)


# ===================== 机型（从输入数据 JSON 装配）=====================
@dataclass(frozen=True)
class 机型:
    编号: str
    名称: str
    空载总质量: float          # 含电池空载总质量（kg）
    最大载货质量: float        # Q_g（kg）
    可用装载体积: float        # V_g（m^3）
    巡航速度: float            # v^c（m/s）
    空载标准航程: float        # L0（m）
    满载标准航程: float        # LF（m）
    电池可用能量: float        # E^use：单组电池**满电**总能量（kWh）
    返航电量下限: float        # rho（%）：任务结束时剩余 SOC 的**下限**
    工位固定准备时间: float
    每箱装载时间: float
    接收点基础交接时间: float
    每箱增加交接时间: float
    最大爬升速度: float        # v↑（m/s）
    最大下降速度: float        # v↓（m/s）
    爬升能耗效率: float        # η_up
    下降能耗效率: float        # η_down（0 = 不计下降附加能耗）

    @classmethod
    def 由字典(cls, 字典: dict) -> "机型":
        字段 = set(cls.__dataclass_fields__) - {"编号", "名称"}
        缺失 = 字段 - set(字典)
        if 缺失:
            raise KeyError(f"机型 {字典.get('编号')} 缺少字段: {sorted(缺失)}")
        return cls(**{k: 字典[k] for k in cls.__dataclass_fields__})

    @property
    def 返航安全余量比例(self) -> float:
        """ρ_g：返航安全余量**比例**（时间与能源规则 用语），无量纲，= 返航电量下限 / 100。

        它与数据字段「返航电量下限（%）」是**同一个数**的两种写法，不是另一个物理量：
        前者的名字用于能量不等式，后者是数据文件给出的百分数形式。
        """
        return self.返航电量下限 / 100.0

    @property
    def 架次能量上限(self) -> float:
        """(1 − ρ)·E^use（kWh）—— 返航安全余量**约束** E_trip ≤ (1−ρ)·E^use 的右端上限。

        取名"上限"而非"可用能量"，是为与 `电池可用能量`（E^use，满电总能量）区分：
        一个架次最多只能消耗这么多能量，剩下的 ρ·E^use 是留给返航的余量。
        等价说法：架次结束时电池剩余 SOC 不得低于 ρ。
        """
        return (1.0 - self.返航安全余量比例) * self.电池可用能量


# ===================== F5 等效航程 =====================
def 等效航程(机: 机型, 载荷: float) -> float:
    """L_g(q) = L0 - (L0 - LF) * (q / Q)^(3/2)，定义域 0 <= q <= Q。"""
    if 机.最大载货质量 <= 0:
        raise ValueError("最大载货质量必须为正")
    q = min(max(载荷, 0.0), 机.最大载货质量)
    return 机.空载标准航程 - (机.空载标准航程 - 机.满载标准航程) * (q / 机.最大载货质量) ** 1.5


# ===================== F6 航段能耗 =====================
def 航段水平能耗(机: 机型, 水平距离: float, 载荷: float) -> float:
    """E^hor(q) = E^use * d / L_g(q)，单位 kWh。"""
    return 机.电池可用能量 * 水平距离 / 等效航程(机, 载荷)


def 航段爬升能耗(机: 机型, 爬升高度: float, 载荷: float) -> float:
    """E^up = (m0 + q) * g * Δh+ / (η_up * 3.6e6)，单位 kWh。

    下降能耗效率取 0 ⇒ 只对爬升段计附加能耗。
    """
    if 爬升高度 <= 0.0:
        return 0.0
    return (机.空载总质量 + 载荷) * 重力加速度 * 爬升高度 / (机.爬升能耗效率 * 焦耳每千瓦时)


def 航段能耗(机: 机型, 水平距离: float, 爬升高度: float, 载荷: float) -> float:
    """F6：E = E^hor + E^up（kWh）。"""
    return 航段水平能耗(机, 水平距离, 载荷) + 航段爬升能耗(机, 爬升高度, 载荷)


# ===================== F10 航段时间 =====================
def 航段时间(机: 机型, 水平距离: float, 爬升高度: float, 下降高度: float) -> float:
    """t = Δh+/v↑ + d/v^c + Δh-/v↓（s）。"""
    return (
        max(爬升高度, 0.0) / 机.最大爬升速度
        + 水平距离 / 机.巡航速度
        + max(下降高度, 0.0) / 机.最大下降速度
    )


# ===================== F2 + F4 + F7 单点往返 =====================
@dataclass(frozen=True)
class 往返代价:
    """单点往返 O01 → Si → O01 的代价。"""

    水平距离: float          # d（m）
    巡航海拔: float          # H（m）
    去程爬升: float          # Δh+_out（m）
    去程下降: float          # Δh-_out（m）
    回程爬升: float          # Δh+_ret（m）
    回程下降: float          # Δh-_ret（m）
    去程水平能耗: float      # kWh
    去程爬升能耗: float      # kWh
    回程水平能耗: float      # kWh
    回程爬升能耗: float      # kWh
    去程时间: float          # s
    回程时间: float          # s

    @property
    def 去程能耗(self) -> float:
        return self.去程水平能耗 + self.去程爬升能耗

    @property
    def 回程能耗(self) -> float:
        return self.回程水平能耗 + self.回程爬升能耗

    @property
    def 架次总能耗(self) -> float:
        """F7：E_trip(q)。"""
        return self.去程能耗 + self.回程能耗

    @property
    def 架次总时间(self) -> float:
        return self.去程时间 + self.回程时间


def 单点往返代价(
    机: 机型,
    水平距离: float,
    巡航海拔: float,
    O01地面海拔: float,
    服务区地面海拔: float,
    载荷: float,
) -> 往返代价:
    """O01 → Si → O01 单点往返：去程载货 `载荷`，回程空载。

    四段高差（F4）：
        去程  Δh+_out = H - (O01地面海拔 + 0)
              Δh-_out = H - (服务区地面海拔 + 30)
        回程  Δh+_ret = H - (服务区地面海拔 + 30)    ← 投送后即在 30 m 作业高度
              Δh-_ret = H - (O01地面海拔 + 0)
    """
    O01作业高度 = O01地面海拔 + 调度中心作业高度增量_m
    服务区作业高度 = 服务区地面海拔 + 服务区作业高度增量_m

    去程爬升 = max(巡航海拔 - O01作业高度, 0.0)
    去程下降 = max(巡航海拔 - 服务区作业高度, 0.0)
    回程爬升 = max(巡航海拔 - 服务区作业高度, 0.0)
    回程下降 = max(巡航海拔 - O01作业高度, 0.0)

    return 往返代价(
        水平距离=水平距离,
        巡航海拔=巡航海拔,
        去程爬升=去程爬升,
        去程下降=去程下降,
        回程爬升=回程爬升,
        回程下降=回程下降,
        去程水平能耗=航段水平能耗(机, 水平距离, 载荷),
        去程爬升能耗=航段爬升能耗(机, 去程爬升, 载荷),
        回程水平能耗=航段水平能耗(机, 水平距离, 0.0),
        回程爬升能耗=航段爬升能耗(机, 回程爬升, 0.0),
        去程时间=航段时间(机, 水平距离, 去程爬升, 去程下降),
        回程时间=航段时间(机, 水平距离, 回程爬升, 回程下降),
    )

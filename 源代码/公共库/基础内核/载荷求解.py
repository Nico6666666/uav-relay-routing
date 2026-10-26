"""
载荷求解 —— F8 能量受限载荷 + F9 最大安全载荷（双约束整箱）。

    F8  q_energy = max{ q ∈ [0, Q_g] : E_trip(q) <= (1 - rho_g) * E^use_g }
        E_trip(q) 关于 q 严格单调递增 ⇒ 折半求解唯一，另用 Brent 法互验。

    F9  q*(g, i) = max{ Σ_{b∈B} m_b : B ⊆ 货箱(i),
                        Σ_{b∈B} m_b <= min(Q_g, q_energy),
                        Σ_{b∈B} v_b <= V_g }        ← 货箱不可拆分

`余量比例` 可显式覆盖（供余量灵敏度的返航安全余量灵敏度分析使用），默认取机型表中的
"返航电量下限（%）"。

受限因素归因（N1-c 口径，逐级判定）：
    层级 L1 = min(Q_g, q_energy)                质量 / 返航能量上限
    层级 L2 = 无体积约束下 <= L1 的最大整箱组合   整箱离散
    层级 L3 = 双约束下的最大整箱组合 = q*          叠加体积
        L3 == L1        → 恰好可达（并注明 L1 来自质量还是返航能量）
        L3 == L2 < L1   → 整箱离散受限
        L3 <  L2        → 体积受限
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq

from 源代码.公共库.基础内核.配置 import 二分迭代次数, 体积离散单位_m3, 质量离散单位_kg
from 源代码.公共库.基础内核.飞行模型 import 单点往返代价, 机型

数值容差 = 1e-9


# ===================== F8 能量受限载荷 =====================
def 架次总能耗(
    机: 机型, 水平距离: float, 巡航海拔: float, O01地面海拔: float, 服务区地面海拔: float, 载荷: float
) -> float:
    return 单点往返代价(机, 水平距离, 巡航海拔, O01地面海拔, 服务区地面海拔, 载荷).架次总能耗


def 架次能量上限(机: 机型, 余量比例: float | None = None) -> float:
    """(1 − ρ)·E^use（kWh）—— 返航安全余量约束的右端上限。

    `余量比例` 为 None 时取机型表给定值（ρ = 返航电量下限 / 100）。
    详见 `公共库.飞行模型.机型.架次能量上限` 的命名说明。
    """
    rho = 机.返航安全余量比例 if 余量比例 is None else float(余量比例)
    return (1.0 - rho) * 机.电池可用能量


def 能量受限载荷(
    机: 机型,
    水平距离: float,
    巡航海拔: float,
    O01地面海拔: float,
    服务区地面海拔: float,
    余量比例: float | None = None,
) -> float:
    """F8：返航安全余量下允许的最大连续载荷 q_energy（kg）。

    若满载 Q_g 已满足余量要求，则 q_energy = Q_g（记为"未受返航能量限制"）。
    """
    上限 = 机.最大载货质量
    能量限 = 架次能量上限(机, 余量比例)

    if 架次总能耗(机, 水平距离, 巡航海拔, O01地面海拔, 服务区地面海拔, 上限) <= 能量限:
        return 上限

    def 余量函数(q: float) -> float:
        return 架次总能耗(机, 水平距离, 巡航海拔, O01地面海拔, 服务区地面海拔, q) - 能量限

    低, 高 = 0.0, 上限
    for _ in range(二分迭代次数):
        中 = 0.5 * (低 + 高)
        if 余量函数(中) <= 0.0:
            低 = 中
        else:
            高 = 中
    折半解 = 低

    brent解 = brentq(余量函数, 0.0, 上限, xtol=1e-12, rtol=1e-15) if 余量函数(0.0) <= 0.0 else 0.0
    if abs(折半解 - brent解) > 1e-6:
        raise RuntimeError(f"q_energy 两种解法不一致: 折半={折半解} Brent={brent解}")
    return 折半解


# ===================== F9 二维背包：双约束整箱最大质量 =====================
def 最大整箱组合(货箱列表: list[dict], 质量上限: float, 体积上限: float) -> tuple[float, list[int]]:
    """0/1 二维背包：最大化 Σ质量，受 Σ质量 <= 质量上限 且 Σ体积 <= 体积上限。

    返回 (最大质量, 取用的货箱下标)。体积上限允许为 inf（"无体积约束"情形）。
    """
    if not 货箱列表 or 质量上限 <= 0.0 or 体积上限 <= 0.0:
        return 0.0, []

    质量格 = int(np.floor(质量上限 / 质量离散单位_kg + 数值容差))
    体积格 = int(np.floor(体积上限 / 体积离散单位_m3 + 数值容差)) if np.isfinite(体积上限) else 10**9
    体积格 = min(体积格, int(sum(b["体积"] for b in 货箱列表) / 体积离散单位_m3) + 1)
    if 质量格 <= 0 or 体积格 <= 0:
        return 0.0, []

    物品 = []
    for 箱 in 货箱列表:
        w = int(round(箱["质量"] / 质量离散单位_kg))
        c = int(round(箱["体积"] / 体积离散单位_m3))
        if w <= 0 or w > 质量格 or c > 体积格:
            continue
        物品.append((w, c))
    if not 物品:
        return 0.0, []

    可达 = np.zeros((体积格 + 1, 质量格 + 1), dtype=bool)
    可达[0, 0] = True
    父亲: dict[tuple[int, int], tuple[int, int, int]] = {}

    for 序号, (w, c) in enumerate(物品):
        for v in range(体积格, c - 1, -1):
            来源 = np.flatnonzero(可达[v - c, : 质量格 + 1 - w] & ~可达[v, w:])
            for m0 in 来源:
                可达[v, w + m0] = True
                父亲[(v, w + m0)] = (v - c, int(m0), 序号)

    for 目标质量格 in range(质量格, -1, -1):
        列 = np.flatnonzero(可达[:, 目标质量格])
        if 列.size:
            v, m = int(列.min()), 目标质量格
            取用: list[int] = []
            while (v, m) != (0, 0):
                前v, 前m, 序号 = 父亲[(v, m)]
                取用.append(序号)
                v, m = 前v, 前m
            取用.reverse()
            return 目标质量格 * 质量离散单位_kg, 取用
    return 0.0, []


def 枚举最大整箱组合(货箱列表: list[dict], 质量上限: float, 体积上限: float) -> tuple[float, list[int]]:
    """全枚举校验版（货箱数 <= 20 时使用）。"""
    n = len(货箱列表)
    if n > 20:
        raise ValueError("全枚举仅用于货箱数 <= 20 的校验")
    最优质量, 最优下标 = 0.0, []
    for 掩码 in range(1 << n):
        质 = 体 = 0.0
        下标 = []
        for k in range(n):
            if 掩码 >> k & 1:
                质 += 货箱列表[k]["质量"]
                体 += 货箱列表[k]["体积"]
                下标.append(k)
                if 质 > 质量上限 + 数值容差 or 体 > 体积上限 + 数值容差:
                    break
        else:
            if 质 > 最优质量 + 数值容差:
                最优质量, 最优下标 = 质, 下标
    return 最优质量, 最优下标


# ===================== 单元结果 =====================
@dataclass
class 单元结果:
    机型编号: str
    服务区编号: str
    水平距离: float
    巡航海拔: float
    O01地面海拔: float
    服务区地面海拔: float
    去程爬升: float
    去程下降: float
    回程爬升: float
    回程下降: float
    最大载货质量: float              # Q_g
    可用装载体积: float              # V_g
    返航安全余量比例: float          # 本次计算实际使用的 rho
    能量受限载荷: float              # q_energy
    连续质量上限: float              # L1 = min(Q_g, q_energy)
    无体积整箱上限: float            # L2
    最大安全载荷: float              # q* = L3
    装载组合: list[str] = field(default_factory=list)
    装载质量: float = 0.0
    装载体积: float = 0.0
    受限因素: str = ""
    能量是否受限: bool = False
    去程水平能耗: float = 0.0
    去程爬升能耗: float = 0.0
    回程水平能耗: float = 0.0
    回程爬升能耗: float = 0.0
    架次总能耗: float = 0.0
    能量上限占用率: float = 0.0
    去程时间: float = 0.0
    回程时间: float = 0.0
    架次飞行时间: float = 0.0


def 求解单元(
    机: 机型,
    服务区: dict,
    O01地面海拔: float,
    水平距离: float,
    巡航海拔: float,
    货箱列表: list[dict],
    余量比例: float | None = None,
) -> 单元结果:
    """求解单个 (机型, 服务区) 单元。"""
    rho = 机.返航安全余量比例 if 余量比例 is None else float(余量比例)
    q_能量 = 能量受限载荷(机, 水平距离, 巡航海拔, O01地面海拔, 服务区["海拔"], 余量比例)
    L1 = min(机.最大载货质量, q_能量)

    L2, _ = 最大整箱组合(货箱列表, L1, float("inf"))
    q_star, 下标 = 最大整箱组合(货箱列表, L1, 机.可用装载体积)

    取用箱 = [货箱列表[k] for k in 下标]
    装载质量 = sum(b["质量"] for b in 取用箱)
    装载体积 = sum(b["体积"] for b in 取用箱)

    能量受限 = q_能量 < 机.最大载货质量 - 数值容差
    if abs(q_star - L1) <= 数值容差:
        受限因素 = "恰好可达（" + ("返航能量约束" if 能量受限 else "最大载货质量约束") + "）"
    elif abs(q_star - L2) <= 数值容差:
        受限因素 = "整箱离散受限"
    else:
        受限因素 = "体积受限"

    代价 = 单点往返代价(机, 水平距离, 巡航海拔, O01地面海拔, 服务区["海拔"], q_star)
    能量上限 = 架次能量上限(机, 余量比例)

    return 单元结果(
        机型编号=机.编号,
        服务区编号=服务区["编号"],
        水平距离=水平距离,
        巡航海拔=巡航海拔,
        O01地面海拔=O01地面海拔,
        服务区地面海拔=服务区["海拔"],
        去程爬升=代价.去程爬升,
        去程下降=代价.去程下降,
        回程爬升=代价.回程爬升,
        回程下降=代价.回程下降,
        最大载货质量=机.最大载货质量,
        可用装载体积=机.可用装载体积,
        返航安全余量比例=rho,
        能量受限载荷=q_能量,
        连续质量上限=L1,
        无体积整箱上限=L2,
        最大安全载荷=q_star,
        装载组合=[b["货箱编号"] for b in 取用箱],
        装载质量=装载质量,
        装载体积=装载体积,
        受限因素=受限因素,
        能量是否受限=能量受限,
        去程水平能耗=代价.去程水平能耗,
        去程爬升能耗=代价.去程爬升能耗,
        回程水平能耗=代价.回程水平能耗,
        回程爬升能耗=代价.回程爬升能耗,
        架次总能耗=代价.架次总能耗,
        能量上限占用率=代价.架次总能耗 / 能量上限 if 能量上限 > 0 else float("inf"),
        去程时间=代价.去程时间,
        回程时间=代价.回程时间,
        架次飞行时间=代价.架次总时间,
    )

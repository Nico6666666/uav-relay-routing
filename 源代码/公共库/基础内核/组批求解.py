"""
组批内核 —— 单点往返与组批可行组批 / 精确前沿 / 余量灵敏度共用的货箱组批算法。

问题约束（单点往返与组批）：
    * 每个架次采用 O01→Si→O01 直接往返，**仅服务一个服务区**（不得跨服务区组批）
    * 货箱不可拆分，每个货箱只能安排一次
    * 每个架次须满足：载质量 <= q*(机型, 服务区)、装载体积 <= V_g、返航安全能量余量
      （q* 由最大安全载荷给出，已含质量/能量/体积三重约束；此处再按实际箱组合核算体积）
    * 同一服务区可采用不同机型（已确认允许混用）

两个算法：
    `贪心组批`      首次适应递减（FFD）—— 只求可行解，用于可行组批
    `精确组批前沿`  按箱型剩余数做动态规划，在三维目标
                    (架次数, 总能耗, 该区最大架次作业时间) 上求**精确 Pareto 前沿**，
                    用于精确前沿的 ε-约束多目标优化

作业时间口径（已确认）：
    单架次作业时间 = 工位固定准备时间 + 每箱装载时间×箱数 + 去程飞行 + 回程飞行
                   + 接收点基础交接时间 + 每箱增加交接时间×箱数
    服务区作业时间 = 该区各架次作业时间的**最大值**（区内架次并行）
    累计作业时间   = 各服务区作业时间之和（区间累加）

注：同型货箱的质量与体积完全相同，故按"箱型计数向量"决策与逐箱决策等价。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from itertools import product

from 源代码.公共库.基础内核.飞行模型 import 单点往返代价, 机型

数值容差 = 1e-9

# 物资类型的规范顺序（决定箱计数向量各分量的含义）
物资类型顺序 = ("医疗物资", "饮用水", "应急食品", "生活卫生用品")


# ===================== 数据结构 =====================
@dataclass(frozen=True)
class 架次:
    """一个 O01→Si→O01 的运输架次。"""

    机型编号: str
    箱计数: tuple[int, ...]
    箱编号: tuple[str, ...]
    质量: float
    体积: float
    能耗: float                    # kWh
    作业时间: float                # s

    @property
    def 箱数(self) -> int:
        return sum(self.箱计数)


@dataclass
class 组批方案:
    """某个服务区的完整组批方案。"""

    服务区编号: str
    架次列表: list[架次] = field(default_factory=list)

    @property
    def 架次数(self) -> int:
        return len(self.架次列表)

    @property
    def 总质量(self) -> float:
        return sum(a.质量 for a in self.架次列表)

    @property
    def 总能耗(self) -> float:
        return sum(a.能耗 for a in self.架次列表)

    @property
    def 作业时间(self) -> float:
        """服务区作业时间 = 各架次作业时间的最大值（区内并行）。"""
        return max((a.作业时间 for a in self.架次列表), default=0.0)


@dataclass
class 全局方案:
    """15 个服务区的完整组批方案。"""

    各区方案: dict[str, 组批方案] = field(default_factory=dict)

    @property
    def 全部架次(self) -> list[架次]:
        return [a for 方案 in self.各区方案.values() for a in 方案.架次列表]

    @property
    def 总架次数(self) -> int:
        return sum(方案.架次数 for 方案 in self.各区方案.values())

    @property
    def 总能耗(self) -> float:
        return sum(方案.总能耗 for 方案 in self.各区方案.values())

    @property
    def 累计作业时间(self) -> float:
        """各服务区作业时间之和（区内并行、区间累加）。"""
        return sum(方案.作业时间 for 方案 in self.各区方案.values())

    @property
    def 全局最大架次时间(self) -> float:
        """所有架次中最长的一个（对照口径）。"""
        return max((a.作业时间 for a in self.全部架次), default=0.0)


# ===================== 服务区上下文 =====================
@dataclass(frozen=True)
class 服务区上下文:
    """计算架次代价所需的一切。"""

    服务区编号: str
    水平距离: float
    巡航海拔: float
    O01地面海拔: float
    服务区地面海拔: float
    最大载荷: dict[str, float]           # 机型编号 -> q*（kg）
    物资类型: tuple[str, ...]
    箱型质量: tuple[float, ...]
    箱型体积: tuple[float, ...]

    def 可用机型(self, 机型表: dict[str, 机型]) -> list[str]:
        return [g for g in 机型表 if self.最大载荷.get(g, 0.0) > 数值容差]


def 构造上下文(
    服务区编号: str,
    水平距离: float,
    巡航海拔: float,
    O01地面海拔: float,
    服务区地面海拔: float,
    最大载荷: dict[str, float],
    货箱列表: list[dict],
) -> 服务区上下文:
    类型集 = {b["物资类型"] for b in 货箱列表}
    顺序 = tuple(t for t in 物资类型顺序 if t in 类型集)
    质量表 = {b["物资类型"]: b["质量"] for b in 货箱列表}
    体积表 = {b["物资类型"]: b["体积"] for b in 货箱列表}
    return 服务区上下文(
        服务区编号=服务区编号,
        水平距离=水平距离,
        巡航海拔=巡航海拔,
        O01地面海拔=O01地面海拔,
        服务区地面海拔=服务区地面海拔,
        最大载荷=dict(最大载荷),
        物资类型=顺序,
        箱型质量=tuple(质量表[t] for t in 顺序),
        箱型体积=tuple(体积表[t] for t in 顺序),
    )


def 初始箱计数(上下文: 服务区上下文, 货箱列表: list[dict]) -> tuple[int, ...]:
    """把逐箱清单折算为按箱型的计数向量。"""
    计数 = [0] * len(上下文.物资类型)
    for b in 货箱列表:
        计数[上下文.物资类型.index(b["物资类型"])] += 1
    return tuple(计数)


def 分配箱编号(上下文: 服务区上下文, 货箱列表: list[dict], 计数序列: list[tuple[int, ...]]) -> list[tuple[str, ...]]:
    """按顺序给多个架次分配具体的货箱编号（同类货箱按编号升序取，保证每箱只用一次）。"""
    池: dict[str, list[str]] = {}
    for b in sorted(货箱列表, key=lambda x: x["货箱编号"]):
        池.setdefault(b["物资类型"], []).append(b["货箱编号"])
    游标 = {t: 0 for t in 上下文.物资类型}
    结果 = []
    for 计数 in 计数序列:
        编号列表: list[str] = []
        for t, k in zip(上下文.物资类型, 计数):
            段 = 池[t][游标[t]:游标[t] + k]
            if len(段) != k:
                raise RuntimeError(f"{上下文.服务区编号}：{t} 箱数不足，组批方案与逐箱清单不符")
            编号列表.extend(段)
            游标[t] += k
        结果.append(tuple(编号列表))
    return 结果


# ===================== 单架次代价 =====================
def 单架次代价(上下文: 服务区上下文, 机: 机型, 计数: tuple[int, ...]) -> tuple[float, float, float, float]:
    """返回 (质量 kg, 体积 m^3, 能耗 kWh, 作业时间 s)。"""
    质量 = sum(k * m for k, m in zip(计数, 上下文.箱型质量))
    体积 = sum(k * v for k, v in zip(计数, 上下文.箱型体积))
    箱数 = sum(计数)
    代价 = 单点往返代价(
        机, 上下文.水平距离, 上下文.巡航海拔, 上下文.O01地面海拔, 上下文.服务区地面海拔, 质量
    )
    作业时间 = (
        机.工位固定准备时间
        + 机.每箱装载时间 * 箱数
        + 代价.去程时间
        + 机.接收点基础交接时间
        + 机.每箱增加交接时间 * 箱数
        + 代价.回程时间
    )
    return 质量, 体积, 代价.架次总能耗, 作业时间


def _可行(上下文: 服务区上下文, 机: 机型, 计数: tuple[int, ...]) -> bool:
    if sum(计数) == 0:
        return False
    质量, 体积, _, _ = 单架次代价(上下文, 机, 计数)
    return (
        质量 <= 上下文.最大载荷.get(机.编号, 0.0) + 数值容差
        and 体积 <= 机.可用装载体积 + 数值容差
    )


# ===================== 算法一：贪心首次适应递减（用于可行组批）=====================
def 贪心组批(
    上下文: 服务区上下文,
    货箱列表: list[dict],
    机型表: dict[str, 机型],
    机型优先级: list[str] | None = None,
) -> 组批方案:
    """只求可行解。

    货箱按质量降序，依次尝试放入首个可容纳的已开启架次；放不下则新开架次，
    新架次按 `机型优先级`（默认最大载货质量降序）取第一个能承运该箱的机型。
    """
    优先级 = 机型优先级 or sorted(上下文.可用机型(机型表), key=lambda g: (-机型表[g].最大载货质量, g))

    待装 = sorted(货箱列表, key=lambda b: (-b["质量"], -b["体积"], b["货箱编号"]))

    已开: list[tuple[str, list[int]]] = []
    箱位: list[list[dict]] = []

    for 箱 in 待装:
        τ = 上下文.物资类型.index(箱["物资类型"])
        放好 = False
        for 序号, (机编号, 计数) in enumerate(已开):
            试 = list(计数)
            试[τ] += 1
            if _可行(上下文, 机型表[机编号], tuple(试)):
                已开[序号] = (机编号, 试)
                箱位[序号].append(箱)
                放好 = True
                break
        if not 放好:
            for 机编号 in 优先级:
                试 = [0] * len(上下文.物资类型)
                试[τ] = 1
                if _可行(上下文, 机型表[机编号], tuple(试)):
                    已开.append((机编号, 试))
                    箱位.append([箱])
                    放好 = True
                    break
        if not 放好:
            raise RuntimeError(f"{上下文.服务区编号}：货箱 {箱['货箱编号']} 无任何机型可单独承运")

    方案 = 组批方案(服务区编号=上下文.服务区编号)
    for (机编号, 计数), 箱列表 in zip(已开, 箱位):
        质量, 体积, 能耗, 时间 = 单架次代价(上下文, 机型表[机编号], tuple(计数))
        方案.架次列表.append(
            架次(
                机型编号=机编号,
                箱计数=tuple(计数),
                箱编号=tuple(b["货箱编号"] for b in 箱列表),
                质量=质量,
                体积=体积,
                能耗=能耗,
                作业时间=时间,
            )
        )
    return 方案


# ===================== 算法二：精确 Pareto 前沿（用于精确前沿）=====================
@dataclass(frozen=True)
class 前沿项:
    """DP 前沿中的一个带前驱的目标点，便于精确回溯。"""

    架次数: int
    能耗: float
    最大架次时间: float
    机型编号: str | None = None
    箱计数: tuple[int, ...] | None = None
    前驱状态: tuple[int, ...] | None = None
    前驱序号: int | None = None

    @property
    def 目标(self) -> tuple:
        return (self.架次数, self.能耗, self.最大架次时间)


@dataclass
class 前沿结果:
    """DP 的完整产出：初始状态的前沿 + 所有状态的前沿表（用于回溯）。"""

    初始状态: tuple[int, ...]
    表: dict[tuple[int, ...], tuple[前沿项, ...]]

    @property
    def 前沿(self) -> tuple[前沿项, ...]:
        return self.表[self.初始状态]

    def 转方案(self, 上下文: 服务区上下文, 货箱列表: list[dict], 机型表: dict[str, 机型], 序号: int) -> 组批方案:
        """沿前驱链把第 `序号` 个前沿项还原为具体组批方案。"""
        项 = self.前沿[序号]
        计数序列: list[tuple[int, ...]] = []
        机型序列: list[str] = []
        while 项.机型编号 is not None:
            计数序列.append(项.箱计数)
            机型序列.append(项.机型编号)
            if 项.前驱状态 is None or 项.前驱序号 is None:
                raise RuntimeError("前沿项前驱信息缺失，无法回溯")
            项 = self.表[项.前驱状态][项.前驱序号]
        编号序列 = 分配箱编号(上下文, 货箱列表, 计数序列)

        方案 = 组批方案(服务区编号=上下文.服务区编号)
        for 机编号, 计数, 编号 in zip(机型序列, 计数序列, 编号序列):
            质量, 体积, 能耗, 时间 = 单架次代价(上下文, 机型表[机编号], 计数)
            方案.架次列表.append(
                架次(
                    机型编号=机编号,
                    箱计数=计数,
                    箱编号=编号,
                    质量=质量,
                    体积=体积,
                    能耗=能耗,
                    作业时间=时间,
                )
            )
        return 方案


def _支配(甲: 前沿项, 乙: 前沿项) -> bool:
    """甲是否支配乙（三目标全部不劣且至少一项严格更优）。"""
    return (
        甲.架次数 <= 乙.架次数
        and 甲.能耗 <= 乙.能耗 + 数值容差
        and 甲.最大架次时间 <= 乙.最大架次时间 + 数值容差
        and (
            甲.架次数 < 乙.架次数
            or 甲.能耗 < 乙.能耗 - 数值容差
            or 甲.最大架次时间 < 乙.最大架次时间 - 数值容差
        )
    )


def _前沿去支配(候选: list[前沿项]) -> tuple[前沿项, ...]:
    唯一: dict[tuple, 前沿项] = {}
    for 项 in 候选:
        唯一.setdefault(项.目标, 项)
    排序 = sorted(唯一.values(), key=lambda x: x.目标)
    前沿: list[前沿项] = []
    for 项 in 排序:
        if any(_支配(既有, 项) for 既有 in 前沿):
            continue
        前沿 = [既有 for 既有 in 前沿 if not _支配(项, 既有)]
        前沿.append(项)
    return tuple(前沿)


def _枚举子计数(
    剩余: tuple[int, ...],
    上下文: 服务区上下文,
    机: 机型,
    载荷上限: float,
) -> list[tuple[int, ...]]:
    """枚举从 `剩余` 中取出的、能被 `机` 单独承运的非空子计数组合。"""
    结果 = []
    for 计数 in product(*[range(k + 1) for k in 剩余]):
        if sum(计数) == 0:
            continue
        质量 = sum(k * m for k, m in zip(计数, 上下文.箱型质量))
        if 质量 > 载荷上限 + 数值容差:
            continue
        体积 = sum(k * v for k, v in zip(计数, 上下文.箱型体积))
        if 体积 > 机.可用装载体积 + 数值容差:
            continue
        结果.append(计数)
    return 结果


def 精确组批前沿(
    上下文: 服务区上下文,
    货箱列表: list[dict],
    机型表: dict[str, 机型],
) -> 前沿结果:
    """精确求解该服务区的组批 Pareto 前沿。

    目标三维：架次数 / 总能耗(kWh) / 区内最大架次作业时间(s)。
    状态为各箱型的剩余计数向量；由于同型箱可互换，此 DP 是精确的（非启发式）。
    """
    初始 = 初始箱计数(上下文, 货箱列表)
    机型列表 = [机型表[g] for g in 上下文.可用机型(机型表)]

    @lru_cache(maxsize=None)
    def 架次缓存(机编号: str, 计数: tuple[int, ...]) -> tuple[float, float, float, float]:
        return 单架次代价(上下文, 机型表[机编号], 计数)

    @lru_cache(maxsize=None)
    def 求解(剩余: tuple[int, ...]) -> tuple[前沿项, ...]:
        if all(k == 0 for k in 剩余):
            return (前沿项(0, 0.0, 0.0),)

        候选: list[前沿项] = []
        for 机 in 机型列表:
            上限 = 上下文.最大载荷.get(机.编号, 0.0)
            for 计数 in _枚举子计数(剩余, 上下文, 机, 上限):
                _, _, 能耗, 时间 = 架次缓存(机.编号, 计数)
                新剩余 = tuple(a - b for a, b in zip(剩余, 计数))
                for 序号, 子项 in enumerate(求解(新剩余)):
                    候选.append(
                        前沿项(
                            架次数=1 + 子项.架次数,
                            能耗=能耗 + 子项.能耗,
                            最大架次时间=max(时间, 子项.最大架次时间),
                            机型编号=机.编号,
                            箱计数=计数,
                            前驱状态=新剩余,
                            前驱序号=序号,
                        )
                    )
        return _前沿去支配(候选)

    表: dict[tuple[int, ...], tuple[前沿项, ...]] = {}
    for 状态 in product(*[range(k + 1) for k in 初始]):
        表[状态] = 求解(状态)
    if not 表[初始]:
        raise RuntimeError(f"{上下文.服务区编号}：无可行组批方案")
    return 前沿结果(初始状态=初始, 表=表)

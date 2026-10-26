"""服务区原子 —— 分区的不可分割单元。

职责
----
问题第 3 条约束「**若同一运输架次同时涉及多个服务区，则这些服务区应划入同一任务组**」
直接决定了哪些服务区**必须绑在一起**。把每个运输架次的服务区集合视为一条"捆绑"边，
则：

    **原子 = 服务区「同架次」关系图的连通分量。**

于是分区不是对 15 个服务区的自由划分，而是对**原子**的带权装箱。

可加性前提（下游 `m41` / `m51` 依赖它）
--------------------------------------
`构建原子` 已把同一架次的服务区并成一簇，故**每个运输架次的全部服务区必落在唯一一个
原子内** ⇒「组的负载 = 其成员原子的负载之和」，无需再对全部架次做集合交集过滤。
`跨原子架次数()` 是该前提的可验证形式。

保留但可能不触发的保护分支
------------------------------------------
联合调度与中继 2026-09-25 重算后的方案里，**每个运输架次只访问一个服务区**，故 15 个服务区全部
退化为**单元素原子**，连通分量算法只做自反合并。该分支必须保留，并由
`原子自检` 报告「跨原子架次数 = 0」，以免读者误以为约束起了作用。

依据：分区与资源核算的问题描述。
"""
from __future__ import annotations

from dataclasses import dataclass

from 源代码.公共库.资源分区.上游读取 import 上游基线
from 源代码.公共库.资源分区.配置 import 数值容差


@dataclass(frozen=True)
class 原子:
    """一个不可分割的服务区簇及其全部负载。"""

    服务区: tuple[str, ...]  # 升序
    架次序号: tuple[int, ...]  # 升序
    架次数: int
    箱数: int
    能耗_kWh: float
    占用时间_s: float
    人口: int

    @property
    def 负载(self) -> tuple[int, int, float, float, int]:
        """五元组 (架次数, 箱数, 能耗, 占用时间, 人口) —— 可加性的载体。"""
        return (self.架次数, self.箱数, self.能耗_kWh, self.占用时间_s, self.人口)


def 构建原子(基线: 上游基线, 服务区表: dict[str, dict]) -> tuple[原子, ...]:
    """并查集：同一运输架次涉及的服务区归并为一个**不可分割簇**。"""
    父: dict[str, str] = {}

    def 找(x: str) -> str:
        父.setdefault(x, x)
        while 父[x] != x:
            父[x] = 父[父[x]]
            x = 父[x]
        return x

    def 并(甲: str, 乙: str) -> None:
        父[找(甲)] = 找(乙)

    for 架 in 基线.运输架次:
        区 = 架.服务区集合
        for i in range(1, len(区)):
            并(区[0], 区[i])
    for 架 in 基线.运输架次:  # 确保单区架次也建节点
        for 区 in 架.服务区集合:
            找(区)

    未登记 = sorted(set(父) - set(服务区表))
    if 未登记:
        raise KeyError(f"运输架次涉及的服务区 {未登记} 不在数据文件的服务区表中")

    组分: dict[str, list[str]] = {}
    for 区 in sorted(父):
        组分.setdefault(找(区), []).append(区)

    原子表 = []
    for 根 in sorted(组分):
        区集 = sorted(组分[根])
        区集集合 = set(区集)
        架次 = [架 for 架 in 基线.运输架次 if set(架.服务区集合) & 区集集合]
        原子表.append(
            原子(
                服务区=tuple(区集),
                架次序号=tuple(sorted(架.序号 for 架 in 架次)),
                架次数=len(架次),
                箱数=sum(架.箱数 for 架 in 架次),
                能耗_kWh=sum(架.能耗_kWh for 架 in 架次),
                占用时间_s=sum(架.返回时刻_s - 架.开始时刻_s for 架 in 架次),
                人口=sum(服务区表[区]["人口"] for 区 in 区集),
            )
        )
    return tuple(原子表)


def 原子负载(原子表: tuple[原子, ...]) -> tuple[tuple[int, int, float, float, int], ...]:
    """各原子的负载五元组，顺序与 `原子表` 一致（顺序即语义）。"""
    return tuple(a.负载 for a in 原子表)


def 跨原子架次数(基线: 上游基线, 原子表: tuple[原子, ...]) -> int:
    """服务区横跨两个及以上原子的运输架次数。可加性前提成立时应为 0。"""
    区到原子 = {区: i for i, a in enumerate(原子表) for 区 in a.服务区}
    跨界 = 0
    for 架 in 基线.运输架次:
        号 = {区到原子[区] for 区 in 架.服务区集合}
        if len(号) > 1:
            跨界 += 1
    return 跨界


def 全方案负载(
    基线: 上游基线,
    服务区表: dict[str, dict],
) -> tuple[int, int, float, float, int]:
    """不分区时整套方案的负载五元组（原子负载之和应与它逐位相等）。

    人口按**架次涉及的服务区**求和（即方案实际保障的服务区集合），与原子侧口径一致。
    """
    涉及区 = sorted({区 for 架 in 基线.运输架次 for 区 in 架.服务区集合})
    未知 = [区 for 区 in 涉及区 if 区 not in 服务区表]
    if 未知:
        raise KeyError(f"运输架次涉及的服务区 {未知} 不在数据文件的服务区表中")
    return (
        len(基线.运输架次),
        sum(架.箱数 for 架 in 基线.运输架次),
        sum(架.能耗_kWh for 架 in 基线.运输架次),
        sum(架.返回时刻_s - 架.开始时刻_s for 架 in 基线.运输架次),
        sum(服务区表[区]["人口"] for 区 in 涉及区),
    )


def 原子自检(
    基线: 上游基线,
    原子表: tuple[原子, ...],
    服务区表: dict[str, dict],
) -> list[str]:
    """原子无损性与可加性对拍，返回自检条目。"""
    全部服务区 = set(服务区表)
    覆盖: set[str] = set()
    for a in 原子表:
        if 覆盖 & set(a.服务区):
            raise RuntimeError(f"原子 {a.服务区} 与已有原子重叠，服务区被重复划分")
        覆盖 |= set(a.服务区)
    if 覆盖 != 全部服务区:
        raise RuntimeError(f"原子未覆盖全部服务区：缺 {sorted(全部服务区 - 覆盖)}")

    跨界 = 跨原子架次数(基线, 原子表)
    和 = tuple(sum(a.负载[i] for a in 原子表) for i in range(5))
    逐位差 = tuple(s - 全 for s, 全 in zip(和, 全方案负载(基线, 服务区表)))
    if any(abs(x) > 数值容差 for x in 逐位差):
        raise RuntimeError(f"原子负载之和与全方案负载不一致：逐位差 {逐位差}")

    return [
        f"[自检] 原子无损性：{len(原子表)} 个原子覆盖全部 {len(全部服务区)} 个服务区，"
        f"互不重叠，跨原子架次数 = {跨界}"
        + (
            "（恒为 0 是**构造使然**：原子是「同架次」关系图的连通分量，"
            "同一架次涉及的服务区必落入同一原子。本基线的双服务区原子正是这条关系的产物，"
            "并不表示「每个架次只访问 1 个服务区」）"
            if 跨界 == 0
            else ""
        ),
        f"[自检] 原子可加性：Σ原子负载 − 全方案负载 = {逐位差}"
        f"（架次数/箱数/能耗/时间/人口，容差 {数值容差:g}）",
    ]

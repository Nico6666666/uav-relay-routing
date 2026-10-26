"""分区方案模型 —— 组、组负载、极差与合法性。

职责
----
把「把原子装进 k 个组」这件事做成一个可校验的对象：

* `组`：一个任务组承担的原子、服务区、架次与五项负载指标；
* `分区方案`：k、逐原子的组号（规范形）、各组、三项极差、枚举序号；
* `组负载` / `组负载_逐架次`：**快慢两条独立路径** —— 前者按原子负载求和（依赖
  `服务区原子` 的可加性前提），后者逐个架次做集合交集过滤。自检要求两者逐位相等，
  这样「可加性」就不是假设而是被验证过的事实。

口径
----
* 工作量指标：架次数（主）、能耗、占用时间（次）；另附箱数与保障人口供"需求侧"比较。
* 均衡目标：最小化**极差** `max − min`，按 `配置.均衡键` 的字典序比较。
  极差而非方差/熵，是问题「组间工作量均衡」最直白的度量，且与旧实现口径一致。

依据：分区与资源核算的问题描述。
"""
from __future__ import annotations

from dataclasses import dataclass

from 源代码.公共库.资源分区.上游读取 import 上游基线
from 源代码.公共库.资源分区.服务区原子 import 原子
from 源代码.公共库.资源分区.配置 import 数值容差


@dataclass(frozen=True)
class 组:
    """一个任务组。"""

    组号: int  # 1 起
    原子索引: tuple[int, ...]  # 升序
    服务区: tuple[str, ...]  # 升序
    架次序号: tuple[int, ...]  # 升序
    架次数: int
    箱数: int
    能耗_kWh: float
    占用时间_s: float
    人口: int

    @property
    def 负载(self) -> tuple[int, int, float, float, int]:
        return (self.架次数, self.箱数, self.能耗_kWh, self.占用时间_s, self.人口)


@dataclass(frozen=True)
class 分区方案:
    """一个 k 分区方案。`分配` 为**规范形**（按首现序重编号），故同一划分只出现一次。"""

    k: int
    分配: tuple[int, ...]  # 逐原子的组号（0 起），长度为原子数
    组: tuple[组, ...]
    枚举序号: int = 0  # 流式枚举序；并列名次时的稳定顺序（顺序即语义）

    @property
    def 架次极差(self) -> int:
        return max(g.架次数 for g in self.组) - min(g.架次数 for g in self.组)

    @property
    def 能耗极差(self) -> float:
        return max(g.能耗_kWh for g in self.组) - min(g.能耗_kWh for g in self.组)

    @property
    def 时间极差(self) -> float:
        return max(g.占用时间_s for g in self.组) - min(g.占用时间_s for g in self.组)

    @property
    def 最大架次(self) -> int:
        return max(g.架次数 for g in self.组)

    def 分区(self) -> tuple[frozenset[int], ...]:
        """→ 每组的原子索引集合（与旧实现 `分区` 同义，便于与历史结果比对）。"""
        return tuple(frozenset(i for i, c in enumerate(self.分配) if c == g) for g in range(self.k))


def _组负载_按原子(k: int, 分配: tuple[int, ...], 原子表: tuple[原子, ...]) -> tuple[组, ...]:
    """快路径：按原子负载求和（依赖可加性前提）。"""
    组表 = []
    for 号 in range(k):
        成员 = tuple(i for i, c in enumerate(分配) if c == 号)
        区 = tuple(sorted({区 for i in 成员 for 区 in 原子表[i].服务区}))
        架次 = tuple(sorted(序 for i in 成员 for 序 in 原子表[i].架次序号))
        组表.append(
            组(
                组号=号 + 1,
                原子索引=成员,
                服务区=区,
                架次序号=架次,
                架次数=sum(原子表[i].架次数 for i in 成员),
                箱数=sum(原子表[i].箱数 for i in 成员),
                能耗_kWh=sum(原子表[i].能耗_kWh for i in 成员),
                占用时间_s=sum(原子表[i].占用时间_s for i in 成员),
                人口=sum(原子表[i].人口 for i in 成员),
            )
        )
    return tuple(组表)


def 组负载_逐架次(
    k: int,
    分配: tuple[int, ...],
    原子表: tuple[原子, ...],
    基线: 上游基线,
) -> tuple[组, ...]:
    """慢路径：逐架次做集合交集过滤，与被加性前提覆盖的快路径互验。"""
    组表 = []
    for 号 in range(k):
        区集 = {区 for i, c in enumerate(分配) if c == 号 for 区 in 原子表[i].服务区}
        架次 = [架 for 架 in 基线.运输架次 if set(架.服务区集合) & 区集]
        组表.append(
            组(
                组号=号 + 1,
                原子索引=tuple(sorted(i for i, c in enumerate(分配) if c == 号)),
                服务区=tuple(sorted(区集)),
                架次序号=tuple(sorted(架.序号 for 架 in 架次)),
                架次数=len(架次),
                箱数=sum(架.箱数 for 架 in 架次),
                能耗_kWh=sum(架.能耗_kWh for 架 in 架次),
                占用时间_s=sum(架.返回时刻_s - 架.开始时刻_s for 架 in 架次),
                人口=sum(原子表[i].人口 for i, c in enumerate(分配) if c == 号),
            )
        )
    return tuple(组表)


def 组负载(k: int, 分配: tuple[int, ...], 原子表: tuple[原子, ...]) -> tuple[组, ...]:
    """快路径入口（枚举内部使用）。"""
    return _组负载_按原子(k, 分配, 原子表)


def 建方案(k: int, 分配: tuple[int, ...], 原子表: tuple[原子, ...], 枚举序号: int = 0) -> 分区方案:
    """按规范形分配构造分区方案。"""
    return 分区方案(k=k, 分配=分配, 组=组负载(k, 分配, 原子表), 枚举序号=枚举序号)


def 均衡键(方案: 分区方案) -> tuple:
    """按 `配置.均衡键` 取比较键：优先架次极差最小，其次能耗极差、时间极差。"""
    return (方案.架次极差, 方案.能耗极差, 方案.时间极差)


def 分区自检(
    k: int,
    方案: 分区方案,
    原子表: tuple[原子, ...],
    基线: 上游基线,
) -> list[str]:
    """覆盖 / 互斥 / 非空 / 架次不跨界 / 快慢两路一致。"""
    全部原子 = set(range(len(原子表)))
    覆盖: set[int] = set()
    for g in 方案.组:
        if not g.原子索引:
            raise RuntimeError(f"组 {g.组号} 为空，分区不合法")
        if 覆盖 & set(g.原子索引):
            raise RuntimeError(f"组 {g.组号} 的原子与其它组重复：{sorted(覆盖 & set(g.原子索引))}")
        覆盖 |= set(g.原子索引)
    if 覆盖 != 全部原子:
        raise RuntimeError(f"分区未覆盖全部原子：缺 {sorted(全部原子 - 覆盖)}")
    if len(方案.组) != k:
        raise RuntimeError(f"分区组数 {len(方案.组)} 与 k={k} 不一致")

    架次之和 = sum(g.架次数 for g in 方案.组)
    if 架次之和 != len(基线.运输架次):
        raise RuntimeError(f"各组架次数之和 {架次之和} ≠ 全方案运输架次 {len(基线.运输架次)}")

    慢 = 组负载_逐架次(k, 方案.分配, 原子表, 基线)
    for 快组, 慢组 in zip(方案.组, 慢):
        for i, 名 in enumerate(("架次数", "箱数", "能耗", "占用时间", "人口")):
            if abs(快组.负载[i] - 慢组.负载[i]) > 数值容差:
                raise RuntimeError(
                    f"组 {快组.组号} 的{名}快慢两路不一致：可加路径 {快组.负载[i]!r} vs "
                    f"逐架次路径 {慢组.负载[i]!r}"
                )
    return [
        f"[自检] k={k} 分区合法性：{k} 组非空、原子不重不漏、各组架次之和 = 全方案 {架次之和} 架次",
        f"[自检] k={k} 组负载快慢两路一致：可加路径（Σ原子）== 逐架次交集过滤，"
        f"逐组五指标偏差 ≤ {数值容差:g}",
    ]

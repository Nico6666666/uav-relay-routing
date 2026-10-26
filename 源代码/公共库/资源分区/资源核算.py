"""资源核算 —— 逐组核算需求、汇总成资源账。

职责
----
「各组独立执行、资源不得跨组调配」意味着：一个任务组所需的某类资源数 =
**属于该组的那些占用区间的峰值并发**。本模块按组切分区间表、逐组求峰值并发，
再与库存对照汇总成 `资源账`。

组归属规则（「触及」口径）
--------------------------
* 运输无人机 / 共享电池：区间只服务一个架次，归属该架次所在组（原子保证架次不跨组）；
* 中继无人机（驻留段）、中继能源组件（中继架次）：区间服务**多个**架次，可能横跨多个组。
  此时该区间在**它触及的每一个组**各计一次 —— 因为各组独立执行时，须各自起飞中继去
  覆盖属于本组的片段。这是「资源不得跨组调配」的直接推论，也是中继侧 Δ 的主要来源。

依据：分区与资源核算的问题描述「各任务组仅承担本组服务区对应的运输与通信保障任务，并分别核算
独立执行所需的……数量，任务执行期间各类资源不得跨组调配」。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from 源代码.公共库.资源分区.上游读取 import 上游基线
from 源代码.公共库.资源分区.分区方案 import 分区方案
from 源代码.公共库.资源分区.区间图 import 占用区间, 团证据, 峰值并发, 最少单位分配, 紧约束团
from 源代码.公共库.资源分区.资源占用 import 资源区间表
from 源代码.公共库.资源分区.资源账 import 建资源账, 资源账
from 源代码.公共库.资源分区.配置 import 资源类顺序


@dataclass(frozen=True)
class 组资源需求:
    """一个任务组在各类资源上的需求（峰值并发）与取证材料。"""

    组号: int
    峰值: dict[tuple[str, str], int]
    紧约束: dict[tuple[str, str], 团证据] = field(default_factory=dict)
    单位分配: dict[tuple[str, str], tuple[int, ...]] = field(default_factory=dict)
    触及的中继架次: tuple[int, ...] = ()
    驻留段数: int = 0
    保障记录数: int = 0

    def 取(self, 资源类: str, 子类: str) -> int:
        return self.峰值.get((资源类, 子类), 0)


def 架次到组(方案: 分区方案) -> dict[int, int]:
    """{运输架次序号: 组号(0 起)}。原子的可加性保证每个架次只落一个组。"""
    映射: dict[int, int] = {}
    for g, 组 in enumerate(方案.组):
        for 序号 in 组.架次序号:
            已有 = 映射.setdefault(序号, g)
            if 已有 != g:
                raise RuntimeError(f"架次 {序号} 同时落在组 {已有 + 1} 与组 {g + 1}，原子划分有误")
    return 映射


def 归属组(区间: 占用区间, 架次组: dict[int, int]) -> tuple[int, ...]:
    """该占用区间触及哪些任务组（0 起，升序去重）。"""
    if not 区间.服务架次:
        raise RuntimeError(f"区间 {区间.载体}（{区间.资源类}）没有记录服务架次，无法判定组归属")
    缺失 = [序号 for 序号 in 区间.服务架次 if 序号 not in 架次组]
    if 缺失:
        raise KeyError(f"区间 {区间.载体} 的服务架次 {缺失} 不在任何任务组中")
    return tuple(sorted({架次组[序号] for 序号 in 区间.服务架次}))


def 逐组核算(
    方案: 分区方案,
    区间表: 资源区间表,
    基线: 上游基线,
) -> tuple[组资源需求, ...]:
    """逐组核算全部资源的峰值并发，并留下紧约束团与单位分配两份证据。"""
    架次组 = 架次到组(方案)
    结果 = []
    for g, 组 in enumerate(方案.组):
        峰值: dict[tuple[str, str], int] = {}
        团: dict[tuple[str, str], 团证据] = {}
        分配: dict[tuple[str, str], tuple[int, ...]] = {}
        for 键, 区间 in 区间表.区间.items():
            本组 = [x for x in 区间 if g in 归属组(x, 架次组)]
            if not 本组:
                峰值[键] = 0
                continue
            峰值[键] = 峰值并发(本组)
            团[键] = 紧约束团(本组)
            分配[键] = 最少单位分配(本组)

        中继架次 = sorted(
            {架.序号 for 架 in 基线.中继架次 if set(架.保障运输架次) & set(组.架次序号)}
        )
        结果.append(
            组资源需求(
                组号=g + 1,
                峰值=峰值,
                紧约束=团,
                单位分配=分配,
                触及的中继架次=tuple(中继架次),
                驻留段数=sum(
                    1
                    for x in 区间表.取("中继无人机", "")
                    if g in 归属组(x, 架次组)
                ),
                保障记录数=sum(1 for r in 基线.保障关系 if r.运输架次序号 in set(组.架次序号)),
            )
        )
    return tuple(结果)


def 全局核算(区间表: 资源区间表) -> 组资源需求:
    """「不分区 / 允许跨组共池」口径的核算：全部区间合并后求峰值。"""
    峰值 = {键: 峰值并发(区间) for 键, 区间 in 区间表.区间.items()}
    团 = {键: 紧约束团(区间) for 键, 区间 in 区间表.区间.items() if 区间}
    分配 = {键: 最少单位分配(区间) for 键, 区间 in 区间表.区间.items() if 区间}
    return 组资源需求(组号=0, 峰值=峰值, 紧约束=团, 单位分配=分配)


def 库存数(库存: dict, 资源类: str, 子类: str) -> int:
    """从库存字典取某资源的现有数量；按机型细分的资源必须有该机型，缺则 `KeyError`。"""
    if 资源类 not in 库存:
        raise KeyError(f"库存中缺少资源类「{资源类}」")
    值 = 库存[资源类]
    if isinstance(值, dict):
        if 子类 not in 值:
            raise KeyError(f"库存中缺少 {资源类} 的机型「{子类}」")
        return 值[子类]
    return 值


def 核算汇总(
    组需求表: tuple[组资源需求, ...],
    全局需求: 组资源需求,
    库存: dict,
) -> tuple[资源账, ...]:
    """逐资源把「全局峰值 / 各组峰值 / 库存」收口成资源账。"""
    账表 = []
    for 资源类, 子类 in 资源类顺序:
        键 = (资源类, 子类)
        账表.append(
            建资源账(
                资源类=资源类,
                子类=子类,
                库存=库存数(库存, 资源类, 子类),
                全局峰值=全局需求.峰值.get(键, 0),
                各组峰值=tuple(需求.峰值.get(键, 0) for 需求 in 组需求表),
            )
        )
    return tuple(账表)

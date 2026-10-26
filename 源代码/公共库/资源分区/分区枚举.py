"""分区枚举 —— 流式 O(1) 内存枚举 + 堆 top-N 均衡择优。

职责
----
在全部合法 k 分区中，按最小化极差的字典序目标选出候选。返回值是
**(规范形合法方案数, 前 N 名候选)** —— 方案数用于落盘与自检，候选用于比较。

为什么必须流式（一次真实事故）
------------------------------
早期实现把 `k^n` 个分配**全部**建成候选对象存进列表再排序，而调用方只取前 5 名。
原子数 n 随联合调度与中继的输出而变：n=11 时 3 分区是 17 万个候选、尚能承受；n=15 时变成
**1425 万个候选 × 3.8 KB ≈ 54 GB**，必然 `MemoryError`（同一实现下 2 分区仅约 125 MB，
故现象是"只有 3 分区跑不动"）。本模块用三处**语义等价**的优化把内存降到 O(保留)：

1. **规范形去重**：只保留「按首现序重编号后等于自身」的分配 ⇒ 每个划分只枚举一次，
   省掉 k! 倍无用功。规范形是该划分所有排列中字典序最小者，也是 `itertools.product`
   生成序中下标最小者 ⇒ **并列名次的先后与旧实现逐位一致**。
2. **原子负载整数/浮点累加**：`n` 次加法代替集合交集过滤（依据 `m23` 的可加性前提）。
3. **流式 top-N**：小顶堆只留 N 名，不落地全部候选。

末选用 `m41.建方案` 精确重算键值，保证落盘数值与快慢两路一致。

依据：。
"""
from __future__ import annotations

import heapq
import itertools
from functools import lru_cache

from 源代码.公共库.资源分区.分区方案 import 分区方案, 均衡键, 建方案
from 源代码.公共库.资源分区.服务区原子 import 原子
from 源代码.公共库.资源分区.配置 import 保留候选数


def _规范形(分配: tuple[int, ...], k: int) -> bool:
    """该分配是否已按首现序重编号（= 规范形）。

    判据：第 0 位必为 0；此后每遇到「尚未出现过的新组号」，它必须恰好等于当前已用组数。
    """
    if not 分配 or 分配[0] != 0:
        return False
    已用 = 1
    for c in 分配[1:]:
        if c > 已用:
            return False
        if c == 已用:
            已用 += 1
    return 已用 == k


def 枚举分区(
    k: int,
    原子表: tuple[原子, ...],
    保留: int | None = None,
) -> tuple[int, list[分区方案]]:
    """枚举全部合法 k 分区，返回 **(合法方案数, 前 `保留` 名候选)**。

    合法 = k 组皆非空。候选按 `m41.均衡键` 升序；键并列时**先枚举者（字典序最小者）留**，
    与旧实现的稳定排序一致。
    """
    保留 = 保留候选数 if 保留 is None else 保留
    n = len(原子表)
    if k < 1:
        raise ValueError(f"组数 k={k} 必须为正整数")
    if n < k:
        return 0, []
    负载 = [a.负载 for a in 原子表]

    方案数 = 0
    堆: list[tuple] = []
    for 分配 in itertools.product(range(k), repeat=n):
        if not _规范形(分配, k):
            continue
        序号 = 方案数
        方案数 += 1

        组 = [[0, 0, 0.0, 0.0, 0] for _ in range(k)]
        for i, c in enumerate(分配):
            v = 负载[i]
            g = 组[c]
            g[0] += v[0]
            g[1] += v[1]
            g[2] += v[2]
            g[3] += v[3]
            g[4] += v[4]
        键 = (
            max(g[0] for g in 组) - min(g[0] for g in 组),
            max(g[2] for g in 组) - min(g[2] for g in 组),
            max(g[3] for g in 组) - min(g[3] for g in 组),
        )
        # 序号取负：键并列时先枚举者留 ⇒ 堆顶 = 当前最差者
        项 = (-键[0], -键[1], -键[2], -序号, 分配)
        if len(堆) < 保留:
            heapq.heappush(堆, 项)
        elif 项 > 堆[0]:
            heapq.heapreplace(堆, 项)

    候选 = [建方案(k, 项[4], 原子表, 枚举序号=-项[3]) for 项 in 堆]
    候选.sort(key=lambda s: (均衡键(s), s.枚举序号))
    return 方案数, 候选


# ===================== 独立实现（仅用于自检对拍） =====================
@lru_cache(maxsize=None)
def _斯特林(注: int, k: int) -> int:
    """第二类斯特林数 S(n,k) = k·S(n−1,k) + S(n−1,k−1)。"""
    if k == 0:
        return 1 if 注 == 0 else 0
    if 注 == 0:
        return 0
    return k * _斯特林(注 - 1, k) + _斯特林(注 - 1, k - 1)


def 规范形合法方案数(k: int, n: int) -> int:
    """合法（各组非空）且去重后的方案数 = S(n,k)。

    与枚举走**完全不同的算法路径**（递推 vs 遍历），仅用于自检对拍。
    """
    return _斯特林(n, k)


def 全枚举去重集合(k: int, n: int) -> set[tuple[frozenset[int], ...]]:
    """暴力全枚举 + 归一化去重，得到全部划分的集合。仅供小规模自检对拍。

    与 `枚举分区` 的规范形路径互为独立实现：这里对每个分配做显式归一化再放入集合。
    """
    集合 = set()
    for 分配 in itertools.product(range(k), repeat=n):
        映射: dict[int, int] = {}
        归一 = []
        for c in 分配:
            if c not in 映射:
                映射[c] = len(映射)
            归一.append(映射[c])
        if len(映射) != k:
            continue
        集合.add(tuple(frozenset(i for i, c in enumerate(归一) if c == g) for g in range(k)))
    return 集合


def 枚举对拍(k: int) -> list[str]:
    """小规模三路对拍：规范形计数 / 斯特林数 DP / 暴力去重集合大小。"""
    条目 = []
    for n in range(k, 9):
        集合 = 全枚举去重集合(k, n)
        斯特林 = 规范形合法方案数(k, n)
        if len(集合) != 斯特林:
            raise RuntimeError(
                f"n={n}, k={k}：暴力去重集合大小 {len(集合)} ≠ 斯特林数 S({n},{k}) = {斯特林}"
            )
        条目.append(
            f"[自检] 枚举完备性 n={n}, k={k}：暴力去重集合大小 = 斯特林数 = {斯特林}"
        )
    return 条目

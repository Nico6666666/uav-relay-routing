"""E2：小规模组批子问题上的多目标算法对比。

决策编码：313 个候选架次模板上的随机键（连续向量），解码为“按键降序贪心选择互不重叠的模板”。
目标：(架次数, 总能耗, 最大架次时间)。
对照：NSGA-II、SPEA2、RVEA、MOEA/D。
指标：HV、IGD（以 E1a 的精确前沿为参考），5 个随机种子。

说明：该对比针对**组批子问题**，不是集成调度器；用于说明外层搜索骨架的算法相对表现。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from pymoo.algorithms.moo.moead import MOEAD
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.moo.rvea import RVEA
from pymoo.algorithms.moo.spea2 import SPEA2
from pymoo.core.problem import Problem
from pymoo.indicators.hv import HV
from pymoo.indicators.igd import IGD
from pymoo.optimize import minimize
from pymoo.util.ref_dirs import get_reference_directions

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 实验.实例.构造小实例 import 小实例, 截断货箱  # noqa: E402
from 实验.精确基准.e1_运输组批 import 枚举模板, 精确前沿  # noqa: E402
from 实验.定理验证.公共 import 写CSV  # noqa: E402

结果目录 = 项目根 / "结果" / "精确基准"
结果目录.mkdir(parents=True, exist_ok=True)


class 组批问题(Problem):
    def __init__(self, 模板表, 箱编号, 单箱模板):
        self.模板表 = 模板表
        self.箱编号 = 箱编号
        self.单箱模板 = 单箱模板
        super().__init__(n_var=len(模板表), n_obj=3, xl=0.0, xu=1.0)

    def 解码(self, 键: np.ndarray):
        顺序 = np.argsort(-键)
        覆盖 = set()
        选中 = []
        已选 = set()
        for j in 顺序:
            j = int(j)
            t = self.模板表[j]
            if t.箱集合 & 覆盖:
                continue
            选中.append(t)
            已选.add(j)
            覆盖 |= t.箱集合
            if len(覆盖) == len(self.箱编号):
                break
        for b in self.箱编号:
            if b in 覆盖:
                continue
            j = self.单箱模板.get(b)
            if j is None or j in 已选:
                # 兜底：任取一个覆盖该箱的模板（可能覆盖别的箱）
                for k, t in enumerate(self.模板表):
                    if b in t.箱集合 and k not in 已选:
                        j = k
                        break
            if j is None:
                continue
            t = self.模板表[j]
            选中.append(t)
            已选.add(j)
            覆盖 |= t.箱集合
        return 选中

    def _evaluate(self, X, out, *args, **kwargs):
        F = np.zeros((X.shape[0], 3), dtype=float)
        for i in range(X.shape[0]):
            选中 = self.解码(X[i])
            F[i, 0] = len(选中)
            F[i, 1] = sum(t.能耗 for t in 选中)
            F[i, 2] = max((t.时间 for t in 选中), default=0.0)
        out["F"] = F


def 主函数() -> None:
    实例 = 小实例()
    场景 = 截断货箱(实例.场景, 2)
    箱编号 = tuple(b["货箱编号"] for b in 场景.货箱)
    模板表 = 枚举模板(场景)
    精确 = 精确前沿(箱编号, 模板表)
    精确数组 = np.array(sorted(精确), dtype=float)

    # 单箱模板（用于修复）
    单箱模板 = {}
    for j, t in enumerate(模板表):
        if len(t.箱集合) == 1:
            b = next(iter(t.箱集合))
            单箱模板.setdefault(b, j)

    问题 = 组批问题(模板表, 箱编号, 单箱模板)
    参考方向 = get_reference_directions("das-dennis", 3, n_partitions=12)
    种群 = len(参考方向)

    算法表 = [
        ("NSGA-II", lambda: NSGA2(pop_size=种群)),
        ("SPEA2", lambda: SPEA2(pop_size=种群)),
        ("RVEA", lambda: RVEA(ref_dirs=参考方向)),
        ("MOEA/D", lambda: MOEAD(ref_dirs=参考方向, n_neighbors=15, prob_neighbor_mating=0.7)),
    ]

    尺度 = np.maximum(精确数组.max(axis=0), 1e-9)
    参考 = 精确数组 / 尺度
    参考点 = np.maximum(参考.max(axis=0) * 1.1, 0.1)
    hv = HV(ref_point=参考点)
    igd = IGD(参考)

    行 = []
    for 名, 构造 in 算法表:
        for 种子 in range(1, 21):
            开始 = time.time()
            结果 = minimize(问题, 构造(), ("n_gen", 100), seed=种子, verbose=False)
            耗时 = time.time() - 开始
            F = np.asarray(结果.F, dtype=float)
            F = F[np.isfinite(F).all(axis=1)]
            Fn = F / 尺度
            行.append({
                "算法": 名,
                "种子": 种子,
                "种群": 种群,
                "代数": 100,
                "前沿大小": len(F),
                "HV": f"{hv(Fn):.6f}",
                "IGD": f"{igd(Fn):.6f}",
                "耗时_s": f"{耗时:.3f}",
            })
            print(f"{名} 种子{种子}: front={len(F)} HV={hv(Fn):.6f} IGD={igd(Fn):.6f} 用时={耗时:.2f}s")

    写CSV(
        结果目录 / "e2_算法对比_逐次.csv",
        行,
        ["算法", "种子", "种群", "代数", "前沿大小", "HV", "IGD", "耗时_s"],
    )

    # 汇总
    汇总 = []
    for 名, _ in 算法表:
        子 = [r for r in 行 if r["算法"] == 名]
        hv值 = [float(r["HV"]) for r in 子]
        igd值 = [float(r["IGD"]) for r in 子]
        汇总.append({
            "算法": 名,
            "HV均值": f"{np.mean(hv值):.6f}",
            "HV标准差": f"{np.std(hv值):.6f}",
            "IGD均值": f"{np.mean(igd值):.6f}",
            "IGD标准差": f"{np.std(igd值):.6f}",
            "平均前沿大小": f"{np.mean([r['前沿大小'] for r in 子]):.1f}",
        })
    写CSV(
        结果目录 / "e2_算法对比_汇总.csv",
        汇总,
        ["算法", "HV均值", "HV标准差", "IGD均值", "IGD标准差", "平均前沿大小"],
    )
    print(f"E2 完成：结果写入 {结果目录}")


if __name__ == "__main__":
    主函数()

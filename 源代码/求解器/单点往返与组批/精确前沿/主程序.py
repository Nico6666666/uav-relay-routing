"""
单点往返与组批 / 精确前沿 —— 组批方案的多目标优化

任务要求（单点往返与组批，编号 2）：
    "在完成全部货箱交付的基础上，综合考虑往返架次数、总运输能耗和累计作业时间，
      对组批方案进行优化，并说明各指标之间的权衡关系或优先关系。"

方法：
    1. 每个服务区用 `公共库.组批求解.精确组批前沿` 求该区在
       (架次数, 总能耗, 该区作业时间) 上的**精确** Pareto 前沿（DP，非启发式）。
    2. 因三个指标全局可加（总架次 = Σ、总能耗 = Σ、累计作业时间 = Σ 各区作业时间），
       逐区合并求全局三维 Pareto 前沿。
    3. 按 ε-约束法给出"给定架次数上界下的 (能耗, 时间) 前沿"，并给出三个单目标端点解
       与归一化加权扫描解，据此说明指标间的权衡关系。

运行：
    <解释器> "源代码/求解器/单点往返与组批/精确前沿/主程序.py"
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

项目根 = Path(__file__).resolve().parents[4]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

import numpy as np  # noqa: E402

from 源代码.公共库.基础内核 import 组批求解 as Z  # noqa: E402
from 源代码.公共库.基础内核.场景装配 import 装载场景, 计算最大载荷, 载荷字典  # noqa: E402

本程序目录 = Path(__file__).resolve().parent
输出目录 = 本程序目录 / "输出"
图表目录 = 输出目录 / "图表"

机型顺序 = ["A", "B", "C"]
容差 = 1e-9


# ==================================================================
# 1. 逐区精确前沿
# ==================================================================
def 求各区前沿(场景, 最大载荷结果):
    载荷 = 载荷字典(最大载荷结果)
    上下文表: dict[str, Z.服务区上下文] = {}
    前沿表: dict[str, Z.前沿结果] = {}
    for 项 in 场景.各项:
        上下文 = Z.构造上下文(
            服务区编号=项.编号,
            水平距离=项.水平距离,
            巡航海拔=项.巡航海拔,
            O01地面海拔=场景.调度中心["海拔"],
            服务区地面海拔=项.地面海拔,
            最大载荷={g: 载荷[g][项.编号] for g in 载荷},
            货箱列表=项.货箱,
        )
        上下文表[项.编号] = 上下文
        前沿表[项.编号] = Z.精确组批前沿(上下文, 项.货箱, 场景.机型表)
    return 上下文表, 前沿表


# ==================================================================
# 2. 全局三维前沿合并
# ==================================================================
def _支配(甲, 乙) -> bool:
    return (
        甲[0] <= 乙[0]
        and 甲[1] <= 乙[1] + 容差
        and 甲[2] <= 乙[2] + 容差
        and (甲[0] < 乙[0] or 甲[1] < 乙[1] - 容差 or 甲[2] < 乙[2] - 容差)
    )


def 合并全局前沿(顺序: list[str], 前沿表: dict[str, Z.前沿结果]):
    """逐区合并。元素 = (架次数, 能耗, 累计作业时间, 各区前沿序号元组)。"""
    状态: list[tuple] = [(0, 0.0, 0.0, ())]
    for 区 in 顺序:
        前线 = 前沿表[区].前沿
        候选: list[tuple] = []
        for (n, e, t, sel) in 状态:
            for j, 项 in enumerate(前线):
                候选.append((n + 项.架次数, e + 项.能耗, t + 项.最大架次时间, sel + (j,)))
        状态 = _三维前沿(候选)
    return 状态


def _三维前沿(候选: list[tuple]) -> list[tuple]:
    """三维 Pareto 过滤（按 架次数 → 能耗 → 时间 字典序）。"""
    唯一: dict[tuple, tuple] = {}
    for 项 in 候选:
        键 = (项[0], round(项[1], 6), round(项[2], 4))
        唯一.setdefault(键, 项)
    排序 = sorted(唯一.values(), key=lambda x: (x[0], x[1], x[2]))
    前沿: list[tuple] = []
    for 项 in 排序:
        if any(_支配(既有, 项) for 既有 in 前沿):
            continue
        前沿 = [既有 for 既有 in 前沿 if not _支配(项, 既有)]
        前沿.append(项)
    return 前沿


def 还原方案(场景, 上下文表, 前沿表, 顺序, 项) -> Z.全局方案:
    全局 = Z.全局方案()
    for k, 区 in enumerate(顺序):
        全局.各区方案[区] = 前沿表[区].转方案(上下文表[区], 场景.取项(区).货箱, 场景.机型表, 项[3][k])
    return 全局


# ==================================================================
# 3. 选点：单目标端点 + 加权扫描
# ==================================================================
def 单目标端点(前沿: list[tuple]) -> dict[str, tuple]:
    """三个单目标最优解（并列时按字典序取更优的）。"""
    return {
        "最少架次数": min(前沿, key=lambda x: (x[0], x[1], x[2])),
        "最少总能耗": min(前沿, key=lambda x: (x[1], x[0], x[2])),
        "最短累计作业时间": min(前沿, key=lambda x: (x[2], x[0], x[1])),
    }


def 加权扫描(前沿: list[tuple], 步数: int = 12) -> list[dict]:
    """对归一化后的三目标做加权求和扫描（权重和为 1），返回各权重下的最优解。

    归一化以三个单目标端点值为基准（最优点记 0，最差点记 1）。
    """
    n_lo = min(x[0] for x in 前沿)
    n_hi = max(x[0] for x in 前沿)
    e_lo = min(x[1] for x in 前沿)
    e_hi = max(x[1] for x in 前沿)
    t_lo = min(x[2] for x in 前沿)
    t_hi = max(x[2] for x in 前沿)

    def 归一(x):
        return (
            (x[0] - n_lo) / max(n_hi - n_lo, 容差),
            (x[1] - e_lo) / max(e_hi - e_lo, 容差),
            (x[2] - t_lo) / max(t_hi - t_lo, 容差),
        )

    结果 = []
    for i in range(步数 + 1):
        for j in range(步数 + 1 - i):
            k = 步数 - i - j
            w = (i / 步数, j / 步数, k / 步数)
            最优 = min(前沿, key=lambda x: (sum(a * b for a, b in zip(w, 归一(x))), x[0]))
            结果.append({"权重": w, "解": 最优})
    # 去重（同一点被多组权重选中时只保留第一组）
    唯一: dict[tuple, dict] = {}
    for 项 in 结果:
        唯一.setdefault(项["解"][:3], 项)
    return sorted(唯一.values(), key=lambda d: (d["解"][0], d["解"][1], d["解"][2]))


# ==================================================================
# 输出
# ==================================================================
def 写前沿CSV(前沿: list[tuple], 顺序, 前沿表, 路径: Path) -> None:
    with 路径.open("w", newline="", encoding="utf-8-sig") as f:
        写 = csv.writer(f)
        写.writerow(["序号", "总架次数", "总能耗_kWh", "累计作业时间_s"]
                    + [f"{s}_架次数" for s in 顺序] + [f"{s}_能耗_kWh" for s in 顺序])
        for i, 项 in enumerate(前沿, 1):
            各区架次 = [前沿表[s].前沿[j].架次数 for s, j in zip(顺序, 项[3])]
            各区能耗 = [round(前沿表[s].前沿[j].能耗, 4) for s, j in zip(顺序, 项[3])]
            写.writerow([i, 项[0], round(项[1], 4), round(项[2], 1)] + 各区架次 + 各区能耗)


def 写方案CSV(场景, 全局: Z.全局方案, 路径: Path) -> None:
    with 路径.open("w", newline="", encoding="utf-8-sig") as f:
        写 = csv.writer(f)
        写.writerow(["服务区", "服务区名称", "架次序号", "机型", "箱数", "装载质量_kg",
                     "装载体积_m3", "架次能耗_kWh", "作业时间_s", "货箱清单"])
        for 项 in 场景.各项:
            for 序号, 架 in enumerate(全局.各区方案[项.编号].架次列表, 1):
                写.writerow([
                    项.编号, 项.服务区["名称"], 序号, 架.机型编号, 架.箱数,
                    round(架.质量, 2), round(架.体积, 4),
                    round(架.能耗, 4), round(架.作业时间, 1), " ".join(架.箱编号),
                ])


def 写JSON(场景, 顺序, 前沿, 端点, 加权, 基线, 路径: Path) -> None:
    内容 = {
        "说明": "源代码/求解器/单点往返与组批/精确前沿组批方案多目标优化结果。三维目标：总架次数 / 总运输能耗 / 累计作业时间。",
        "口径": {
            "求解方式": "每区按箱型剩余数做精确 DP 求三维 Pareto 前沿，再逐区合并为全局前沿",
            "累计作业时间": "各服务区作业时间之和；服务区作业时间 = 该区各架次作业时间的最大值（区内并行）",
        },
        "前沿规模": len(前沿),
        "单目标端点解": {
            名: {"总架次数": 项[0], "总能耗_kWh": round(项[1], 4), "累计作业时间_s": round(项[2], 1)}
            for 名, 项 in 端点.items()
        },
        "1_1基线": {
            "总架次数": 基线.总架次数,
            "总能耗_kWh": round(基线.总能耗, 4),
            "累计作业时间_s": round(基线.累计作业时间, 1),
            "是否被支配": any(_支配(x[:3], (基线.总架次数, 基线.总能耗, 基线.累计作业时间)) for x in 前沿),
        },
        "Pareto前沿": [
            {"序号": i, "总架次数": x[0], "总能耗_kWh": round(x[1], 4), "累计作业时间_s": round(x[2], 1)}
            for i, x in enumerate(前沿, 1)
        ],
        "加权扫描选点": [
            {
                "权重": {"架次数": d["权重"][0], "能耗": d["权重"][1], "时间": d["权重"][2]},
                "总架次数": d["解"][0],
                "总能耗_kWh": round(d["解"][1], 4),
                "累计作业时间_s": round(d["解"][2], 1),
            }
            for d in 加权
        ],
    }
    路径.write_text(json.dumps(内容, ensure_ascii=False, indent=2), encoding="utf-8")


def 写方案Markdown(场景, 名: str, 全局: Z.全局方案, 项, 路径: Path) -> None:
    行 = []
    行.append(f"## {名}\n")
    行.append(
        f"总架次数 **{项[0]}**，总运输能耗 **{项[1]:.3f} kWh**，累计作业时间 **{项[2]:.0f} s**。\n"
    )
    行.append("| 服务区 | 架次数 | 机型构成 | 总能耗(kWh) | 作业时间(s) | 逐架次（机型: 货箱） |")
    行.append("| --- | --- | --- | --- | --- | --- |")
    for 项i in 场景.各项:
        方案 = 全局.各区方案[项i.编号]
        构成: dict[str, int] = {}
        for 架 in 方案.架次列表:
            构成[架.机型编号] = 构成.get(架.机型编号, 0) + 1
        明细 = " ／ ".join(f"{架.机型编号}: {' '.join(架.箱编号)}" for 架 in 方案.架次列表)
        行.append(
            f"| {项i.编号} | {方案.架次数} | {' '.join(f'{g}×{构成[g]}' for g in sorted(构成))} | "
            f"{方案.总能耗:.3f} | {方案.作业时间:.0f} | {明细} |"
        )
    行.append("")
    路径.write_text("\n".join(行) + "\n", encoding="utf-8")


def 写Markdown(场景, 顺序, 前沿, 端点, 加权, 基线, 各端点方案, 路径: Path) -> None:
    行 = []
    行.append("# 单点往返与组批 · 精确前沿：组批方案的多目标优化\n")
    行.append("> 由 `源代码/求解器/单点往返与组批/精确前沿/主程序.py` 自动生成。\n")
    行.append(
        "> **三目标**：总架次数 `N`、总运输能耗 `E`(kWh)、累计作业时间 `T`(s)。\n"
        "> **方法**：每区按箱型剩余数做精确动态规划求该区三维 Pareto 前沿，"
        "因三目标全局可加，逐区合并即得全局精确前沿（非启发式、非近似）。\n"
    )

    行.append("\n## 一、Pareto 前沿规模与端点解\n")
    行.append(f"全局 Pareto 前沿共 **{len(前沿)}** 个非支配解。\n")
    行.append("| 解 | 总架次数 | 总能耗(kWh) | 累计作业时间(s) |")
    行.append("| --- | --- | --- | --- |")
    for 名, 项 in 端点.items():
        行.append(f"| **{名}** | {项[0]} | {项[1]:.3f} | {项[2]:.0f} |")
    行.append(
        f"| 可行组批基线（贪婪可行解） | {基线.总架次数} | {基线.总能耗:.3f} | {基线.累计作业时间:.0f} |"
    )
    行.append("")

    行.append("\n## 二、ε-约束：给定架次数上界下的 (能耗, 时间) 前沿\n")
    行.append("| 架次数上界 N | 该 N 下最少能耗(kWh) | 该 N 下最短累计作业时间(s) | 该 N 下非支配解个数 |")
    行.append("| --- | --- | --- | --- |")
    分组: dict[int, list[tuple]] = {}
    for 项 in 前沿:
        分组.setdefault(项[0], []).append(项)
    for N in sorted(分组):
        子 = 分组[N]
        行.append(
            f"| {N} | {min(x[1] for x in 子):.3f} | {min(x[2] for x in 子):.0f} | {len(子)} |"
        )

    行.append("\n## 三、加权扫描选点（归一化后加权求和）\n")
    行.append("| 权重(架次数, 能耗, 时间) | 总架次数 | 总能耗(kWh) | 累计作业时间(s) |")
    行.append("| --- | --- | --- | --- |")
    for d in 加权:
        w = d["权重"]
        行.append(
            f"| ({w[0]:.2f}, {w[1]:.2f}, {w[2]:.2f}) | {d['解'][0]} | {d['解'][1]:.3f} | {d['解'][2]:.0f} |"
        )

    行.append("\n## 四、三个端点解的完整组批方案\n")
    for 名, 方案 in 各端点方案.items():
        行.append(f"### {名}\n")
        行.append(
            f"总架次数 **{方案.总架次数}**，总运输能耗 **{方案.总能耗:.3f} kWh**，"
            f"累计作业时间 **{方案.累计作业时间:.0f} s**。\n"
        )
        行.append("| 服务区 | 架次数 | 机型构成 | 总能耗(kWh) | 作业时间(s) |")
        行.append("| --- | --- | --- | --- | --- |")
        for 项i in 场景.各项:
            区方案 = 方案.各区方案[项i.编号]
            构成: dict[str, int] = {}
            for 架 in 区方案.架次列表:
                构成[架.机型编号] = 构成.get(架.机型编号, 0) + 1
            行.append(
                f"| {项i.编号} | {区方案.架次数} | "
                f"{' '.join(f'{g}×{构成[g]}' for g in sorted(构成))} | "
                f"{区方案.总能耗:.3f} | {区方案.作业时间:.0f} |"
            )
        行.append("")

    行.append("\n## 五、指标间的权衡关系\n")
    行.append(
        "1. **架次数 ↔ 总能耗：同向**。货箱总量固定时，能耗关于单架次载荷是凸函数"
        "（`E^hor ∝ 1/L_g(q)`，而 `L_g(q)` 随载荷递减），因此把载荷**尽量集中**"
        "到少数架次反而更省能；增加架次数会同时抬高水平巡航能耗与爬升附加能耗。\n"
        "2. **架次数 ↔ 累计作业时间：反向**（在超过最少架次数之后）。"
        "架次作业时间含「每箱装载」与「每箱增加交接」两项，箱数越分散则单架次越短；"
        "服务区作业时间取该区架次最大值，因此拆成多架次可以压低该区时间。\n"
        "3. **能耗 ↔ 时间：同向**。省时间靠「多拆架次」，而这正是费能的来源，"
        "两者构成前沿上的主要折中。\n"
        "4. **优先关系**：`总架次数` 是唯一的整数目标且直接决定资源占用，"
        "在前沿上呈明显的阶梯结构，宜作为第一优先级；在给定架次数上界后，"
        "再在 `能耗` 与 `时间` 之间按任务紧急度取舍。\n"
    )

    路径.write_text("\n".join(行) + "\n", encoding="utf-8")


# ==================================================================
# 图表
# ==================================================================
def 绘图(前沿, 端点, 加权, 基线, 顺序, 前沿表) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["svg.fonttype"] = "none"

    产出 = []
    N = np.array([x[0] for x in 前沿])
    E = np.array([x[1] for x in 前沿])
    T = np.array([x[2] for x in 前沿])

    图 = plt.figure(figsize=(9, 7))
    轴 = 图.add_subplot(111, projection="3d")
    轴.scatter(N, E, T, c=T, cmap="viridis", s=18)
    标记 = {"最少架次数": ("*", "red"), "最少总能耗": ("s", "blue"), "最短累计作业时间": ("^", "green")}
    for 名, 项 in 端点.items():
        轴.scatter([项[0]], [项[1]], [项[2]], marker=标记[名][0], c=标记[名][1], s=160, label=名)
    轴.scatter([基线.总架次数], [基线.总能耗], [基线.累计作业时间], marker="x", c="k", s=120, label="可行组批基线")
    轴.set_xlabel("总架次数")
    轴.set_ylabel("总能耗 (kWh)")
    轴.set_zlabel("累计作业时间 (s)")
    轴.set_title("图1 组批方案的三维 Pareto 前沿")
    轴.legend(fontsize=8)
    图.tight_layout()
    for 后缀 in ("png", "svg"):
        p = 图表目录 / f"图1_Pareto前沿三维.{后缀}"
        图.savefig(p, dpi=300)
        产出.append(p)
    plt.close(图)

    图, 轴列 = plt.subplots(1, 2, figsize=(13, 5))
    轴列[0].scatter(N, E, c="#2c7fb8", s=18)
    轴列[0].set_xlabel("总架次数")
    轴列[0].set_ylabel("总能耗 (kWh)")
    轴列[0].set_title("(a) 架次数 vs 总能耗")
    轴列[0].grid(alpha=0.3)
    轴列[1].scatter(N, T, c="#e6550d", s=18)
    轴列[1].set_xlabel("总架次数")
    轴列[1].set_ylabel("累计作业时间 (s)")
    轴列[1].set_title("(b) 架次数 vs 累计作业时间")
    轴列[1].grid(alpha=0.3)
    图.suptitle("图2 Pareto 前沿的二维投影")
    图.tight_layout()
    for 后缀 in ("png", "svg"):
        p = 图表目录 / f"图2_前沿二维投影.{后缀}"
        图.savefig(p, dpi=300)
        产出.append(p)
    plt.close(图)

    图, 轴 = plt.subplots(figsize=(9, 5))
    分组: dict[int, list[tuple]] = {}
    for 项 in 前沿:
        分组.setdefault(项[0], []).append(项)
    上界 = sorted(分组)
    轴.plot(上界, [min(x[1] for x in 分组[k]) for k in 上界], "o-", color="#2c7fb8", label="给定 N 下的最少能耗")
    轴.plot(上界, [min(x[2] for x in 分组[k]) for k in 上界], "s--", color="#e6550d", label="给定 N 下的最短累计作业时间")
    轴.set_xlabel("架次数上界 N（ε-约束）")
    轴.set_ylabel("目标值")
    轴.set_title("图3 ε-约束扫描：给定架次数上界时的最优能耗与最优作业时间")
    轴.grid(alpha=0.3)
    轴.legend()
    图.tight_layout()
    for 后缀 in ("png", "svg"):
        p = 图表目录 / f"图3_ε约束扫描.{后缀}"
        图.savefig(p, dpi=300)
        产出.append(p)
    plt.close(图)

    return 产出


# ==================================================================
# 主流程
# ==================================================================
def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    输出目录.mkdir(parents=True, exist_ok=True)
    图表目录.mkdir(parents=True, exist_ok=True)

    场景 = 装载场景()
    最大载荷结果 = 计算最大载荷(场景)
    顺序 = 场景.编号顺序

    t0 = time.time()
    上下文表, 前沿表 = 求各区前沿(场景, 最大载荷结果)
    print(f"各区精确前沿求解完毕（{time.time() - t0:.1f}s）：" +
          ", ".join(f"{s}={len(前沿表[s].前沿)}" for s in 顺序))

    前沿 = 合并全局前沿(顺序, 前沿表)
    print(f"全局 Pareto 前沿规模：{len(前沿)}")

    端点 = 单目标端点(前沿)
    加权 = 加权扫描(前沿)
    各端点方案 = {名: 还原方案(场景, 上下文表, 前沿表, 顺序, 项) for 名, 项 in 端点.items()}

    # 可行组批基线（同一算法族：贪婪 FFD）
    基线 = Z.全局方案()
    for 项 in 场景.各项:
        基线.各区方案[项.编号] = Z.贪心组批(上下文表[项.编号], 项.货箱, 场景.机型表)

    写前沿CSV(前沿, 顺序, 前沿表, 输出目录 / "Pareto前沿.csv")
    写JSON(场景, 顺序, 前沿, 端点, 加权, 基线, 输出目录 / "优化结果.json")
    写Markdown(场景, 顺序, 前沿, 端点, 加权, 基线, 各端点方案, 输出目录 / "优化方案.md")
    for 名, 方案 in 各端点方案.items():
        写方案CSV(场景, 方案, 输出目录 / f"方案_{名}.csv")
    for p in 绘图(前沿, 端点, 加权, 基线, 顺序, 前沿表):
        print(f"  图已生成：{p.relative_to(项目根)}")

    print("\n端点解：")
    for 名, 项 in 端点.items():
        print(f"  {名:>12}：架次数 {项[0]:2d}，能耗 {项[1]:7.3f} kWh，累计作业时间 {项[2]:6.0f} s")
    print(f"  {'可行组批基线':>12}：架次数 {基线.总架次数:2d}，能耗 {基线.总能耗:7.3f} kWh，"
          f"累计作业时间 {基线.累计作业时间:6.0f} s")
    print(f"\n输出目录：{输出目录}")


if __name__ == "__main__":
    main()

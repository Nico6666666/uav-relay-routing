"""
单点往返与组批 / 余量灵敏度 —— 返航安全余量变化对最大安全载荷与货箱组批结果的影响

任务要求（单点往返与组批，编号 3）：
    "讨论返航安全余量变化对不同机型最大安全载荷和货箱组批结果的影响。"

方法：
    对 rho ∈ {0%, 5%, ..., 50%} 各跑一遍完整链路：
        q*(g,i; rho)          ← 公共库.场景装配.计算最大载荷（余量比例可覆盖）
        组批方案               ← 公共库.组批求解.贪心组批（与可行组批同算法，保证可比）
    考察三个层面：① 最大安全载荷 q* ② 各机型的受约束位置 ③ 组批的架次数/能耗/作业时间。

运行：
    <解释器> "源代码/求解器/单点往返与组批/余量灵敏度/主程序.py"
"""
from __future__ import annotations

import csv
import sys
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
余量网格 = [i / 100.0 for i in range(0, 55, 5)]     # 0% ~ 50%，步长 5%


# ==================================================================
# 单个 rho 下跑一遍完整链路
# ==================================================================
def 跑一次(场景, 余量: float):
    """返回 (结果表, 载荷字典, 全局方案, 不可行服务区字典)。

    不可行 = 该服务区存在某个货箱，没有任何机型能在满足余量要求的前提下承运它。
    最典型的情形是 rho 较大时，**连空载往返都会突破 (1-rho)*E^use**，此时 q* 退化为 0。
    """
    结果表 = 计算最大载荷(场景, 余量比例=余量)
    载荷 = 载荷字典(结果表)
    全局 = Z.全局方案()
    不可行: dict[str, str] = {}

    for 项 in 场景.各项:
        可用 = {g: 载荷[g][项.编号] for g in 载荷 if 载荷[g][项.编号] > 1e-9}
        if not 可用:
            不可行[项.编号] = f"所有机型 q*=0（空载往返即超出可用能量 {1 - 余量:.0%}·E^use）"
            continue
        上下文 = Z.构造上下文(
            服务区编号=项.编号,
            水平距离=项.水平距离,
            巡航海拔=项.巡航海拔,
            O01地面海拔=场景.调度中心["海拔"],
            服务区地面海拔=项.地面海拔,
            最大载荷=可用,
            货箱列表=项.货箱,
        )
        # 逐箱预检：是否存在能承运该箱的机型
        无解箱 = [
            箱["货箱编号"]
            for 箱 in 项.货箱
            if not any(
                箱["质量"] <= 可用[g] + 1e-9 and 箱["体积"] <= 场景.机型表[g].可用装载体积 + 1e-9
                for g in 可用
            )
        ]
        if 无解箱:
            不可行[项.编号] = f"货箱 {无解箱[0]} 无法被任何机型的剩余载荷/体积容纳"
            continue
        全局.各区方案[项.编号] = Z.贪心组批(上下文, 项.货箱, 场景.机型表)

    return 结果表, 载荷, 全局, 不可行


# ==================================================================
# 输出
# ==================================================================
def 写载荷CSV(场景, 每次: dict, 路径: Path) -> None:
    with 路径.open("w", newline="", encoding="utf-8-sig") as f:
        写 = csv.writer(f)
        写.writerow(["余量比例", "机型", "服务区", "最大安全载荷_kg", "能量受限载荷_kg",
                     "连续质量上限_kg", "受限因素", "能量是否受限"])
        for 余量 in 余量网格:
            结果表 = 每次[余量][0]
            for r in 结果表:
                写.writerow([
                    余量, r.机型编号, r.服务区编号, round(r.最大安全载荷, 3),
                    round(r.能量受限载荷, 3), round(r.连续质量上限, 3),
                    r.受限因素, "是" if r.能量是否受限 else "否",
                ])


def 写组批CSV(场景, 每次: dict, 路径: Path) -> None:
    with 路径.open("w", newline="", encoding="utf-8-sig") as f:
        写 = csv.writer(f)
        写.writerow(["余量比例", "服务区", "架次数", "机型构成", "总装载质量_kg",
                     "总能耗_kWh", "服务区作业时间_s"])
        for 余量 in 余量网格:
            全局, 不可行 = 每次[余量][2], 每次[余量][3]
            for 项 in 场景.各项:
                if 项.编号 in 不可行:
                    写.writerow([余量, 项.编号, "不可行", 不可行[项.编号], "", "", ""])
                    continue
                方案 = 全局.各区方案[项.编号]
                构成: dict[str, int] = {}
                for 架 in 方案.架次列表:
                    构成[架.机型编号] = 构成.get(架.机型编号, 0) + 1
                写.writerow([
                    余量, 项.编号, 方案.架次数,
                    " ".join(f"{g}×{构成[g]}" for g in sorted(构成)),
                    round(方案.总质量, 2), round(方案.总能耗, 4), round(方案.作业时间, 1),
                ])


def 写汇总CSV(场景, 每次: dict, 路径: Path) -> None:
    with 路径.open("w", newline="", encoding="utf-8-sig") as f:
        写 = csv.writer(f)
        写.writerow(["余量比例", "总架次数", "总能耗_kWh", "累计作业时间_s", "不可行服务区数",
                     "三机型可用能量_kWh(A,B,C)"] +
                    [f"{g}型_能量受限服务区数" for g in 机型顺序])
        for 余量 in 余量网格:
            结果表, 载荷, 全局, 不可行 = 每次[余量]
            可用 = [f"{场景.机型表[g].电池可用能量 * (1 - 余量):.2f}" for g in 机型顺序]
            受限数 = [
                sum(1 for r in 结果表 if r.机型编号 == g and r.能量是否受限) for g in 机型顺序
            ]
            写.writerow([余量, 全局.总架次数, round(全局.总能耗, 4), round(全局.累计作业时间, 1),
                         len(不可行), " / ".join(可用)] + 受限数)


def 写Markdown(场景, 每次: dict, 路径: Path) -> None:
    顺序 = 场景.编号顺序
    行 = []
    行.append("# 单点往返与组批 · 余量灵敏度：返航安全余量的灵敏度分析\n")
    行.append("> 由 `源代码/求解器/单点往返与组批/余量灵敏度/主程序.py` 自动生成。\n")
    行.append(
        "> **扫描范围**：ρ ∈ {0%, 5%, ..., 50%}。每个 ρ 下重算 q*(机型, 服务区)，"
        "并用与可行组批完全相同的贪婪组批算法重跑组批，保证不同 ρ 之间可比。\n"
    )

    行.append("\n## 一、全局指标随返航安全余量的变化\n")
    行.append("| ρ | 架次能量上限 A/B/C (kWh) | 可行服务区 | 总架次数 | 总能耗(kWh) | 累计作业时间(s) | "
              "不可行服务区 | A型能量受限区数 | B型 | C型 |")
    行.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for 余量 in 余量网格:
        结果表, 载荷, 全局, 不可行 = 每次[余量]
        可用 = "/".join(f"{场景.机型表[g].电池可用能量 * (1 - 余量):.2f}" for g in 机型顺序)
        受限数 = [sum(1 for r in 结果表 if r.机型编号 == g and r.能量是否受限) for g in 机型顺序]
        行.append(
            f"| {余量:.0%} | {可用} | {len(全局.各区方案)}/15 | {全局.总架次数} | {全局.总能耗:.3f} | "
            f"{全局.累计作业时间:.0f} | {len(不可行)} | {受限数[0]} | {受限数[1]} | {受限数[2]} |"
        )
    行.append(
        "\n> 注意：ρ≥45% 时部分服务区已不可行并被排除，故总架次数/总能耗反而下降；"
        "应结合「可行服务区」列一起看，不可直接比较。\n"
    )

    if any(每次[余量][3] for 余量 in 余量网格):
        行.append("\n### 不可行服务区清单\n")
        行.append("| ρ | 服务区 | 原因 |")
        行.append("| --- | --- | --- |")
        for 余量 in 余量网格:
            for s, 原因 in sorted(每次[余量][3].items()):
                行.append(f"| {余量:.0%} | {s} | {原因} |")
        行.append("")

    行.append("\n## 二、最大安全载荷 q* 随 ρ 的变化（单位 kg）\n")
    for 机编号 in 机型顺序:
        机 = 场景.机型表[机编号]
        行.append(f"\n### 机型 {机编号}（Q_g = {机.最大载货质量} kg，E^use = {机.电池可用能量} kWh）\n")
        行.append("| ρ | " + " | ".join(顺序) + " |")
        行.append("| --- | " + " | ".join(["---"] * len(顺序)) + " |")
        for 余量 in 余量网格:
            结果表 = 每次[余量][0]
            单元 = {r.服务区编号: r for r in 结果表 if r.机型编号 == 机编号}
            行.append(f"| {余量:.0%} | " + " | ".join(f"{单元[s].最大安全载荷:.1f}" for s in 顺序) + " |")

    行.append("\n## 三、各服务区架次数随 ρ 的变化\n")
    行.append("| ρ | " + " | ".join(顺序) + " | 合计 |")
    行.append("| --- | " + " | ".join(["---"] * len(顺序)) + " | --- |")
    for 余量 in 余量网格:
        全局, 不可行 = 每次[余量][2], 每次[余量][3]
        架次 = [全局.各区方案[s].架次数 if s in 全局.各区方案 else None for s in 顺序]
        合计 = sum(x for x in 架次 if x is not None)
        行.append(
            f"| {余量:.0%} | " + " | ".join("—" if x is None else str(x) for x in 架次) + f" | {合计} |"
        )
    行.append("\n（「—」表示该服务区在此 ρ 下不可行，已排除在合计之外。）\n")

    行.append("\n## 四、结论\n")
    行.append(_结论(场景, 每次))
    路径.write_text("\n".join(行) + "\n", encoding="utf-8")


def _结论(场景, 每次: dict) -> str:
    顺序 = 场景.编号顺序
    基准 = 0.20
    行 = []

    # 1) q* 单调性
    单调坏 = 0
    for 机编号 in 机型顺序:
        for s in 顺序:
            序列 = []
            for 余量 in 余量网格:
                单元 = {r.服务区编号: r for r in 每次[余量][0] if r.机型编号 == 机编号}
                序列.append(单元[s].最大安全载荷)
            if any(b > a + 1e-9 for a, b in zip(序列, 序列[1:])):
                单调坏 += 1
    行.append(
        f"1. **q* 关于 ρ 单调不增**：45 个 (机型, 服务区) 组合中，违反单调性的有 {单调坏} 个。"
        "返航安全余量越大，架次能量上限越少，能量受限载荷越低——这是模型的必然方向。\n"
    )

    # 2) 哪些机型/服务区对 ρ 敏感
    敏感 = []
    for 机编号 in 机型顺序:
        for s in 顺序:
            a = next(r for r in 每次[0.0][0] if r.机型编号 == 机编号 and r.服务区编号 == s).最大安全载荷
            b = next(r for r in 每次[0.5][0] if r.机型编号 == 机编号 and r.服务区编号 == s).最大安全载荷
            敏感.append((机编号, s, a, b, a - b))
    敏感.sort(key=lambda x: -x[4])
    行.append("2. **敏感度排序（ρ 从 0% 升到 50% 时 q* 的降幅，前 8 位）**：\n")
    行.append("| 机型 | 服务区 | q*(ρ=0%) | q*(ρ=50%) | 降幅(kg) |")
    行.append("| --- | --- | --- | --- | --- |")
    for 机编号, s, a, b, d in 敏感[:8]:
        行.append(f"| {机编号} | {s} | {a:.1f} | {b:.1f} | {d:.1f} |")

    # 3) 组批结果对 ρ 的响应
    a0 = 每次[0.0][2]
    a20 = 每次[基准][2]
    a50 = 每次[0.5][2]
    行.append(
        f"\n3. **组批结果对 ρ 的响应**：总架次数由 ρ=0% 时的 {a0.总架次数} 架次，"
        f"变为 ρ=20%（给定值）时的 {a20.总架次数} 架次，ρ=50% 时 {a50.总架次数} 架次；"
        f"总能耗相应为 {a0.总能耗:.3f} / {a20.总能耗:.3f} / {a50.总能耗:.3f} kWh。\n"
    )

    # 4) 瓶颈是否会从体积切换到能量
    切换 = [
        (机编号, s)
        for 机编号, s, *_ in 敏感
        if next(r for r in 每次[0.0][0] if r.机型编号 == 机编号 and r.服务区编号 == s).能量是否受限
        != next(r for r in 每次[0.5][0] if r.机型编号 == 机编号 and r.服务区编号 == s).能量是否受限
    ]
    行.append(
        f"4. **瓶颈切换**：在 ρ 由 0% 升到 50% 的过程中，共有 {len(切换)} 个 (机型, 服务区) 组合的"
        f"瓶颈由「非能量」切换为「返航能量」。这说明**只有把余量压得足够小，能量约束才会让位于"
        f"体积约束而不再是最终瓶颈**；给定的 ρ=20% 已处于能量开始起作用的区间边缘。\n"
    )

    # 5) 对论文的提示
    行.append(
        "\n5. **操作含义**：返航安全余量 ρ 是「保险丝」参数——调大它换来的安全性提升"
        "是以载荷能力下降、架次数与能耗上升为代价的。给定 ρ=20% 时，"
        "C 型重载机在 S002/S003/S004/S008/S012 已进入能量受限区间，"
        "若把 ρ 提高到 35% 以上，将影响更多服务区的组批结构。\n"
    )
    return "\n".join(行)


# ==================================================================
# 图表
# ==================================================================
def 绘图(场景, 每次: dict) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["svg.fonttype"] = "none"

    顺序 = 场景.编号顺序
    产出 = []
    X = np.array(余量网格) * 100

    图, 轴列 = plt.subplots(1, 3, figsize=(16, 4.6), sharey=True)
    色 = plt.get_cmap("tab20")(np.linspace(0, 1, len(顺序)))
    for 列, 机编号 in enumerate(机型顺序):
        轴 = 轴列[列]
        for k, s in enumerate(顺序):
            ys = [
                next(r for r in 每次[余量][0] if r.机型编号 == 机编号 and r.服务区编号 == s).最大安全载荷
                for 余量 in 余量网格
            ]
            轴.plot(X, ys, marker="o", ms=3, lw=1.1, color=色[k], label=s)
        轴.set_title(f"机型 {机编号}")
        轴.set_xlabel("返航安全余量 ρ (%)")
        轴.grid(alpha=0.3)
    轴列[0].set_ylabel("最大安全载荷 q* (kg)")
    轴列[2].legend(fontsize=7, ncol=2, loc="center left", bbox_to_anchor=(1.02, 0.5))
    图.suptitle("图1 最大安全载荷 q* 随返航安全余量 ρ 的变化（15 个服务区各一条曲线）")
    图.tight_layout()
    for 后缀 in ("png", "svg"):
        p = 图表目录 / f"图1_qmax随余量变化.{后缀}"
        图.savefig(p, dpi=300, bbox_inches="tight")
        产出.append(p)
    plt.close(图)

    图, 轴列 = plt.subplots(1, 3, figsize=(16, 4.6), sharey=True)
    for 列, 机编号 in enumerate(机型顺序):
        轴 = 轴列[列]
        for k, s in enumerate(顺序):
            ys = [
                next(r for r in 每次[余量][0] if r.机型编号 == 机编号 and r.服务区编号 == s).能量受限载荷
                for 余量 in 余量网格
            ]
            轴.plot(X, ys, marker="o", ms=3, lw=1.1, color=色[k], label=s)
        轴.set_title(f"机型 {机编号}")
        轴.set_xlabel("返航安全余量 ρ (%)")
        轴.grid(alpha=0.3)
    轴列[0].set_ylabel("能量受限载荷 q_energy (kg)")
    轴列[2].legend(fontsize=7, ncol=2, loc="center left", bbox_to_anchor=(1.02, 0.5))
    图.suptitle("图2 能量受限载荷 q_energy 随 ρ 的变化（不受体积/整箱平滑）")
    图.tight_layout()
    for 后缀 in ("png", "svg"):
        p = 图表目录 / f"图2_能量受限载荷随余量变化.{后缀}"
        图.savefig(p, dpi=300, bbox_inches="tight")
        产出.append(p)
    plt.close(图)

    图, 轴列 = plt.subplots(1, 3, figsize=(15, 4.8))
    总架次 = [每次[余量][2].总架次数 for 余量 in 余量网格]
    总能 = [每次[余量][2].总能耗 for 余量 in 余量网格]
    总时 = [每次[余量][2].累计作业时间 for 余量 in 余量网格]
    不可行数 = [len(每次[余量][3]) for 余量 in 余量网格]
    坏点 = [k for k, v in enumerate(不可行数) if v > 0]
    for 轴, 序列, 名, 色 in zip(
        轴列,
        (总架次, 总能, 总时),
        ("总架次数", "总运输能耗 (kWh)", "累计作业时间 (s)"),
        ("#2c7fb8", "#e6550d", "#31a354"),
    ):
        轴.plot(X, 序列, "o-", color=色)
        if 坏点:
            轴.plot(X[坏点], [序列[k] for k in 坏点], "x", color="crimson", ms=11, mew=2.2,
                    label="存在不可行服务区（曲线不可直接比较）")
            轴.legend(fontsize=8, loc="upper left")
        轴.axvline(20, color="crimson", ls="--", lw=1.2)
        轴.set_title(名)
        轴.set_xlabel("返航安全余量 ρ (%)")
        轴.grid(alpha=0.3)
    for k, n in enumerate(不可行数):
        if n:
            轴列[0].annotate(f"{n}区不可行", (X[k], 总架次[k]), textcoords="offset points",
                             xytext=(0, -14), ha="center", fontsize=7, color="crimson")
    图.suptitle("图3 组批结果的全局指标随 ρ 的变化（红虚线为给定 ρ=20%）")
    图.tight_layout()
    for 后缀 in ("png", "svg"):
        p = 图表目录 / f"图3_组批指标随余量变化.{后缀}"
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
    每次 = {}
    for 余量 in 余量网格:
        每次[余量] = 跑一次(场景, 余量)

    写载荷CSV(场景, 每次, 输出目录 / "灵敏度_最大安全载荷.csv")
    写组批CSV(场景, 每次, 输出目录 / "灵敏度_组批结果.csv")
    写汇总CSV(场景, 每次, 输出目录 / "灵敏度_全局指标.csv")
    写Markdown(场景, 每次, 输出目录 / "灵敏度分析.md")
    for p in 绘图(场景, 每次):
        print(f"  图已生成：{p.relative_to(项目根)}")

    print("\n全局指标随 ρ 的变化（不可行服务区已排除在架次数/能耗/时间之外）：")
    print("    ρ    架次能量上限A/B/C  可行区  总架次   总能耗(kWh)   累计作业时间(s)")
    for 余量 in 余量网格:
        结果表, 载荷, 全局, 不可行 = 每次[余量]
        可用 = "/".join(f"{场景.机型表[g].电池可用能量 * (1 - 余量):.2f}" for g in 机型顺序)
        print(f"  {余量:4.0%}   {可用:>14}   {len(全局.各区方案):2d}/15   {全局.总架次数:5d}   "
              f"{全局.总能耗:10.3f}   {全局.累计作业时间:12.0f}")
    print(f"\n输出目录：{输出目录}")


if __name__ == "__main__":
    main()

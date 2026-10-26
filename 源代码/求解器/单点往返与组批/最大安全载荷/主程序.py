"""
单点往返与组批 / 最大安全载荷 —— 单点往返最大安全载荷（三种机型 × 15 个服务区）

任务要求（单点往返与组批第一子任务）：
    "计算三种机型在不同服务区执行单点往返任务时的最大安全载荷。"

口径：
    最大安全载荷 = 单架次可投送的最大质量，同时受
        ① 最大载货质量 Q_g
        ② 返航安全能量余量  E_trip(q) <= (1 - rho_g) * E^use_g
        ③ 可用装载体积 V_g（货箱不可拆分 ⇒ 整箱组合）
      三重约束。

运行：
    <解释器> "源代码/求解器/单点往返与组批/最大安全载荷/主程序.py"
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

项目根 = Path(__file__).resolve().parents[4]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

import numpy as np  # noqa: E402

from 源代码.公共库.基础内核.场景装配 import 装载场景  # noqa: E402
from 源代码.公共库.基础内核.载荷求解 import (  # noqa: E402
    单元结果,
    最大整箱组合,
    枚举最大整箱组合,
)
from 源代码.公共库.基础内核.飞行模型 import 单点往返代价  # noqa: E402

本程序目录 = Path(__file__).resolve().parent
输出目录 = 本程序目录 / "输出"
图表目录 = 输出目录 / "图表"

机型顺序 = ["A", "B", "C"]


# ==================================================================
# 自检
# ==================================================================
def 自检(场景, 结果表) -> list[str]:
    记录 = []
    O01海拔 = 场景.调度中心["海拔"]

    负值 = [
        (r.机型编号, r.服务区编号)
        for r in 结果表
        if min(r.去程爬升, r.去程下降, r.回程爬升, r.回程下降) < -1e-9
    ]
    记录.append(f"[自检1] Δh+/Δh- 负值单元数 = {len(负值)}" + (f" {负值}" if 负值 else "（全部非负，clamp 分支未触发）"))

    最大偏差 = 0.0
    for 机编号, 机 in 场景.机型表.items():
        for 项 in 场景.各项:
            代价 = 单点往返代价(机, 项.水平距离, 项.巡航海拔, O01海拔, 项.地面海拔, 0.0)
            水平项 = 机.电池可用能量 * 项.水平距离 / 机.空载标准航程
            期望 = (
                2 * 水平项
                + 机.空载总质量 * 9.8 * 代价.去程爬升 / (机.爬升能耗效率 * 3.6e6)
                + 机.空载总质量 * 9.8 * 代价.回程爬升 / (机.爬升能耗效率 * 3.6e6)
            )
            最大偏差 = max(最大偏差, abs(代价.架次总能耗 - 期望))
    记录.append(f"[自检2] 空载一致性最大偏差 = {最大偏差:.3e} kWh")

    违反 = 0
    for 机 in 场景.机型表.values():
        for 项 in 场景.各项:
            qs = np.linspace(0.0, 机.最大载货质量, 200)
            es = [单点往返代价(机, 项.水平距离, 项.巡航海拔, O01海拔, 项.地面海拔, q).架次总能耗 for q in qs]
            if np.any(np.diff(es) <= 0):
                违反 += 1
    记录.append(f"[自检3] E_trip(q) 单调性被破坏的单元数 = {违反}（应为 0）")

    不一致 = []
    for 项 in 场景.各项:
        if len(项.货箱) > 20:
            continue
        for 机编号, 机 in 场景.机型表.items():
            行 = _取(结果表, 机编号, 项.编号)
            dp质, _ = 最大整箱组合(项.货箱, 行.连续质量上限, 机.可用装载体积)
            枚质, _ = 枚举最大整箱组合(项.货箱, 行.连续质量上限, 机.可用装载体积)
            if abs(dp质 - 枚质) > 1e-9:
                不一致.append((机编号, 项.编号, dp质, 枚质))
    记录.append(f"[自检4] DP 与全枚举不一致单元数 = {len(不一致)}" + (f" {不一致}" if 不一致 else "（逐区一致）"))

    漏网 = []
    for 项 in 场景.各项:
        n = len(项.货箱)
        if n > 20:
            continue
        for 机编号, 机 in 场景.机型表.items():
            行 = _取(结果表, 机编号, 项.编号)
            for 掩码 in range(1 << n):
                质 = 体 = 0.0
                for k in range(n):
                    if 掩码 >> k & 1:
                        质 += 项.货箱[k]["质量"]
                        体 += 项.货箱[k]["体积"]
                if 质 <= 行.最大安全载荷 + 1e-9:
                    continue
                if 质 > 行.连续质量上限 + 1e-9 or 体 > 机.可用装载体积 + 1e-9:
                    continue
                漏网.append((机编号, 项.编号, 质, 体))
    记录.append(f"[自检5] 存在高于 q* 的可行整箱组合的单元数 = {len(漏网)}" + (f" {漏网[:5]}" if 漏网 else "（q* 确为最优）"))

    return 记录


def _取(结果表: list[单元结果], 机编号: str, 服务区编号: str) -> 单元结果:
    for r in 结果表:
        if r.机型编号 == 机编号 and r.服务区编号 == 服务区编号:
            return r
    raise KeyError((机编号, 服务区编号))


# ==================================================================
# 输出
# ==================================================================
CSV列 = [
    ("机型", lambda r: r.机型编号),
    ("服务区", lambda r: r.服务区编号),
    ("水平距离_m", lambda r: round(r.水平距离, 2)),
    ("巡航海拔_m", lambda r: round(r.巡航海拔, 2)),
    ("去程爬升_m", lambda r: round(r.去程爬升, 2)),
    ("去程下降_m", lambda r: round(r.去程下降, 2)),
    ("回程爬升_m", lambda r: round(r.回程爬升, 2)),
    ("回程下降_m", lambda r: round(r.回程下降, 2)),
    ("最大载货质量_kg", lambda r: r.最大载货质量),
    ("可用装载体积_m3", lambda r: r.可用装载体积),
    ("返航安全余量比例", lambda r: r.返航安全余量比例),
    ("能量受限载荷_kg", lambda r: round(r.能量受限载荷, 4)),
    ("连续质量上限_kg", lambda r: round(r.连续质量上限, 4)),
    ("无体积整箱上限_kg", lambda r: round(r.无体积整箱上限, 2)),
    ("最大安全载荷_kg", lambda r: round(r.最大安全载荷, 2)),
    ("装载质量_kg", lambda r: round(r.装载质量, 2)),
    ("装载体积_m3", lambda r: round(r.装载体积, 4)),
    ("装载箱数", lambda r: len(r.装载组合)),
    ("装载组合", lambda r: " ".join(r.装载组合)),
    ("受限因素", lambda r: r.受限因素),
    ("能量是否受限", lambda r: "是" if r.能量是否受限 else "否"),
    ("去程水平能耗_kWh", lambda r: round(r.去程水平能耗, 4)),
    ("去程爬升能耗_kWh", lambda r: round(r.去程爬升能耗, 4)),
    ("回程水平能耗_kWh", lambda r: round(r.回程水平能耗, 4)),
    ("回程爬升能耗_kWh", lambda r: round(r.回程爬升能耗, 4)),
    ("架次总能耗_kWh", lambda r: round(r.架次总能耗, 4)),
    ("能量上限占用率", lambda r: round(r.能量上限占用率, 4)),
    ("去程时间_s", lambda r: round(r.去程时间, 1)),
    ("回程时间_s", lambda r: round(r.回程时间, 1)),
    ("架次飞行时间_s", lambda r: round(r.架次飞行时间, 1)),
]


def 写CSV(结果表, 路径: Path) -> None:
    with 路径.open("w", newline="", encoding="utf-8-sig") as f:
        写 = csv.writer(f)
        写.writerow([名 for 名, _ in CSV列])
        for r in 结果表:
            写.writerow([取(r) for _, 取 in CSV列])


def 写JSON(场景, 结果表, 路径: Path) -> None:
    载荷 = {}
    for r in 结果表:
        载荷.setdefault(r.机型编号, {})[r.服务区编号] = {
            "服务区名称": 场景.取项(r.服务区编号).服务区["名称"],
            "水平距离_m": round(r.水平距离, 3),
            "巡航海拔_m": round(r.巡航海拔, 3),
            "去程爬升_m": round(r.去程爬升, 3),
            "去程下降_m": round(r.去程下降, 3),
            "回程爬升_m": round(r.回程爬升, 3),
            "回程下降_m": round(r.回程下降, 3),
            "最大载货质量_kg": r.最大载货质量,
            "可用装载体积_m3": r.可用装载体积,
            "返航安全余量比例": r.返航安全余量比例,
            "能量受限载荷_kg": round(r.能量受限载荷, 6),
            "连续质量上限_kg": round(r.连续质量上限, 6),
            "无体积整箱上限_kg": round(r.无体积整箱上限, 4),
            "最大安全载荷_kg": round(r.最大安全载荷, 4),
            "装载组合": r.装载组合,
            "装载质量_kg": round(r.装载质量, 4),
            "装载体积_m3": round(r.装载体积, 6),
            "受限因素": r.受限因素,
            "能量是否受限": r.能量是否受限,
            "架次总能耗_kWh": round(r.架次总能耗, 6),
            "能量上限占用率": round(r.能量上限占用率, 6),
            "架次飞行时间_s": round(r.架次飞行时间, 3),
        }
    内容 = {
        "说明": "源代码/求解器/单点往返与组批/最大安全载荷单点往返最大安全载荷结果；单点往返与组批后续子任务（可行组批组批 / 精确前沿优化 / 余量灵敏度灵敏度）"
                "应直接消费本文件或调用 公共库.场景装配，以保证口径一致。",
        "调度中心": 场景.调度中心,
        "机型": {k: vars(v) for k, v in 场景.机型表.items()},
        "场景": {
            项.编号: {
                "服务区名称": 项.服务区["名称"],
                "经度": 项.服务区["经度"],
                "纬度": 项.服务区["纬度"],
                "海拔_m": 项.地面海拔,
                "水平距离_m": round(项.水平距离, 3),
                "沿线最高地面高程_m": round(项.沿线最高地面高程, 3),
                "巡航海拔_m": round(项.巡航海拔, 3),
                "DEM采样地面高程_m": round(项.DEM采样地面高程, 3),
            }
            for 项 in 场景.各项
        },
        "最大安全载荷": 载荷,
    }
    路径.write_text(json.dumps(内容, ensure_ascii=False, indent=2), encoding="utf-8")


def 写Markdown(场景, 结果表, 自检记录, 路径: Path) -> None:
    服务区顺序 = 场景.编号顺序
    行 = []
    行.append("# 单点往返与组批 · 最大安全载荷：单点往返最大安全载荷\n")
    行.append("> 由 `源代码/求解器/单点往返与组批/最大安全载荷/主程序.py` 自动生成。\n")
    行.append(
        "> **最大安全载荷** = 单架次可投送的最大质量，同时满足：最大载货质量 `Q_g`、"
        "返航安全能量余量 `E_trip(q) <= (1-rho)E_use`、可用装载体积 `V_g`（货箱不可拆分）。\n"
    )
    行.append(
        f"> 调度中心 {场景.调度中心['编号']}（{场景.调度中心['名称']}）地面海拔 {场景.调度中心['海拔']} m；"
        f"服务区作业高度 = 地面海拔 + 30 m；巡航海拔 = 航线沿线 DEM 最高地面高程 + 50 m。\n"
    )

    行.append("\n## 一、结果总表（最大安全载荷，kg）\n")
    行.append("| 机型 | " + " | ".join(服务区顺序) + " |")
    行.append("| --- | " + " | ".join(["---"] * len(服务区顺序)) + " |")
    for 机编号 in 机型顺序:
        单元 = {r.服务区编号: r for r in 结果表 if r.机型编号 == 机编号}
        行.append(f"| **{机编号}** | " + " | ".join(f"{单元[s].最大安全载荷:.1f}" for s in 服务区顺序) + " |")

    行.append("\n对照：`min(Q_g, q_energy)` 连续质量上限（kg）\n")
    行.append("| 机型 | " + " | ".join(服务区顺序) + " |")
    行.append("| --- | " + " | ".join(["---"] * len(服务区顺序)) + " |")
    for 机编号 in 机型顺序:
        单元 = {r.服务区编号: r for r in 结果表 if r.机型编号 == 机编号}
        行.append(f"| {机编号} | " + " | ".join(f"{单元[s].连续质量上限:.1f}" for s in 服务区顺序) + " |")

    for 序号, 机编号 in enumerate(机型顺序):
        机 = 场景.机型表[机编号]
        行.append(f"\n## {['二', '三', '四'][序号]}、机型 {机编号}（{机.名称}）明细\n")
        行.append(
            f"Q_g = {机.最大载货质量} kg，V_g = {机.可用装载体积} m³，E^use = {机.电池可用能量} kWh，"
            f"rho = {机.返航电量下限}% ⇒ 架次能量上限 {机.架次能量上限:.4g} kWh。\n"
        )
        行.append(
            "| 服务区 | 距离(m) | 巡航海拔(m) | q_energy(kg) | 连续上限(kg) | V上限整箱(kg) | **q\\*(kg)** "
            "| 受限因素 | 架次能耗(kWh) | 能量上限占用率 | 飞行时间(s) |"
        )
        行.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in (x for x in 结果表 if x.机型编号 == 机编号):
            行.append(
                f"| {r.服务区编号} | {r.水平距离:.0f} | {r.巡航海拔:.1f} | {r.能量受限载荷:.2f} | "
                f"{r.连续质量上限:.2f} | {r.无体积整箱上限:.1f} | **{r.最大安全载荷:.1f}** | "
                f"{r.受限因素} | {r.架次总能耗:.3f} | {r.能量上限占用率:.1%} | {r.架次飞行时间:.0f} |"
            )

    行.append("\n## 五、自检记录\n")
    for 条 in 自检记录:
        行.append(f"- {条}")

    路径.write_text("\n".join(行) + "\n", encoding="utf-8")


# ==================================================================
# 图表
# ==================================================================
def 绘图(场景, 结果表) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["svg.fonttype"] = "none"

    服务区顺序 = 场景.编号顺序
    距离 = [项.水平距离 for 项 in 场景.各项]
    产出 = []

    矩阵 = np.array(
        [
            [next(r.最大安全载荷 for r in 结果表 if r.机型编号 == g and r.服务区编号 == s) for s in 服务区顺序]
            for g in 机型顺序
        ]
    )
    图, 轴 = plt.subplots(figsize=(9.5, 3.2))
    像 = 轴.imshow(矩阵, cmap="YlGnBu", aspect="auto")
    轴.set_xticks(range(len(服务区顺序)), 服务区顺序, rotation=45, ha="right")
    轴.set_yticks(range(len(机型顺序)), [f"机型 {g}" for g in 机型顺序])
    for i in range(矩阵.shape[0]):
        for j in range(矩阵.shape[1]):
            轴.text(j, i, f"{矩阵[i, j]:.0f}", ha="center", va="center", fontsize=8)
    轴.set_title("图1 三种机型 × 15 个服务区的单点往返最大安全载荷（kg）")
    图.colorbar(像, ax=轴, shrink=0.9, label="最大安全载荷 (kg)")
    图.tight_layout()
    for 后缀 in ("png", "svg"):
        p = 图表目录 / f"图1_最大安全载荷热力图.{后缀}"
        图.savefig(p, dpi=300)
        产出.append(p)
    plt.close(图)

    图, 轴 = plt.subplots(figsize=(9, 5))
    颜色 = {"A": "#2c7fb8", "B": "#e6550d", "C": "#31a354"}
    序号 = np.arange(len(服务区顺序))
    for 机编号 in 机型顺序:
        单元 = {r.服务区编号: r for r in 结果表 if r.机型编号 == 机编号}
        轴.plot(序号, [单元[s].最大安全载荷 for s in 服务区顺序], "o-", color=颜色[机编号],
                label=f"机型 {机编号} 最大安全载荷 q*")
        轴.plot(序号, [单元[s].连续质量上限 for s in 服务区顺序], "--", color=颜色[机编号], alpha=0.55,
                label=f"机型 {机编号} 连续质量上限 min(Q_g, q_energy)")
    轴.set_xticks(序号, [f"{s}\n{距离[k]:.0f} m" for k, s in enumerate(服务区顺序)], fontsize=8)
    轴.set_xlabel("服务区（下方为水平距离）")
    轴.set_ylabel("载荷 (kg)")
    轴.set_title("图2 最大安全载荷随服务区距离的变化")
    轴.grid(alpha=0.3)
    轴.legend(fontsize=8, ncol=2)
    图.tight_layout()
    for 后缀 in ("png", "svg"):
        p = 图表目录 / f"图2_载荷随距离变化.{后缀}"
        图.savefig(p, dpi=300)
        产出.append(p)
    plt.close(图)

    图, 轴列 = plt.subplots(3, 1, figsize=(13, 9), sharex=True)
    宽 = 0.62
    for 行号, 机编号 in enumerate(机型顺序):
        轴 = 轴列[行号]
        单元 = [next(r for r in 结果表 if r.机型编号 == 机编号 and r.服务区编号 == s) for s in 服务区顺序]
        去横 = np.array([r.去程水平能耗 for r in 单元])
        去爬 = np.array([r.去程爬升能耗 for r in 单元])
        回横 = np.array([r.回程水平能耗 for r in 单元])
        回爬 = np.array([r.回程爬升能耗 for r in 单元])
        轴.bar(序号, 去横, 宽, label="去程·水平巡航", color="#4a90d9")
        轴.bar(序号, 去爬, 宽, bottom=去横, label="去程·爬升附加", color="#a9cce3")
        轴.bar(序号, 回横, 宽, bottom=去横 + 去爬, label="回程·水平巡航", color="#e59866")
        轴.bar(序号, 回爬, 宽, bottom=去横 + 去爬 + 回横, label="回程·爬升附加", color="#f5cba7")
        轴.axhline(场景.机型表[机编号].架次能量上限, color="crimson", ls="--", lw=1.2,
                   label=f"架次能量上限 {场景.机型表[机编号].架次能量上限:.1f} kWh")
        轴.set_ylabel("能耗 (kWh)")
        轴.set_title(f"机型 {机编号}（载 q* 去程、空载回程）", fontsize=10)
        轴.grid(alpha=0.3, axis="y")
        轴.legend(fontsize=7, ncol=5, loc="upper left")
    轴列[-1].set_xticks(序号, 服务区顺序, rotation=45, ha="right")
    轴列[0].set_title("图3 各服务区单点往返架次能耗分项", fontsize=12)
    图.tight_layout()
    for 后缀 in ("png", "svg"):
        p = 图表目录 / f"图3_架次能耗分项.{后缀}"
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
    print(f"已装载：调度中心 {场景.调度中心['编号']}，{len(场景.各项)} 个服务区，{len(场景.机型表)} 种机型")

    from 源代码.公共库.基础内核.场景装配 import 计算最大载荷

    结果表 = 计算最大载荷(场景)

    自检记录 = 自检(场景, 结果表)
    for 条 in 自检记录:
        print(" ", 条)

    写CSV(结果表, 输出目录 / "最大安全载荷.csv")
    写JSON(场景, 结果表, 输出目录 / "最大安全载荷.json")
    写Markdown(场景, 结果表, 自检记录, 输出目录 / "最大安全载荷.md")
    for p in 绘图(场景, 结果表):
        print(f"  图已生成：{p.relative_to(项目根)}")

    print("\n结果总表（最大安全载荷 kg）")
    服务区顺序 = 场景.编号顺序
    print("       " + "".join(f"{s:>8}" for s in 服务区顺序))
    for 机编号 in 机型顺序:
        单元 = {r.服务区编号: r for r in 结果表 if r.机型编号 == 机编号}
        print(f"  机型{机编号} " + "".join(f"{单元[s].最大安全载荷:>8.1f}" for s in 服务区顺序))
    print(f"\n输出目录：{输出目录}")


if __name__ == "__main__":
    main()

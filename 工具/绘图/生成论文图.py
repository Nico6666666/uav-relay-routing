"""生成论文图件：中文版与英文版。

用法：
    python 工具/绘图/生成论文图.py --语言 中文
    python 工具/绘图/生成论文图.py --语言 English
    python 工具/绘图/生成论文图.py --语言 all

数据源：`结果/标准档_20261025/`。
输出：`结果/论文图/中文/` 与 `结果/论文图/英文/`。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 工具.绘图.术语表 import 取  # noqa: E402
from 源代码.公共库.基础内核.数据读取 import (  # noqa: E402
    读取DEM,
    读取服务区,
    读取调度中心,
)

结果根 = 项目根 / "结果" / "标准档_20261025"
联合调度与中继 = 结果根 / "联合调度与中继"
方案目录 = 联合调度与中继 / "方案检验" / "各方案" / "最及时"
图根 = 项目根 / "结果" / "论文图"

代表方案英文 = {
    "最少运输架次数": "Min transport sorties",
    "最短联合完成时间": "Min joint makespan",
    "最省联合能耗": "Min joint energy",
    "最及时": "Most timely",
    "最少中继架次数": "Min relay sorties",
    "平衡拐点": "Balanced knee",
}


def 设字体(语言: str) -> None:
    if 语言 == "zh":
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
    else:
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["svg.fonttype"] = "none"


def 读CSV(路径: Path) -> list[dict]:
    with 路径.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def 保存(图, 输出目录: Path, 名: str) -> None:
    输出目录.mkdir(parents=True, exist_ok=True)
    图.tight_layout()
    图.savefig(输出目录 / f"{名}.png", dpi=300)
    图.savefig(输出目录 / f"{名}.svg")
    plt.close(图)


def 图场景DEM(语言: str, 输出: Path) -> None:
    地面, 纬度, 经度 = 读取DEM()
    地面 = 地面[::-1, :]
    纬度 = 纬度[::-1]
    中心 = 读取调度中心()
    服务区 = 读取服务区()

    图, 轴 = plt.subplots(figsize=(7.2, 5.2))
    像 = 轴.imshow(
        地面,
        extent=[float(经度[0]), float(经度[-1]), float(纬度[0]), float(纬度[-1])],
        origin="lower",
        cmap="terrain",
        aspect="auto",
    )
    色条 = 图.colorbar(像, ax=轴, shrink=0.85)
    色条.set_label(取("elevation", 语言))

    轴.scatter(
        [中心["经度"]], [中心["纬度"]],
        marker="*", s=180, c="red", edgecolors="black", linewidths=0.5,
        label=取("depot", 语言), zorder=5,
    )
    轴.scatter(
        [s["经度"] for s in 服务区], [s["纬度"] for s in 服务区],
        s=28, c="white", edgecolors="black", linewidths=0.6,
        label=取("service_area", 语言), zorder=4,
    )
    for s in 服务区:
        轴.annotate(s["编号"], (s["经度"], s["纬度"]), xytext=(3, 3),
                    textcoords="offset points", fontsize=7)
    轴.set_xlabel(取("longitude", 语言))
    轴.set_ylabel(取("latitude", 语言))
    轴.set_title(取("fig1_title", 语言))
    轴.legend(loc="lower right", fontsize=8)
    保存(图, 输出, "图01_场景与DEM" if 语言 == "zh" else "Fig01_Scenario_DEM")


def 图框架(语言: str, 输出: Path) -> None:
    图, 轴 = plt.subplots(figsize=(9.2, 3.6))
    轴.set_xlim(0, 10)
    轴.set_ylim(0, 4)
    轴.axis("off")
    框 = [
        (0.2, 2.0, 2.1, 1.0, 取("framework_transport", 语言)),
        (2.8, 2.0, 2.1, 1.0, 取("framework_gap", 语言)),
        (5.4, 2.0, 2.1, 1.0, 取("framework_relay", 语言)),
        (8.0, 2.0, 1.8, 1.0, 取("framework_eval", 语言)),
    ]
    for x, y, w, h, 文本 in 框:
        轴.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05,rounding_size=0.12",
                                    linewidth=1.0, edgecolor="#333333", facecolor="#eef3fb"))
        轴.text(x + w / 2, y + h / 2, 文本, ha="center", va="center", fontsize=10)
    for i in range(len(框) - 1):
        x1 = 框[i][0] + 框[i][2]
        x2 = 框[i + 1][0]
        y = 框[i][1] + 框[i][3] / 2
        轴.annotate("", xy=(x2, y), xytext=(x1, y),
                    arrowprops=dict(arrowstyle="->", lw=1.2, color="#333333"))
    轴.add_patch(FancyBboxPatch((2.8, 0.4), 4.7, 0.8, boxstyle="round,pad=0.05,rounding_size=0.12",
                                linewidth=1.0, edgecolor="#777777", facecolor="#f7f7f7",
                                linestyle="--"))
    轴.text(5.15, 0.8, 取("framework_tables", 语言), ha="center", va="center", fontsize=9)
    轴.set_title(取("fig2_title", 语言))
    保存(图, 输出, "图02_求解框架" if 语言 == "zh" else "Fig02_Framework")


def 图通信缺口(语言: str, 输出: Path) -> None:
    缺口 = 读CSV(方案目录 / "通信缺口清单.csv")
    按架次: dict[int, list[dict]] = {}
    for g in 缺口:
        按架次.setdefault(int(g["运输架次序号"]), []).append(g)
    架次序 = sorted(按架次)
    位置 = {s: i for i, s in enumerate(架次序)}

    图, (轴1, 轴2) = plt.subplots(1, 2, figsize=(11, 4.8), gridspec_kw={"width_ratios": [2.2, 1]})
    for s in 架次序:
        段 = [(float(g["起时刻_s"]), float(g["时长_s"])) for g in 按架次[s]]
        轴1.broken_barh(段, (位置[s] - 0.35, 0.7), facecolors="#4c72b0", edgecolors="none")
    轴1.set_yticks(range(len(架次序)))
    轴1.set_yticklabels([str(s) for s in 架次序], fontsize=7)
    轴1.set_xlabel(取("time_s", 语言))
    轴1.set_ylabel(取("transport_sortie", 语言))
    轴1.set_title(取("gap", 语言))
    轴1.grid(axis="x", alpha=0.3)

    总时长 = [sum(float(g["时长_s"]) for g in 按架次[s]) for s in 架次序]
    轴2.barh(range(len(架次序)), 总时长, color="#dd8452")
    轴2.set_yticks(range(len(架次序)))
    轴2.set_yticklabels([str(s) for s in 架次序], fontsize=7)
    轴2.set_xlabel(取("gap_duration", 语言))
    轴2.set_title(取("gap_duration", 语言))
    轴2.grid(axis="x", alpha=0.3)
    图.suptitle(取("fig3_title", 语言))
    保存(图, 输出, "图06_通信缺口" if 语言 == "zh" else "Fig06_Gaps")


def 图Pareto(语言: str, 输出: Path) -> None:
    行 = 读CSV(联合调度与中继 / "五目标优化" / "Pareto前沿.csv")
    f2 = [float(r["联合任务完成时间_s"]) for r in 行]
    f3 = [float(r["联合总能耗_kWh"]) for r in 行]
    f4 = [float(r["运输架次数"]) for r in 行]
    f5 = [float(r["中继架次数"]) for r in 行]

    数据 = json.loads((联合调度与中继 / "五目标优化" / "代表方案.json").read_text(encoding="utf-8"))
    代表 = 数据.get("代表方案", {})

    图, (轴1, 轴2) = plt.subplots(1, 2, figsize=(11, 4.6))
    轴1.scatter(f2, f3, s=22, c="#4c72b0", alpha=0.75, label="")
    轴2.scatter(f4, f5, s=22, c="#4c72b0", alpha=0.75, label="")
    for 名, 方案 in 代表.items():
        轴1.scatter([float(方案["联合任务完成时间_s"])], [float(方案["联合总能耗_kWh"])],
                    marker="*", s=150, c="#c44e52", edgecolors="black", linewidths=0.4, zorder=5)
        轴2.scatter([float(方案["运输架次数"])], [float(方案["中继架次数"])],
                    marker="*", s=150, c="#c44e52", edgecolors="black", linewidths=0.4, zorder=5)
    轴1.set_xlabel(取("makespan", 语言))
    轴1.set_ylabel(取("energy", 语言))
    轴2.set_xlabel(取("transport_trips", 语言))
    轴2.set_ylabel(取("relay_trips", 语言))
    轴1.grid(alpha=0.3)
    轴2.grid(alpha=0.3)
    图.suptitle(取("fig4_title", 语言))
    保存(图, 输出, "图07_Pareto前沿" if 语言 == "zh" else "Fig07_Pareto")


def 图甘特(语言: str, 输出: Path) -> None:
    行 = 读CSV(方案目录 / "架次安排.csv")
    图, 轴 = plt.subplots(figsize=(9.5, 5.2))
    颜色 = {"运输": "#4c72b0", "中继": "#dd8452"}
    标签 = []
    for i, r in enumerate(行):
        起 = float(r["开始/起飞时刻_s"])
        终 = float(r["返回时刻_s"])
        类 = r["类型"]
        轴.barh(i, 终 - 起, left=起, height=0.7,
                color=颜色.get(类, "#999999"), edgecolor="none")
        标签.append(("T" if 类 == "运输" else "R") + str(r["架次序号"]))
    轴.set_yticks(range(len(行)))
    轴.set_yticklabels(标签, fontsize=7)
    轴.set_xlabel(取("time_s", 语言))
    轴.set_title(取("fig5_title", 语言))
    轴.grid(axis="x", alpha=0.3)
    保存(图, 输出, "图08_调度甘特图" if 语言 == "zh" else "Fig08_Gantt")


def 图中继覆盖(语言: str, 输出: Path) -> None:
    中心 = 读取调度中心()
    服务区 = 读取服务区()
    中继行 = 读CSV(方案目录 / "中继架次与悬停站.csv")
    悬停 = []
    已见 = set()
    for r in 中继行:
        if not r.get("悬停经度"):
            continue
        键 = (r["中继架次序号"], r["悬停经度"], r["悬停纬度"])
        if 键 in 已见:
            continue
        已见.add(键)
        悬停.append({
            "架次": r["中继架次序号"],
            "经度": float(r["悬停经度"]),
            "纬度": float(r["悬停纬度"]),
            "海拔": float(r["悬停海拔_m"]),
            "离地": float(r["悬停离地_m"]),
        })

    图, (轴1, 轴2) = plt.subplots(1, 2, figsize=(11, 4.8), gridspec_kw={"width_ratios": [1.2, 1.5]})
    轴1.scatter([s["经度"] for s in 服务区], [s["纬度"] for s in 服务区],
                s=26, c="white", edgecolors="black", linewidths=0.6)
    轴1.scatter([中心["经度"]], [中心["纬度"]], marker="*", s=160, c="red",
                edgecolors="black", linewidths=0.5)
    for s in 服务区:
        轴1.annotate(s["编号"], (s["经度"], s["纬度"]), xytext=(3, 3),
                     textcoords="offset points", fontsize=6)
    for i, h in enumerate(悬停, start=1):
        轴1.scatter([h["经度"]], [h["纬度"]], marker="^", s=90, c="#dd8452",
                    edgecolors="black", linewidths=0.5)
        轴1.annotate(f"S{i}", (h["经度"], h["纬度"]), xytext=(3, -8),
                     textcoords="offset points", fontsize=7)
    轴1.set_xlabel(取("longitude", 语言))
    轴1.set_ylabel(取("latitude", 语言))
    轴1.set_title(取("hover_station", 语言))
    轴1.grid(alpha=0.25)

    关系 = 读CSV(方案目录 / "通信保障关系.csv")
    事件 = []
    for r in 关系:
        事件.append((float(r["保障起时刻_s"]), 1))
        事件.append((float(r["保障终时刻_s"]), -1))
    事件.sort(key=lambda x: (x[0], x[1]))
    时刻 = [事件[0][0]] if 事件 else [0.0]
    计数 = [0]
    当前 = 0
    for t, d in 事件:
        当前 += d
        时刻.append(t)
        计数.append(当前)
    轴2.step(时刻, 计数, where="post", color="#4c72b0", linewidth=1.2)
    轴2.set_xlabel(取("time_s", 语言))
    轴2.set_ylabel(取("service_load", 语言))
    轴2.set_title(取("relay_coverage", 语言))
    轴2.grid(alpha=0.3)
    图.suptitle(取("fig6_title", 语言))
    保存(图, 输出, "图09_中继覆盖" if 语言 == "zh" else "Fig09_RelayCoverage")




def 图消融(语言: str, 输出: Path) -> None:
    行 = 读CSV(项目根 / "结果" / "多种子" / "汇总.csv")
    组 = {}
    for r in 行:
        if r.get("实验") == "e2e3":
            组.setdefault(r["配置"], []).append(r)
    顺序 = [c for c in ["完整", "无打磨", "单步长", "单种子", "仅贪心", "随机重启"] if c in 组]
    映射 = {
        "完整": "full", "无打磨": "no_polish", "单步长": "single_step",
        "单种子": "single_seed", "仅贪心": "greedy_only", "随机重启": "random",
    }
    名 = [取(映射.get(c, "full"), 语言) for c in 顺序]
    hv = [sum(float(x["HV_mean"]) for x in 组[c]) / len(组[c]) for c in 顺序]
    igd = [sum(float(x["IGD_mean"]) for x in 组[c]) / len(组[c]) for c in 顺序]
    图, (轴1, 轴2) = plt.subplots(1, 2, figsize=(11, 4.2))
    位置 = list(range(len(顺序)))
    轴1.bar(位置, hv, color="#4c72b0")
    轴1.set_xticks(位置)
    轴1.set_xticklabels(名, rotation=20, ha="right", fontsize=8)
    轴1.set_ylabel(取("hv", 语言))
    轴1.set_title(取("hv", 语言))
    轴1.grid(axis="y", alpha=0.3)
    轴2.bar(位置, igd, color="#dd8452")
    轴2.set_xticks(位置)
    轴2.set_xticklabels(名, rotation=20, ha="right", fontsize=8)
    轴2.set_ylabel(取("igd", 语言))
    轴2.set_title(取("igd", 语言))
    轴2.grid(axis="y", alpha=0.3)
    图.suptitle(取("fig7_title", 语言))
    保存(图, 输出, "图03_消融" if 语言 == "zh" else "Fig03_Ablation")


def 图灵敏度(语言: str, 输出: Path) -> None:
    行 = 读CSV(项目根 / "结果" / "多种子" / "汇总.csv")
    def 取组(前缀):
        出 = []
        for r in 行:
            if r.get("实验") != "e4":
                continue
            if r["配置"].startswith(前缀):
                try:
                    x = float(r["配置"].split("=")[1])
                except Exception:
                    continue
                出.append((x, float(r["完成时间_mean"]), float(r["能耗_mean"])))
        return sorted(出)
    rho = 取组("rho=")
    箱 = 取组("每区箱数=")
    机 = 取组("每型无人机=")
    图, (轴1, 轴2, 轴3) = plt.subplots(1, 3, figsize=(13, 4))
    轴1.plot([x for x, _, _ in rho], [e for _, _, e in rho], marker="o", color="#4c72b0")
    轴1.set_xlabel(取("rho", 语言))
    轴1.set_ylabel(取("min_energy", 语言))
    轴1.set_title(取("rho", 语言))
    轴1.grid(alpha=0.3)
    轴2.plot([x for x, _, _ in 箱], [t for _, t, _ in 箱], marker="s", color="#dd8452")
    轴2.set_xlabel(取("boxes_per_area", 语言))
    轴2.set_ylabel(取("min_makespan", 语言))
    轴2.set_title(取("boxes_per_area", 语言))
    轴2.grid(alpha=0.3)
    轴3.plot([x for x, _, _ in 机], [t for _, t, _ in 机], marker="^", color="#55a868")
    轴3.set_xlabel(取("drones_per_type", 语言))
    轴3.set_ylabel(取("min_makespan", 语言))
    轴3.set_title(取("drones_per_type", 语言))
    轴3.grid(alpha=0.3)
    图.suptitle(取("fig8_title", 语言))
    保存(图, 输出, "图04_灵敏度" if 语言 == "zh" else "Fig04_Sensitivity")


def 图可扩展(语言: str, 输出: Path) -> None:
    行 = 读CSV(项目根 / "结果" / "多种子" / "汇总.csv")
    e5 = []
    for r in 行:
        if r.get("实验") != "e5":
            continue
        try:
            x = int(r["配置"].replace("区", ""))
        except Exception:
            continue
        e5.append((x, float(r["完成时间_mean"]), float(r["前沿规模_mean"])))
    e5.sort()
    图, (轴1, 轴2) = plt.subplots(1, 2, figsize=(11, 4.2))
    轴1.plot([x for x, _, _ in e5], [t for _, t, _ in e5], marker="o", color="#4c72b0")
    轴1.set_xlabel(取("service_area_count", 语言))
    轴1.set_ylabel(取("min_makespan", 语言))
    轴1.set_title(取("min_makespan", 语言))
    轴1.grid(alpha=0.3)
    轴2.plot([x for x, _, _ in e5], [f for _, _, f in e5], marker="s", color="#dd8452")
    轴2.set_xlabel(取("service_area_count", 语言))
    轴2.set_ylabel(取("front_size", 语言))
    轴2.set_title(取("front_size", 语言))
    轴2.grid(alpha=0.3)
    图.suptitle(取("fig9_title", 语言))
    保存(图, 输出, "图05_可扩展性" if 语言 == "zh" else "Fig05_Scalability")


def 占位图(标题键: str, 语言: str, 输出: Path, 名: str) -> None:
    图, 轴 = plt.subplots(figsize=(7, 4))
    轴.axis("off")
    轴.text(0.5, 0.58, 取(标题键, 语言), ha="center", va="center", fontsize=14)
    轴.text(0.5, 0.40, 取("pending", 语言), ha="center", va="center", fontsize=12,
            color="#888888")
    保存(图, 输出, 名)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--语言", choices=["中文", "English", "all"], default="all")
    args = parser.parse_args()
    语言表 = ["zh", "en"] if args.语言 == "all" else (["zh"] if args.语言 == "中文" else ["en"])
    for 语言 in 语言表:
        设字体(语言)
        输出 = 图根 / ("中文" if 语言 == "zh" else "英文")
        输出.mkdir(parents=True, exist_ok=True)
        print(f"生成 {语言} 图 → {输出}")
        图场景DEM(语言, 输出)
        图框架(语言, 输出)
        图消融(语言, 输出)
        图灵敏度(语言, 输出)
        图可扩展(语言, 输出)
        图通信缺口(语言, 输出)
        图Pareto(语言, 输出)
        图甘特(语言, 输出)
        图中继覆盖(语言, 输出)
    print("完成。")


if __name__ == "__main__":
    main()

"""多种子实验统计分析。

读取 `结果/多种子/逐次.jsonl`：
- e2e3：按实例构造参考前沿，计算每次运行的 HV/IGD；逐配置/实例 mean±SD；
  关键配对比较的 signed-rank、Holm、bootstrap CI、W/T/L。
- e4/e5：逐配置/实例 mean±SD 的关键指标。
输出：`汇总.csv`、`统计.csv`、`摘要.md`。
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from pymoo.indicators.hv import HV
from pymoo.indicators.igd import IGD
from scipy.stats import wilcoxon

项目根 = Path(__file__).resolve().parents[2]
结果目录 = 项目根 / "结果" / "多种子"
逐次 = 结果目录 / "逐次.jsonl"


def 读取():
    行 = []
    for 行文本 in 逐次.read_text(encoding="utf-8").splitlines():
        if 行文本.strip():
            行.append(json.loads(行文本))
    return 行


def 非支配(点集):
    点列 = sorted({tuple(round(float(x), 9) for x in p) for p in 点集})
    出 = []
    for p in 点列:
        if not any(all(q[i] <= p[i] for i in range(len(p))) and any(q[i] < p[i] for i in range(len(p))) for q in 点列 if q != p):
            出.append(p)
    return np.array(出, dtype=float) if 出 else np.zeros((0, len(点列[0]) if 点列 else 5))


def holm(p值):
    m = len(p值)
    序 = sorted(range(m), key=lambda i: p值[i])
    出 = [1.0] * m
    累计 = 0.0
    for 位, i in enumerate(序):
        调整 = min(1.0, p值[i] * (m - 位))
        累计 = max(累计, 调整)
        出[i] = 累计
    return 出


def 主函数():
    行 = 读取()
    if not 行:
        print("逐次.jsonl 为空")
        return

    # e2e3：按实例参考前沿，计算 HV/IGD
    参考 = {}
    for r in 行:
        if r.get("实验") != "e2e3":
            continue
        for v in r.get("可行目标向量", []):
            参考.setdefault(r["实例"], []).append(v)
    for 实例, 点 in 参考.items():
        参考[实例] = 非支配(点)
    尺度 = {k: np.maximum(v.max(axis=0), 1e-9) if len(v) else np.ones(5) for k, v in 参考.items()}
    参考n = {k: (v / 尺度[k] if len(v) else v) for k, v in 参考.items()}
    参考点 = {k: (np.maximum(v.max(axis=0) * 1.5, 0.5) if len(v) else np.ones(5)) for k, v in 参考n.items()}

    for r in 行:
        if r.get("实验") not in ("e2e3", "fixed"):
            continue
        实例 = r["实例"]
        向量 = np.array(r.get("可行目标向量", []), dtype=float)
        if len(向量) == 0:
            r["HV"] = 0.0
            r["IGD"] = math.inf
            continue
        向量n = 向量 / 尺度[实例]
        r["HV"] = float(HV(ref_point=参考点[实例])(向量n))
        r["IGD"] = float(IGD(参考n[实例])(向量n))

    # 汇总：按 实验/配置/实例
    组 = defaultdict(list)
    for r in 行:
        组[(r["实验"], r["配置"], r["实例"])].append(r)

    汇总 = []
    for (实验, 配置, 实例), 列 in sorted(组.items()):
        hv = [x["HV"] for x in 列 if "HV" in x]
        igd = [x["IGD"] for x in 列 if "IGD" in x]
        汇总.append({
            "实验": 实验,
            "配置": 配置,
            "实例": 实例,
            "运行数": len(列),
            "前沿规模_mean": np.mean([x["前沿规模"] for x in 列]),
            "可行数_mean": np.mean([x["可行数"] for x in 列]),
            "零中断数_mean": np.mean([x["零中断数"] for x in 列]),
            "HV_mean": np.mean(hv) if hv else "",
            "HV_std": np.std(hv) if hv else "",
            "IGD_mean": np.mean(igd) if igd else "",
            "IGD_std": np.std(igd) if igd else "",
            "完成时间_mean": np.nanmean([x["最小完成时间_s"] for x in 列]),
            "能耗_mean": np.nanmean([x["最小能耗_kWh"] for x in 列]),
            "墙钟_mean": np.mean([x["墙钟_s"] for x in 列]),
        })

    import csv
    with (结果目录 / "汇总.csv").open("w", newline="", encoding="utf-8-sig") as f:
        写 = csv.DictWriter(f, fieldnames=list(汇总[0].keys()))
        写.writeheader()
        写.writerows(汇总)

    # e2e3 配对比较：以“无打磨”为基准，按 (实例,种子) 配对 HV
    统计 = []
    基准名 = "无打磨"
    基准 = {(r["实例"], r["种子"]): r for r in 行 if r.get("实验") == "e2e3" and r["配置"] == 基准名}
    for 配置 in ["完整", "单步长", "单种子", "仅贪心", "随机重启"]:
        目标 = {(r["实例"], r["种子"]): r for r in 行 if r.get("实验") == "e2e3" and r["配置"] == 配置}
        共同 = sorted(set(基准) & set(目标))
        if len(共同) < 5:
            continue
        b = np.array([基准[k]["HV"] for k in 共同])
        a = np.array([目标[k]["HV"] for k in 共同])
        差 = a - b
        try:
            p = float(wilcoxon(a, b, alternative="two-sided", method="approx").pvalue)
        except Exception:
            p = float("nan")
        胜 = int(np.sum(差 > 1e-12))
        负 = int(np.sum(差 < -1e-12))
        平 = len(差) - 胜 - 负
        # 按实例的均值做 bootstrap
        实例集 = sorted(set(k[0] for k in 共同))
        实例差 = []
        for 实例 in 实例集:
            位 = [i for i, k in enumerate(共同) if k[0] == 实例]
            实例差.append(float(np.mean(差[位])))
        rng = np.random.default_rng(20261025)
        boots = []
        for _ in range(10000):
            选 = rng.choice(实例差, size=len(实例差), replace=True)
            boots.append(float(np.mean(选)))
        统计.append({
            "实验": "e2e3",
            "目标": 配置,
            "基准": 基准名,
            "配对数": len(共同),
            "HV_gain_mean": float(np.mean(差)),
            "HV_gain_CI95_low": float(np.percentile(boots, 2.5)),
            "HV_gain_CI95_high": float(np.percentile(boots, 97.5)),
            "W/T/L": f"{胜}/{平}/{负}",
            "p_raw": p,
        })
    if 统计:
        调整 = holm([x["p_raw"] for x in 统计])
        for x, p in zip(统计, 调整):
            x["p_Holm"] = p
        with (结果目录 / "统计.csv").open("w", newline="", encoding="utf-8-sig") as f:
            写 = csv.DictWriter(f, fieldnames=list(统计[0].keys()))
            写.writeheader()
            写.writerows(统计)

    # 摘要 Markdown
    行文 = ["# 多种子实验摘要", ""]
    行文.append(f"- 总运行数：{len(行)}")
    行文.append(f"- e2e3 实例数：{len(参考)}")
    行文.append("")
    行文.append("## e2e3 汇总（按实例）")
    行文.append("")
    行文.append("| 配置 | 实例 | 运行数 | HV mean±SD | IGD mean±SD |")
    行文.append("|---|---|---:|---|---|")
    for x in 汇总:
        if x["实验"] != "e2e3":
            continue
        hv = f"{x['HV_mean']:.4f}±{x['HV_std']:.4f}" if x["HV_mean"] != "" else ""
        igd = f"{x['IGD_mean']:.4f}±{x['IGD_std']:.4f}" if x["IGD_mean"] != "" else ""
        行文.append(f"| {x['配置']} | {x['实例']} | {x['运行数']} | {hv} | {igd} |")
    行文.append("")
    行文.append("## 配对比较（HV，目标 vs 无打磨）")
    行文.append("")
    行文.append("| 目标 | 配对数 | HV gain | 95% CI | W/T/L | p_Holm |")
    行文.append("|---|---:|---:|---|---:|---:|")
    for x in 统计:
        行文.append(
            f"| {x['目标']} | {x['配对数']} | {x['HV_gain_mean']:.4f} | "
            f"[{x['HV_gain_CI95_low']:.4f}, {x['HV_gain_CI95_high']:.4f}] | "
            f"{x['W/T/L']} | {x['p_Holm']:.4g} |"
        )
    行文.append("")
    行文.append("## fixed 固定预算汇总")
    行文.append("")
    行文.append("| 配置 | 实例 | 运行数 | 前沿 | HV | 完成时间 | 能耗 | 墙钟 |")
    行文.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for x in 汇总:
        if x["实验"] != "fixed":
            continue
        hv = f"{x['HV_mean']:.4f}" if x["HV_mean"] != "" else ""
        行文.append(
            f"| {x['配置']} | {x['实例']} | {x['运行数']} | {x['前沿规模_mean']:.1f} | "
            f"{hv} | {x['完成时间_mean']:.1f} | {x['能耗_mean']:.4f} | {x['墙钟_mean']:.1f} |"
        )
    行文.append("")
    行文.append("## e4/e5 汇总")
    行文.append("")
    行文.append("| 实验 | 配置 | 实例 | 运行数 | 完成时间 | 能耗 | 可行数 | 零中断 | 墙钟 |")
    行文.append("|---|---|---|---:|---:|---:|---:|---:|---:|")
    for x in 汇总:
        if x["实验"] not in ("e4", "e5"):
            continue
        行文.append(
            f"| {x['实验']} | {x['配置']} | {x['实例']} | {x['运行数']} | "
            f"{x['完成时间_mean']:.1f} | {x['能耗_mean']:.4f} | {x['可行数_mean']:.1f} | "
            f"{x['零中断数_mean']:.1f} | {x['墙钟_mean']:.1f} |"
        )
    (结果目录 / "摘要.md").write_text("\n".join(行文) + "\n", encoding="utf-8")
    print(f"完成：{结果目录}")


if __name__ == "__main__":
    主函数()

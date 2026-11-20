"""Analyze the budget-matched single-step run (A1).

The reference front is rebuilt from the ORIGINAL multi-seed data only (the new
run is evaluated against it, not added to it), so the comparison is like-for-like
with the published E3 numbers.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
from collections import defaultdict
from pathlib import Path

import numpy as np
from pymoo.indicators.hv import HV
from pymoo.indicators.igd import IGD
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parents[3]
ORIG = ROOT / "结果" / "多种子"
NEW = ROOT / "结果" / "多种子_round3" / "逐次_e3_单步长72.jsonl"
OUT = ROOT / "结果" / "多种子_round3" / "A1_report.md"


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


def 读取原始():
    行 = []
    文件 = [ORIG / "逐次.jsonl"]
    for p in sorted(ORIG.glob("逐次_*.jsonl")):
        if "备份" in p.name or "分块" in p.name:
            continue
        文件.append(p)
    for p in 文件:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                行.append(json.loads(line))
    表 = {}
    for r in 行:
        键 = (r.get("实验"), r.get("配置"), r.get("实例"), r.get("种子"))
        表[键] = r
    return list(表.values())


def 建参考(行):
    参考 = {}
    for r in 行:
        if r.get("实验") != "e2e3":
            continue
        for v in r.get("可行目标向量", []):
            参考.setdefault(r["实例"], []).append(v)
    for k, v in 参考.items():
        参考[k] = 非支配(v)
    尺度 = {k: np.maximum(v.max(axis=0), 1e-9) if len(v) else np.ones(5) for k, v in 参考.items()}
    参考n = {k: (v / 尺度[k] if len(v) else v) for k, v in 参考.items()}
    参考点 = {k: (np.maximum(v.max(axis=0) * 1.5, 0.5) if len(v) else np.ones(5)) for k, v in 参考n.items()}
    return 参考, 尺度, 参考n, 参考点


def 加指标(行, 尺度, 参考n, 参考点):
    for r in 行:
        if r.get("实验") != "e2e3":
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


def 配对(行, 基准名, 目标名):
    基准 = {(r["实例"], r["种子"]): r for r in 行 if r.get("实验") == "e2e3" and r["配置"] == 基准名}
    目标 = {(r["实例"], r["种子"]): r for r in 行 if r.get("实验") == "e2e3" and r["配置"] == 目标名}
    共同 = sorted(set(基准) & set(目标))
    if len(共同) < 5:
        return None
    b = np.array([基准[k]["HV"] for k in 共同])
    a = np.array([目标[k]["HV"] for k in 共同])
    差 = a - b
    p = float(wilcoxon(a, b, alternative="two-sided", method="approx").pvalue)
    胜 = int(np.sum(差 > 1e-12))
    负 = int(np.sum(差 < -1e-12))
    平 = len(差) - 胜 - 负
    实例集 = sorted(set(k[0] for k in 共同))
    实例差 = []
    for 实例 in 实例集:
        位 = [i for i, k in enumerate(共同) if k[0] == 实例]
        实例差.append(float(np.mean(差[位])))
    rng = np.random.default_rng(20261025)
    boots = [float(np.mean(rng.choice(实例差, size=len(实例差), replace=True))) for _ in range(10000)]
    return {
        "目标": 目标名, "基准": 基准名, "配对数": len(共同),
        "HV_gain_mean": float(np.mean(差)),
        "CI_low": float(np.percentile(boots, 2.5)),
        "CI_high": float(np.percentile(boots, 97.5)),
        "W/T/L": f"{胜}/{平}/{负}", "p_raw": p,
    }


def 均值(行, 配置, 实例=None):
    xs = [r for r in 行 if r.get("实验") == "e2e3" and r["配置"] == 配置 and "HV" in r]
    if 实例 is not None:
        xs = [r for r in xs if r["实例"] == 实例]
    if not xs:
        return None
    return (float(np.mean([r["HV"] for r in xs])), float(np.std([r["HV"] for r in xs])),
            float(np.mean([r["IGD"] for r in xs])), float(np.std([r["IGD"] for r in xs])), len(xs))


def main():
    原始 = 读取原始()
    参考, 尺度, 参考n, 参考点 = 建参考(原始)
    加指标(原始, 尺度, 参考n, 参考点)

    if not NEW.exists():
        print("A1 output missing", NEW)
        return
    新 = [json.loads(l) for l in NEW.read_text(encoding="utf-8").splitlines() if l.strip()]
    新 = [r for r in 新 if "错误" not in r]
    加指标(新, 尺度, 参考n, 参考点)

    行 = 原始 + 新
    配置列 = ["完整", "单步长72", "单种子", "仅贪心", "随机重启", "无打磨"]
    统计 = [配对(行, "无打磨", c) for c in 配置列]
    统计 = [x for x in 统计 if x]
    p调整 = holm([x["p_raw"] for x in 统计])
    for x, p in zip(统计, p调整):
        x["p_Holm"] = p

    全vs单 = 配对(行, "单步长72", "完整")
    # IGD paired full vs single-step72
    基准 = {(r["实例"], r["种子"]): r for r in 行 if r.get("实验") == "e2e3" and r["配置"] == "单步长72"}
    目标 = {(r["实例"], r["种子"]): r for r in 行 if r.get("实验") == "e2e3" and r["配置"] == "完整"}
    共同 = sorted(set(基准) & set(目标))
    igd_diff = np.array([目标[k]["IGD"] - 基准[k]["IGD"] for k in 共同])
    igd_p = float(wilcoxon([目标[k]["IGD"] for k in 共同], [基准[k]["IGD"] for k in 共同],
                           alternative="two-sided", method="approx").pvalue)

    lines = ["# A1 report: budget-matched single-step (8 x 9 x 1 = 72)\n",
             f"- New runs: {len(新)}\n",
             f"- Reference front: rebuilt from original E3 data only ({len(原始)} rows).\n",
             "\n## Per-instance means (HV / IGD)\n",
             "| Config | Instance | n | HV mean±SD | IGD mean±SD |\n|---|---|---:|---|---|\n"]
    for c in 配置列:
        for inst in ["3区", "4区", "5区", "6区", "7区"]:
            m = 均值(行, c, inst)
            if m:
                lines.append(f"| {c} | {inst} | {m[4]} | {m[0]:.4f}±{m[1]:.4f} | {m[2]:.4f}±{m[3]:.4f} |\n")
    lines.append("\n## Overall means\n")
    lines.append("| Config | n | Mean HV | Mean IGD |\n|---|---:|---:|---:|\n")
    for c in 配置列:
        m = 均值(行, c)
        if m:
            lines.append(f"| {c} | {m[4]} | {m[0]:.4f} | {m[2]:.4f} |\n")
    lines.append("\n## Paired comparisons vs no polishing (HV)\n")
    lines.append("| Config | pairs | HV gain | 95% CI | W/T/L | p raw | p Holm |\n|---|---:|---:|---|---:|---:|---:|\n")
    for x in 统计:
        lines.append(f"| {x['目标']} | {x['配对数']} | {x['HV_gain_mean']:.4f} | "
                     f"[{x['CI_low']:.4f}, {x['CI_high']:.4f}] | {x['W/T/L']} | "
                     f"{x['p_raw']:.4g} | {x['p_Holm']:.4g} |\n")
    lines.append("\n## Full vs single-step72\n")
    if 全vs单:
        lines.append(f"- HV gain (full - single-step72): {全vs单['HV_gain_mean']:.4f}, "
                     f"95% CI [{全vs单['CI_low']:.4f}, {全vs单['CI_high']:.4f}], "
                     f"W/T/L {全vs单['W/T/L']}, p {全vs单['p_raw']:.4g}\n")
    lines.append(f"- IGD difference (full - single-step72): {igd_diff.mean():.4f}, p {igd_p:.4g}\n")
    lines.append("\n## Validation against the published E3 means\n")
    for c in ["完整", "无打磨"]:
        m = 均值(原始, c)
        if m:
            lines.append(f"- Original {c}: HV {m[0]:.6f}, IGD {m[2]:.6f} (published 0.136865/0.112374 for full; 0.087494/0.226848 for no polishing)\n")
    m = 均值(原始, "单步长")
    if m:
        lines.append(f"- Original 单步长 (24 evals): HV {m[0]:.6f}, IGD {m[2]:.6f}\n")

    lines.append("\n## Conclusion check\n")
    if 全vs单:
        changed = (全vs单["HV_gain_mean"] <= 0) or (全vs单["p_raw"] >= 0.05)
        lines.append(f"- Full vs single-step72 HV gain {全vs单['HV_gain_mean']:.4f}, "
                     f"p {全vs单['p_raw']:.4g}; IGD difference {igd_diff.mean():.4f}, p {igd_p:.4g}.\n")
        lines.append(f"- conclusion_changed: {changed}\n")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(lines), encoding="utf-8")
    csvout = ROOT / "结果" / "多种子_round3" / "统计_A1.csv"
    with io.open(csvout, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["目标", "基准", "配对数", "HV_gain_mean", "CI_low", "CI_high", "W/T/L", "p_raw", "p_Holm"])
        w.writeheader()
        for x in 统计:
            if x["目标"] != "无打磨":
                w.writerow({k: x.get(k) for k in w.fieldnames})
    print("written", csvout)
    print("written", OUT)
    print("".join(lines[-12:]))


if __name__ == "__main__":
    main()

"""R1-B: recompute E3 HV/IGD after de-duplicating each run's objective vectors.

The reference front is rebuilt from de-duplicated points; the per-run vectors are
also de-duplicated before HV/IGD.  Writes a before/after comparison so the impact
on the paper can be judged before editing.
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
OUT = ROOT / "结果" / "多种子_round3" / "R1B_report.md"


def 非支配(点集):
    点列 = sorted({tuple(round(float(x), 9) for x in p) for p in 点集})
    出 = []
    for p in 点列:
        if not any(all(q[i] <= p[i] for i in range(len(p))) and any(q[i] < p[i] for i in range(len(p))) for q in 点列 if q != p):
            出.append(p)
    return np.array(出, dtype=float) if 出 else np.zeros((0, len(点列[0]) if 点列 else 5))


def 去重(点集):
    return np.array(sorted({tuple(round(float(x), 9) for x in p) for p in 点集}), dtype=float) if 点集 else np.zeros((0, 5))


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
        原始 = r.get("可行目标向量", [])
        向量 = 去重(原始)
        r["n_original"] = len(原始)
        r["n_unique"] = len(向量)
        if len(向量) == 0:
            r["HV"] = 0.0
            r["IGD"] = math.inf
            continue
        向量n = 向量 / 尺度[实例]
        r["HV"] = float(HV(ref_point=参考点[实例])(向量n))
        r["IGD"] = float(IGD(参考n[实例])(向量n))


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
    新 = [json.loads(l) for l in NEW.read_text(encoding="utf-8").splitlines() if l.strip()]
    新 = [r for r in 新 if "错误" not in r]
    加指标(新, 尺度, 参考n, 参考点)
    行 = 原始 + 新

    lines = ["# R1-B: deduplicated E3 HV/IGD\n",
             "\n## Per-instance means after dedup\n",
             "| Config | Instance | n | n_orig | n_unique | HV | IGD |\n|---|---|---:|---:|---:|---:|---:|\n"]
    for c in ["完整", "单步长72", "单种子", "仅贪心", "随机重启", "无打磨"]:
        for inst in ["3区", "4区", "5区", "6区", "7区"]:
            m = 均值(行, c, inst)
            if m:
                xs = [r for r in 行 if r.get("实验") == "e2e3" and r["配置"] == c and r["实例"] == inst]
                no = np.mean([r.get("n_original", 0) for r in xs])
                nu = np.mean([r.get("n_unique", 0) for r in xs])
                lines.append(f"| {c} | {inst} | {m[4]} | {no:.1f} | {nu:.1f} | {m[0]:.4f} | {m[2]:.4f} |\n")
    lines.append("\n## Overall means after dedup\n")
    lines.append("| Config | n | Mean HV | Mean IGD |\n|---|---:|---:|---:|\n")
    for c in ["完整", "单步长72", "单种子", "仅贪心", "随机重启", "无打磨"]:
        m = 均值(行, c)
        if m:
            lines.append(f"| {c} | {m[4]} | {m[0]:.4f} | {m[2]:.4f} |\n")

    lines.append("\n## Comparison with current paper values\n")
    current = {
        "完整": (0.1369, 0.1124),
        "单步长72": (0.1268, 0.1476),
        "单种子": (0.1415, 0.1026),
        "仅贪心": (0.0735, 0.2629),
        "随机重启": (0.0799, 0.2392),
        "无打磨": (0.0875, 0.2268),
    }
    lines.append("| Config | Current HV | Dedup HV | Current IGD | Dedup IGD |\n|---|---:|---:|---:|---:|\n")
    for c, (hv, igd) in current.items():
        m = 均值(行, c)
        if m:
            lines.append(f"| {c} | {hv:.4f} | {m[0]:.4f} | {igd:.4f} | {m[2]:.4f} |\n")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(lines), encoding="utf-8")
    print("written", OUT)
    print("".join(lines[-20:]))


if __name__ == "__main__":
    main()

"""A1: budget-matched single-step configuration (8 x 9 x 1 = 72 evaluations).

Runs 5 instances (3-7 areas) x 20 seeds with the same evaluator as the full
configuration, but one staggering step and nine generations.  The output is
written to ``结果/多种子_round3/`` so that the original results are untouched.
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 实验.集成.多种子实验 import 跑任务  # noqa: E402

实例 = [
    ("3区", ["S009", "S010", "S011"]),
    ("4区", ["S009", "S010", "S011", "S014"]),
    ("5区", ["S009", "S010", "S011", "S014", "S015"]),
    ("6区", ["S009", "S010", "S011", "S012", "S014", "S015"]),
    ("7区", ["S009", "S010", "S011", "S012", "S013", "S014", "S015"]),
]

输出目录 = 项目根 / "结果" / "多种子_round3"
输出目录.mkdir(parents=True, exist_ok=True)
输出 = 输出目录 / "逐次_e3_单步长72.jsonl"


def main() -> None:
    任务 = []
    for 名, 区 in 实例:
        for 种子 in range(1, 21):
            任务.append({
                "实验": "e2e3", "配置": "单步长72", "实例": 名, "服务区": 区,
                "每区箱数": 3, "每型无人机": 1, "每型电池": 2, "种子": 种子,
                "种群": 8, "代数": 9, "步长": (0,),
                "打磨": True, "任务类型": "solve",
            })
    if 输出.exists():
        输出.unlink()
    进程数 = int(os.environ.get("REPRO_WORKERS", "20"))
    print(f"任务数 {len(任务)}，进程 {进程数}", flush=True)
    with ProcessPoolExecutor(max_workers=进程数, max_tasks_per_child=5) as 池:
        表 = {池.submit(跑任务, t): t for t in 任务}
        for i, 任 in enumerate(as_completed(表), 1):
            try:
                r = 任.result()
            except Exception as e:
                t = 表[任]
                r = {**{k: t.get(k) for k in ("实验", "配置", "实例", "种子")}, "错误": repr(e)}
            print(i, r.get("实例"), r.get("种子"), r.get("可行数"), round(r.get("墙钟_s", 0.0), 1), flush=True)
            with 输出.open("a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("done", 输出, flush=True)


if __name__ == "__main__":
    main()

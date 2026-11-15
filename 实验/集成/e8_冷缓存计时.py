"""E8：单任务串行计时（消除并行争抢对墙钟的影响）。

背景
----
可扩展性实验的可扩展性表若用多个任务同时跑，墙钟受进程争抢、缓存预热与构造开销
影响，可能出现「小区数反而更慢」的非单调现象。本实验对同一批实例**逐任务串行**
运行 5 次，报中位数与四分位距，作为计时口径。

用法
----
    python 实验/集成/e8_冷缓存计时.py
    python 实验/集成/e8_冷缓存计时.py --重复 5

输出
----
`结果/集成实验/e8_串行计时.csv`
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from pathlib import Path

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 实验.集成.多种子实验 import 跑任务  # noqa: E402

结果目录 = 项目根 / "结果" / "集成实验"
结果目录.mkdir(parents=True, exist_ok=True)

基础服务区 = ["S009", "S010", "S011", "S012", "S014", "S015"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--重复", type=int, default=5)
    args = parser.parse_args()

    行 = []
    for 区数 in (2, 3, 4, 5, 6):
        区 = 基础服务区[:区数]
        样本 = []
        for 次 in range(args.重复):
            task = {
                "实验": "e8", "配置": f"{区数}区", "实例": f"{区数}区",
                "服务区": 区, "每区箱数": 3, "每型无人机": 1, "每型电池": 2,
                "种子": 次 + 1, "种群": 8, "代数": 2, "步长": (0,),
                "打磨": False, "任务类型": "solve",
            }
            开始 = time.time()
            r = 跑任务(task)
            钟 = float(r.get("墙钟_s", time.time() - 开始))
            样本.append(钟)
            行.append({
                "区数": 区数, "次": 次 + 1, "墙钟_s": f"{钟:.3f}",
                "前沿规模": r.get("前沿规模"), "可行数": r.get("可行数"),
                "零中断数": r.get("零中断数"),
            })
            print(f"{区数}区 第{次+1}次：{钟:.2f} s "
                  f"（前沿 {r.get('前沿规模')}，可行 {r.get('可行数')}）", flush=True)
        中位 = statistics.median(样本)
        if len(样本) >= 4:
            四分位 = statistics.quantiles(样本, n=4)
            下, 上 = 四分位[0], 四分位[2]
        else:
            下, 上 = min(样本), max(样本)
        print(f"== {区数}区：中位数 {中位:.2f} s，IQR [{下:.2f}, {上:.2f}]")

    路径 = 结果目录 / "e8_串行计时.csv"
    with 路径.open("w", encoding="utf-8", newline="") as f:
        写 = csv.DictWriter(f, fieldnames=list(行[0].keys()))
        写.writeheader()
        写.writerows(行)
    print(f"写入 {路径}")


if __name__ == "__main__":
    main()

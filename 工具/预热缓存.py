"""预热中继站解缓存。

目的：用一次**广度优先、深度很浅**的联合搜索，把「悬停点 × 缺口位姿」的
站位形缓存尽量填满；随后跑正式规模时，冷评估会显著减少。

用法：
    python 工具/预热缓存.py
    python 工具/预热缓存.py --种群 60 --代数 2 --进程数 auto

说明：
- 只跑外层搜索，不做局部打磨、不写结果、不出图。
- 缓存由 `联合调度求解.求解联合` 在结束时自动落盘到
  `源代码/公共库/.中继站解缓存.pkl`。
- 该缓存是纯记忆化：冷算与命中逐位一致，不改变任何口径。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

项目根 = Path(__file__).resolve().parents[1]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 源代码.公共库.通信中继.场景装配 import 装载场景  # noqa: E402
from 源代码.公共库.通信中继.多目标求解 import 搜索参数  # noqa: E402
from 源代码.公共库.通信中继.性能调度 import 建议进程数, 探测硬件, 校准性能  # noqa: E402
from 源代码.公共库.通信中继.联合调度求解 import 求解联合, 默认错峰步长表  # noqa: E402
from 源代码.公共库.通信中继.通信剖面 import 构造剖面  # noqa: E402
from 源代码.公共库.通信中继.通信模型 import 由场景装配  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="预热中继站解缓存")
    parser.add_argument("--种群", type=int, default=60, help="预热种群规模（默认 60）")
    parser.add_argument("--代数", type=int, default=2, help="预热迭代代数（默认 2）")
    parser.add_argument("--进程数", default="auto", help="auto 或整数（默认 auto）")
    args = parser.parse_args()

    print("=" * 78)
    print("预热中继站解缓存：广度优先、深度很浅的一次联合搜索")
    print("=" * 78)

    场景 = 装载场景()
    环境 = 由场景装配(场景)
    剖面表 = 构造剖面(场景, 环境)

    参数 = 搜索参数(种群规模=args.种群, 迭代代数=args.代数)
    硬件 = 探测硬件()
    常量 = 校准性能(硬件)
    进程数, _ = 建议进程数(参数.种群规模, 硬件, 常量)
    if args.进程数 != "auto":
        进程数 = int(args.进程数)

    print(
        f"种群 {参数.种群规模} × {参数.迭代代数} 代 × "
        f"{len(默认错峰步长表)} 个错峰步长；进程数 = {进程数}"
    )
    print(f"校准：冷 {常量.单次评估冷_s:.2f} s / 热 {常量.单次评估热_s:.2f} s")

    开始 = time.time()
    结果 = 求解联合(
        剖面表,
        环境,
        参数=参数,
        错峰步长表=默认错峰步长表,
        打磨=False,
        进程数=进程数,
        verbose=True,
    )
    耗时 = time.time() - 开始
    print("-" * 78)
    print(f"预热完成：{耗时:.1f} s；前沿 {len(结果.存档)} 个；站解缓存 {结果.缓存规模} 条")
    print("缓存已落盘，正式运行将自动加载。")


if __name__ == "__main__":
    main()

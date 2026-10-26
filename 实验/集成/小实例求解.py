"""集成层小实例求解器：把现有 `求解联合` 跑在缩编场景上。

用法：
    python 实验/集成/小实例求解.py --服务区 S009,S010,S011 --每区箱数 3 \
        --种群 6 --代数 1 --步长 0,900 --进程数 1

用途：E2b 集成层算法对比、E3 消融、E4 灵敏度。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 实验.实例.构造小实例 import 子场景, 截断货箱  # noqa: E402
from 源代码.公共库.通信中继.场景装配 import 装载场景  # noqa: E402
from 源代码.公共库.通信中继.通信模型 import 由场景装配  # noqa: E402
from 源代码.公共库.通信中继.通信剖面 import 构造剖面  # noqa: E402
from 源代码.公共库.通信中继.中继覆盖求解 import 生成候选点  # noqa: E402
from 源代码.公共库.通信中继.多目标求解 import 搜索参数  # noqa: E402
from 源代码.公共库.通信中继.联合调度求解 import 求解联合  # noqa: E402

结果目录 = 项目根 / "结果" / "集成实验"
结果目录.mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--服务区", default="S009,S010,S011")
    parser.add_argument("--每区箱数", type=int, default=3)
    parser.add_argument("--每型无人机", type=int, default=1)
    parser.add_argument("--每型电池", type=int, default=2)
    parser.add_argument("--种群", type=int, default=6)
    parser.add_argument("--代数", type=int, default=1)
    parser.add_argument("--步长", default="0,900")
    parser.add_argument("--进程数", type=int, default=1)
    parser.add_argument("--打磨", action="store_true")
    parser.add_argument("--名称", default="small")
    args = parser.parse_args()

    服务区 = [s.strip() for s in args.服务区.split(",") if s.strip()]
    全 = 装载场景()
    场景 = 子场景(全, 服务区, 每型无人机数=args.每型无人机, 每型电池数=args.每型电池)
    场景 = 截断货箱(场景, args.每区箱数)
    环境 = 由场景装配(场景)
    剖面表 = 构造剖面(场景, 环境)
    候选点表 = 生成候选点(场景, 环境, 剖面表.网关)
    步长 = tuple(float(x) for x in args.步长.split(",") if x.strip())
    参数 = 搜索参数(种群规模=args.种群, 迭代代数=args.代数)

    print(f"实例 {args.名称}: 服务区 {服务区}, 货箱 {len(场景.货箱)}, "
          f"步长 {步长}, 种群 {args.种群} × 代数 {args.代数}, 进程 {args.进程数}")
    开始 = time.time()
    结果 = 求解联合(
        剖面表,
        环境,
        错峰步长表=步长,
        参数=参数,
        候选点表=候选点表,
        打磨=args.打磨,
        进程数=args.进程数,
        verbose=True,
    )
    耗时 = time.time() - 开始
    可行 = [x for x in 结果.存档 if x.是否可行]
    零中断 = [x for x in 可行 if getattr(x.评价, "零中断", False)]
    摘要 = {
        "名称": args.名称,
        "服务区": 服务区,
        "货箱数": len(场景.货箱),
        "种群": args.种群,
        "代数": args.代数,
        "步长": 步长,
        "打磨": args.打磨,
        "墙钟_s": round(耗时, 2),
        "前沿规模": len(结果.存档),
        "全可行数": len(可行),
        "零中断数": len(零中断),
        "代表目标": [
            {
                "目标向量": list(x.评价.目标向量),
                "违反量": x.违反量,
            }
            for x in 结果.存档[:20]
        ],
    }
    (结果目录 / f"{args.名称}.json").write_text(
        json.dumps(摘要, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(摘要, ensure_ascii=False, indent=2)[:2000])


if __name__ == "__main__":
    main()

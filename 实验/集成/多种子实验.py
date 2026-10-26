"""20 种子/多配置集成实验 runner。

支持：
- e2e3：集成层对比与消融（3/4/5 区，20 种子；完整含打磨 5 种子）
- e4：灵敏度（中继数、组件数、机队、rho、需求）
- e5：可扩展性（2–6 区）
- fixed：固定评价预算对比（200/500/1000）

多进程：每个 (配置, 实例, 种子) 是一个任务，8 进程执行。
输出：`结果/多种子/逐次.jsonl`、`结果/多种子/汇总.csv`。
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 实验.实例.构造小实例 import 子场景, 截断货箱  # noqa: E402
from 实验.定理验证.公共 import 非支配  # noqa: E402
from 源代码.公共库.通信中继.场景装配 import 装载场景  # noqa: E402
from 源代码.公共库.通信中继.通信模型 import 由场景装配  # noqa: E402
from 源代码.公共库.通信中继.通信剖面 import 构造剖面  # noqa: E402
from 源代码.公共库.通信中继.构造启发式 import 构造种子, 载荷包  # noqa: E402
from 源代码.公共库.通信中继.中继覆盖求解 import 生成候选点  # noqa: E402
from 源代码.公共库.通信中继.中继模型 import 中继能源池, 构造中继资源  # noqa: E402
from 源代码.公共库.通信中继.资源模型 import 电池状态  # noqa: E402
from 源代码.公共库.通信中继.多目标求解 import 搜索参数  # noqa: E402
from 源代码.公共库.通信中继.联合调度求解 import 构造联合评价器, 求解联合  # noqa: E402
import 源代码.公共库.通信中继.中继驻留排程 as 驻留排程模块  # noqa: E402

结果目录 = 项目根 / "结果" / "多种子"
结果目录.mkdir(parents=True, exist_ok=True)

基础服务区 = ["S009", "S010", "S011", "S012", "S014", "S015"]


def 自定义资源(中继数: int, 组件数: int) -> 中继能源池:
    基 = 构造中继资源()
    return 中继能源池(
        组件={
            f"R-ENG-{i:02d}": 电池状态(编号=f"R-ENG-{i:02d}", 机型编号="R")
            for i in range(1, 组件数 + 1)
        },
        中继机表=tuple(f"R{i:02d}" for i in range(1, 中继数 + 1)),
        等效完全充电时间_s=基.等效完全充电时间_s,
        架次周转时间_s=基.架次周转时间_s,
    )


def 建场景(task: dict):
    全 = 装载场景()
    场景 = 子场景(
        全, task["服务区"],
        每型无人机数=task.get("每型无人机", 1),
        每型电池数=task.get("每型电池", 2),
    )
    场景 = 截断货箱(场景, task.get("每区箱数", 3))
    if task.get("rho") is not None:
        新机型 = {
            k: dataclasses.replace(v, 返航电量下限=task["rho"] * 100.0)
            for k, v in 场景.机型表.items()
        }
        场景 = dataclasses.replace(场景, 机型表=新机型)
    return 场景


def 评价个体(个体) -> dict:
    可行 = bool(个体.是否可行)
    向量 = [float(x) for x in 个体.评价.目标向量]
    return {
        "可行": 可行,
        "零中断": bool(getattr(个体.评价, "零中断", False)),
        "目标向量": 向量,
    }


def 随机重启(评价器, 场景, 种子, 次数, rng):
    出 = []
    for _ in range(次数):
        _, 包列 = 种子[rng.randrange(len(种子))]
        新列 = []
        for 包 in 包列:
            顺序 = list(包.访问顺序)
            rng.shuffle(顺序)
            新列.append(载荷包(箱表=包.箱表, 访问顺序=tuple(顺序)))
        rng.shuffle(新列)
        出.append(评价器(场景, 新列))
    return 出


def 跑任务(task: dict) -> dict:
    驻留排程模块.构造中继资源 = lambda: 自定义资源(
        task.get("中继数", 2), task.get("组件数", 6)
    )
    开始 = time.time()
    场景 = 建场景(task)
    环境 = 由场景装配(场景)
    剖面表 = 构造剖面(场景, 环境)
    候选点表 = 生成候选点(场景, 环境, 剖面表.网关)
    种子 = 构造种子(场景)
    评价器 = 构造联合评价器(剖面表, 环境, 候选点表, {}, 0.0)

    类型 = task.get("任务类型", "solve")
    if 类型 == "greedy":
        个体列 = [评价器(场景, 包列) for _, 包列 in 种子]
    elif 类型 == "random":
        个体列 = 随机重启(
            评价器, 场景, 种子, task.get("随机次数", 144),
            random.Random(20260924 + task["种子"]),
        )
    else:
        种子包序列 = [种子[0]] if task.get("种子选择") == "first" else 种子
        结果 = 求解联合(
            剖面表, 环境, 种子包序列=种子包序列,
            错峰步长表=tuple(task.get("步长", (0.0,))),
            参数=搜索参数(
                种群规模=task.get("种群", 8),
                迭代代数=task.get("代数", 3),
                随机种子=task.get("随机种子", 20260924 + task["种子"]),
            ),
            候选点表=候选点表, 缓存={}, 打磨=task.get("打磨", False), 进程数=1,
        )
        个体列 = 结果.存档

    评价列 = [评价个体(x) for x in 个体列]
    可行 = [x for x in 评价列 if x["可行"]]
    零 = [x for x in 可行 if x["零中断"]]
    向量 = [x["目标向量"] for x in 可行]
    return {
        "实验": task["实验"],
        "配置": task["配置"],
        "实例": task["实例"],
        "服务区": task["服务区"],
        "种子": task["种子"],
        "任务类型": 类型,
        "货箱数": len(场景.货箱),
        "中继数": task.get("中继数", 2),
        "组件数": task.get("组件数", 6),
        "rho": task.get("rho", None),
        "每型无人机": task.get("每型无人机", 1),
        "种群": task.get("种群", 8),
        "代数": task.get("代数", 3),
        "步长数": len(task.get("步长", (0.0,))),
        "打磨": bool(task.get("打磨", False)),
        "前沿规模": len(个体列),
        "可行数": len(可行),
        "零中断数": len(零),
        "最小完成时间_s": min((v[1] for v in 向量), default=float("nan")),
        "最小能耗_kWh": min((v[2] for v in 向量), default=float("nan")),
        "最小运输架次": min((v[3] for v in 向量), default=-1),
        "最小中继架次": min((v[4] for v in 向量), default=-1),
        "墙钟_s": time.time() - 开始,
        "可行目标向量": 向量,
    }


def 生成任务(实验: str) -> list[dict]:
    任务 = []
    if 实验 in ("e2e3", "all"):
        实例 = [
            ("3区", ["S009", "S010", "S011"]),
            ("4区", ["S009", "S010", "S011", "S014"]),
            ("5区", ["S009", "S010", "S011", "S014", "S015"]),
        ]
        配置 = [
            ("完整", dict(种群=8, 代数=3, 步长=(0, 900, 1800), 打磨=True, 任务类型="solve", 种子数=5)),
            ("无打磨", dict(种群=8, 代数=3, 步长=(0, 900, 1800), 打磨=False, 任务类型="solve", 种子数=20)),
            ("单步长", dict(种群=8, 代数=3, 步长=(0,), 打磨=True, 任务类型="solve", 种子数=20)),
            ("单种子", dict(种群=8, 代数=3, 步长=(0, 900, 1800), 打磨=True, 任务类型="solve", 种子选择="first", 种子数=20)),
            ("仅贪心", dict(任务类型="greedy", 种子数=1)),
            ("随机重启", dict(任务类型="random", 随机次数=144, 种子数=20)),
        ]
        for 实例名, 区 in 实例:
            for 配置名, 参数 in 配置:
                for 种子 in range(1, 参数["种子数"] + 1):
                    任务.append({
                        "实验": "e2e3", "配置": 配置名, "实例": 实例名,
                        "服务区": 区, "每区箱数": 3, "每型无人机": 1, "每型电池": 2,
                        "种子": 种子, **参数,
                    })
    if 实验 in ("e4", "all"):
        基准 = dict(服务区=["S009", "S010", "S011", "S014"], 每区箱数=3,
                    每型无人机=1, 每型电池=2, 中继数=2, 组件数=6, rho=0.2)
        配置 = []
        for n in (1, 2, 3):
            配置.append((f"中继数={n}", {**基准, "中继数": n}))
        for n in (2, 4, 6, 8):
            配置.append((f"组件数={n}", {**基准, "组件数": n}))
        for n in (1, 2):
            配置.append((f"每型无人机={n}", {**基准, "每型无人机": n, "每型电池": 2 * n}))
        for r in (0.1, 0.2, 0.3):
            配置.append((f"rho={r}", {**基准, "rho": r}))
        for n in (1, 2, 3):
            配置.append((f"每区箱数={n}", {**基准, "每区箱数": n}))
        for 名, 参数 in 配置:
            for 种子 in range(1, 21):
                任务.append({
                    "实验": "e4", "配置": 名, "实例": "4区", "种子": 种子,
                    "种群": 6, "代数": 2, "步长": (0,), "打磨": False,
                    "任务类型": "solve", **参数,
                })
    if 实验 in ("e5", "all"):
        for 区数 in (2, 3, 4, 5, 6):
            区 = 基础服务区[:区数]
            for 种子 in range(1, 21):
                任务.append({
                    "实验": "e5", "配置": f"{区数}区", "实例": f"{区数}区",
                    "服务区": 区, "每区箱数": 3, "每型无人机": 1, "每型电池": 2,
                    "种子": 种子, "种群": 8, "代数": 2, "步长": (0,),
                    "打磨": False, "任务类型": "solve",
                })
    if 实验 in ("fixed", "all"):
        预算 = [
            ("200", 10, 7, (0, 900, 1800)),
            ("500", 20, 9, (0, 900, 1800)),
            ("1000", 25, 14, (0, 900, 1800)),
        ]
        for 名, pop, gen, steps in 预算:
            for 打磨 in (False, True):
                for 种子 in range(1, 6):
                    任务.append({
                        "实验": "fixed", "配置": f"{'打磨' if 打磨 else '无打磨'}_{名}",
                        "实例": "4区", "服务区": ["S009", "S010", "S011", "S014"],
                        "每区箱数": 3, "每型无人机": 1, "每型电池": 2,
                        "种子": 种子, "种群": pop, "代数": gen, "步长": steps,
                        "打磨": 打磨, "任务类型": "solve",
                    })
    return 任务


def 主函数() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--实验", choices=["e2e3", "e4", "e5", "fixed", "all"], default="all")
    parser.add_argument("--进程", type=int, default=8)
    args = parser.parse_args()
    任务 = 生成任务(args.实验)
    print(f"任务数 {len(任务)}，进程 {args.进程}")
    行 = []
    with ProcessPoolExecutor(max_workers=args.进程) as 池:
        任务表 = {池.submit(跑任务, t): t for t in 任务}
        for i, 任 in enumerate(as_completed(任务表), start=1):
            try:
                r = 任.result()
            except Exception as e:
                t = 任务表[任]
                r = {**{k: t.get(k) for k in ("实验", "配置", "实例", "种子")}, "错误": repr(e)}
            print(f"[{i}/{len(任务)}] {r.get('实验')} {r.get('配置')} {r.get('实例')} 种子{r.get('种子')}")
            行.append(r)
    (结果目录 / "逐次.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in 行) + "\n",
        encoding="utf-8",
    )
    print(f"完成：{结果目录 / '逐次.jsonl'}")


if __name__ == "__main__":
    主函数()

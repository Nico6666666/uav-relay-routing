"""E4：灵敏度分析（小实例，多进程实验级并行）。

扫描：
- 中继无人机数：1 / 2 / 3；
- 中继能源组件数：2 / 4 / 6 / 8；
- 每型实体无人机数：1 / 2；
- 返航安全余量 rho：10% / 20% / 30%；
- 每区货箱数：1 / 2 / 3。

每个配置用同一小实例、同一小预算（8×2×1，无打磨），记录：
前沿规模、可行数、零中断数、最小完成时间、最小能耗、最小运输架次、最小中继架次、墙钟。
"""
from __future__ import annotations

import dataclasses
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 实验.实例.构造小实例 import 子场景, 截断货箱  # noqa: E402
from 实验.定理验证.公共 import 写CSV  # noqa: E402
from 源代码.公共库.通信中继.场景装配 import 装载场景  # noqa: E402
from 源代码.公共库.通信中继.通信模型 import 由场景装配  # noqa: E402
from 源代码.公共库.通信中继.通信剖面 import 构造剖面  # noqa: E402
from 源代码.公共库.通信中继.中继覆盖求解 import 生成候选点  # noqa: E402
from 源代码.公共库.通信中继.中继模型 import 构造中继资源, 中继能源池  # noqa: E402
from 源代码.公共库.通信中继.资源模型 import 电池状态  # noqa: E402
from 源代码.公共库.通信中继.多目标求解 import 搜索参数  # noqa: E402
from 源代码.公共库.通信中继.联合调度求解 import 求解联合  # noqa: E402
import 源代码.公共库.通信中继.中继驻留排程 as 驻留排程模块  # noqa: E402

结果目录 = 项目根 / "结果" / "集成实验"
结果目录.mkdir(parents=True, exist_ok=True)

服务区 = ["S009", "S010", "S011", "S014"]
种群 = 8
代数 = 2
步长表 = (0.0,)


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


def 跑配置(配置: dict) -> dict:
    # 每个 worker 内单独 patch 中继资源
    驻留排程模块.构造中继资源 = lambda: 自定义资源(
        配置.get("中继数", 2), 配置.get("组件数", 6)
    )
    全 = 装载场景()
    场景 = 子场景(
        全,
        服务区,
        每型无人机数=配置.get("每型无人机", 1),
        每型电池数=配置.get("每型电池", 2),
    )
    场景 = 截断货箱(场景, 配置.get("每区箱数", 3))
    if 配置.get("rho") is not None:
        新机型 = {
            k: dataclasses.replace(v, 返航电量下限=配置["rho"] * 100.0)
            for k, v in 场景.机型表.items()
        }
        场景 = dataclasses.replace(场景, 机型表=新机型)
    环境 = 由场景装配(场景)
    剖面表 = 构造剖面(场景, 环境)
    候选点表 = 生成候选点(场景, 环境, 剖面表.网关)
    开始 = time.time()
    结果 = 求解联合(
        剖面表, 环境, 错峰步长表=步长表,
        参数=搜索参数(种群规模=种群, 迭代代数=代数),
        候选点表=候选点表, 缓存={}, 打磨=False, 进程数=1,
    )
    耗时 = time.time() - 开始
    可行 = [x for x in 结果.存档 if x.是否可行]
    零 = [x for x in 可行 if getattr(x.评价, "零中断", False)]
    向量 = [x.评价.目标向量 for x in 可行]
    return {
        "参数": 配置.get("参数", ""),
        "取值": 配置.get("取值", ""),
        "货箱数": len(场景.货箱),
        "中继数": 配置.get("中继数", 2),
        "组件数": 配置.get("组件数", 6),
        "每型无人机": 配置.get("每型无人机", 1),
        "rho": 配置.get("rho", 0.2),
        "前沿规模": len(结果.存档),
        "可行数": len(可行),
        "零中断数": len(零),
        "最小完成时间_s": f"{min((v[1] for v in 向量), default=float('nan')):.3f}",
        "最小能耗_kWh": f"{min((v[2] for v in 向量), default=float('nan')):.6f}",
        "最小运输架次": min((v[3] for v in 向量), default=-1),
        "最小中继架次": min((v[4] for v in 向量), default=-1),
        "墙钟_s": f"{耗时:.2f}",
    }


def 配置表() -> list[dict]:
    出 = []
    for n in (1, 2, 3):
        出.append({"参数": "中继数", "取值": n, "中继数": n})
    for n in (2, 4, 6, 8):
        出.append({"参数": "组件数", "取值": n, "组件数": n})
    for n in (1, 2):
        出.append({"参数": "每型无人机", "取值": n, "每型无人机": n, "每型电池": 2 * n})
    for r in (0.10, 0.20, 0.30):
        出.append({"参数": "rho", "取值": r, "rho": r})
    for n in (1, 2, 3):
        出.append({"参数": "每区箱数", "取值": n, "每区箱数": n})
    return 出


def 主函数() -> None:
    配置 = 配置表()
    行 = []
    with ProcessPoolExecutor(max_workers=4) as 池:
        任务 = {池.submit(跑配置, c): c for c in 配置}
        for 任 in as_completed(任务):
            c = 任务[任]
            try:
                r = 任.result()
            except Exception as e:
                r = {"参数": c.get("参数"), "取值": c.get("取值"), "错误": repr(e)}
            print(r)
            行.append(r)
    写CSV(
        结果目录 / "e4_灵敏度.csv",
        行,
        ["参数", "取值", "货箱数", "中继数", "组件数", "每型无人机", "rho",
         "前沿规模", "可行数", "零中断数", "最小完成时间_s", "最小能耗_kWh",
         "最小运输架次", "最小中继架次", "墙钟_s", "错误"],
    )
    print(f"E4 完成：结果写入 {结果目录}")


if __name__ == "__main__":
    主函数()

"""E1c：小实例上的“真实缺口 + 精确中继覆盖”基准。

流程：
1. 用 2 个服务区、6 个货箱构造一个真实运输方案；
2. 用真实通信模型解析缺口；
3. 用真实候选驻留点构造覆盖表；
4. 用集合覆盖 MILP（HiGHS）求“最少驻留点数覆盖全部缺口”；
5. 与确定性中继 oracle（`中继排程.评估`）的未覆盖数、中继架次数对照。

说明：
- 该基准验证“覆盖层”在真实缺口上的精确性；
- 不含中继逐站建链、转场、能源组件周转与时间窗排程；这些由标准档自检与后续 E1d 覆盖。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 实验.实例.构造小实例 import 小实例  # noqa: E402
from 实验.定理验证.公共 import 写CSV  # noqa: E402
from 源代码.公共库.通信中继.场景装配 import 装载场景  # noqa: E402
from 源代码.公共库.通信中继.通信模型 import 由场景装配  # noqa: E402
from 源代码.公共库.通信中继.通信剖面 import 构造剖面  # noqa: E402
from 源代码.公共库.通信中继.缺口解析 import 解析缺口  # noqa: E402
from 源代码.公共库.通信中继.多点飞行模型 import 多点架次代价  # noqa: E402
from 源代码.公共库.通信中继.方案结构 import 全局方案, 架次, 调度记录  # noqa: E402
from 源代码.公共库.通信中继.资源模型 import 充电时长, 结束SOC  # noqa: E402
from 源代码.公共库.通信中继.中继覆盖求解 import 生成候选点  # noqa: E402
from 源代码.公共库.通信中继.中继覆盖关系 import 候选覆盖表  # noqa: E402
from 源代码.公共库.通信中继.中继排程 import 评估  # noqa: E402

结果目录 = 项目根 / "结果" / "精确基准"
结果目录.mkdir(parents=True, exist_ok=True)


def 构造运输方案(场景) -> 全局方案:
    机 = 场景.机型表["C"]
    架次列表 = []
    调度表 = {}
    开始 = 0.0
    for 序, 区 in enumerate(场景.编号顺序, start=1):
        箱列 = 场景.货箱归属[区]
        代价 = 多点架次代价(场景, 机, (区,), [箱列])
        架 = 架次(
            序号=序,
            机型编号="C",
            服务区序列=(区,),
            各区箱编号=(tuple(b["货箱编号"] for b in 箱列),),
            代价=代价,
        )
        结束 = 结束SOC(机, 代价.总能耗)
        充 = 充电时长(场景.电池表["C"]["等效完全充电时间"], 结束)
        记录 = 调度记录(
            架次序号=序,
            机型编号="C",
            无人机编号="U07",
            电池编号="C-BAT-01",
            开始时刻=开始,
            返回时刻=开始 + 代价.作业时间,
            起始SOC=1.0,
            结束SOC=结束,
            电池可用时刻=开始 + 代价.作业时间 + 充,
        )
        架次列表.append(架)
        调度表[序] = 记录
        开始 = 记录.电池可用时刻
    return 全局方案(架次列表=架次列表, 调度表=调度表)


def 解集合覆盖(覆盖表, 罚: float = 100.0):
    n = 覆盖表.缺口数
    点序 = sorted(覆盖表.掩码)
    m = len(点序)
    A = np.zeros((n, m + n), dtype=float)
    for j, p in enumerate(点序):
        掩码 = 覆盖表.掩码[p]
        for g in range(n):
            if 掩码 >> g & 1:
                A[g, j] = 1.0
    for g in range(n):
        A[g, m + g] = 1.0
    c = np.array([1.0] * m + [罚] * n, dtype=float)
    结果 = milp(
        c=c,
        integrality=np.ones(m + n),
        bounds=Bounds(np.zeros(m + n), np.ones(m + n)),
        constraints=LinearConstraint(A, np.ones(n), np.full(n, np.inf)),
        options={"time_limit": 120},
    )
    return 结果, 点序


def main() -> None:
    实例 = 小实例()
    场景 = 实例.场景
    环境 = 由场景装配(场景)
    剖面表 = 构造剖面(场景, 环境)
    方案 = 构造运输方案(场景)
    缺口集合 = 解析缺口(剖面表, 方案)
    候选点表 = 生成候选点(场景, 环境, 剖面表.网关)
    缓存: dict = {}
    覆盖表 = 候选覆盖表(剖面表, 环境, 缺口集合, 候选点表, 缓存)

    结果, 点序 = 解集合覆盖(覆盖表)
    if 结果.success:
        值 = np.asarray(结果.x)
        m = len(点序)
        最少驻留点 = int(round(float(值[:m].sum())))
        未覆盖 = int(round(float(值[m:].sum())))
    else:
        最少驻留点 = -1
        未覆盖 = -1

    联合, 摘要 = 评估(剖面表, 环境, 方案.架次列表, 候选点表, 缓存)

    行 = [{
        "服务区": "、".join(场景.编号顺序),
        "货箱数": len(场景.货箱),
        "运输架次": len(方案.架次列表),
        "缺口数": 缺口集合.缺口数,
        "缺口位姿数": sum(缺.位姿数 for 缺 in 缺口集合.缺口列表),
        "候选点数": len(候选点表),
        "覆盖表中的点数": len(点序),
        "MILP状态": int(结果.status),
        "精确最少驻留点": 最少驻留点,
        "精确未覆盖缺口": 未覆盖,
        "启发式中继架次": 联合.中继方案.架次数,
        "启发式未覆盖缺口": int(摘要.get("未覆盖缺口数", -1)),
        "启发式中继站数": int(摘要.get("中继站数", -1)) if "中继站数" in 摘要 else "",
    }]
    写CSV(
        结果目录 / "e1c_集成中继覆盖.csv",
        行,
        ["服务区", "货箱数", "运输架次", "缺口数", "缺口位姿数", "候选点数",
         "覆盖表中的点数", "MILP状态", "精确最少驻留点", "精确未覆盖缺口",
         "启发式中继架次", "启发式未覆盖缺口", "启发式中继站数"],
    )
    for k, v in 行[0].items():
        print(f"{k}: {v}")
    print(f"结果写入 {结果目录 / 'e1c_集成中继覆盖.csv'}")


if __name__ == "__main__":
    main()

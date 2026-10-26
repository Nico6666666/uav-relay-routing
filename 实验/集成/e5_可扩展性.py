"""E5：可扩展性（小实例，多进程实验级并行）。

服务区数：2 / 3 / 4 / 5 / 6；每区 3 箱；每型 1 架、2 组电池；
预算 8×2×1、无打磨。另附标准档 15 服务区 / 80 箱的结果作大规模数据点。
30/50 服务区在现有数据中不存在，本文如实标注为未运行。
"""
from __future__ import annotations

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
from 源代码.公共库.通信中继.多目标求解 import 搜索参数  # noqa: E402
from 源代码.公共库.通信中继.联合调度求解 import 求解联合  # noqa: E402

结果目录 = 项目根 / "结果" / "集成实验"
结果目录.mkdir(parents=True, exist_ok=True)

配置列表 = [
    ["S009", "S010"],
    ["S009", "S010", "S011"],
    ["S009", "S010", "S011", "S014"],
    ["S009", "S010", "S011", "S014", "S015"],
    ["S009", "S010", "S011", "S012", "S014", "S015"],
]


def 跑配置(服务区: list[str]) -> dict:
    全 = 装载场景()
    场景 = 子场景(全, 服务区, 每型无人机数=1, 每型电池数=2)
    场景 = 截断货箱(场景, 3)
    环境 = 由场景装配(场景)
    剖面表 = 构造剖面(场景, 环境)
    候选点表 = 生成候选点(场景, 环境, 剖面表.网关)
    开始 = time.time()
    结果 = 求解联合(
        剖面表, 环境, 错峰步长表=(0.0,),
        参数=搜索参数(种群规模=8, 迭代代数=2),
        候选点表=候选点表, 缓存={}, 打磨=False, 进程数=1,
    )
    耗时 = time.time() - 开始
    可行 = [x for x in 结果.存档 if x.是否可行]
    零 = [x for x in 可行 if getattr(x.评价, "零中断", False)]
    return {
        "服务区数": len(服务区),
        "货箱数": len(场景.货箱),
        "服务区": "、".join(服务区),
        "前沿规模": len(结果.存档),
        "可行数": len(可行),
        "零中断数": len(零),
        "墙钟_s": f"{耗时:.2f}",
        "备注": "小实例 8×2×1 无打磨",
    }


def 主函数() -> None:
    行 = []
    with ProcessPoolExecutor(max_workers=4) as 池:
        任务 = {池.submit(跑配置, c): c for c in 配置列表}
        for 任 in as_completed(任务):
            try:
                r = 任.result()
            except Exception as e:
                r = {"服务区": "、".join(任务[任]), "错误": repr(e)}
            print(r)
            行.append(r)

    # 标准档 15 服务区数据点（已跑，不重跑）
    行.append({
        "服务区数": 15,
        "货箱数": 80,
        "服务区": "全部",
        "前沿规模": 37,
        "可行数": 37,
        "零中断数": 37,
        "墙钟_s": "4748.5",
        "备注": "标准档 60×24×7，含打磨与 8 进程",
    })

    写CSV(
        结果目录 / "e5_可扩展性.csv",
        行,
        ["服务区数", "货箱数", "服务区", "前沿规模", "可行数", "零中断数", "墙钟_s", "备注", "错误"],
    )
    print(f"E5 完成：结果写入 {结果目录}")


if __name__ == "__main__":
    主函数()

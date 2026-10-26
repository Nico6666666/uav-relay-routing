"""E3 完整配置 20 种子：分块运行（每 5 个种子重建进程池）。

这样避免长寿命进程池在 worker 回收时挂住；每块跑完即落盘。
"""
from __future__ import annotations

import json
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
]
输出 = 项目根 / "结果" / "多种子" / "逐次_e3_完整20_分块.jsonl"


def 跑一块(任务: list[dict]) -> list[dict]:
    行 = []
    with ProcessPoolExecutor(max_workers=4) as 池:
        表 = {池.submit(跑任务, t): t for t in 任务}
        for 任 in as_completed(表):
            try:
                r = 任.result()
            except Exception as e:
                t = 表[任]
                r = {**{k: t.get(k) for k in ("实验", "配置", "实例", "种子")}, "错误": repr(e)}
            行.append(r)
    return 行


def main() -> None:
    if 输出.exists():
        输出.unlink()
    for 名, 区 in 实例:
        for 起 in range(1, 21, 5):
            种子列 = list(range(起, min(起 + 5, 21)))
            任务 = [{
                "实验": "e2e3", "配置": "完整", "实例": 名, "服务区": 区,
                "每区箱数": 3, "每型无人机": 1, "每型电池": 2, "种子": 种子,
                "种群": 8, "代数": 3, "步长": (0, 900, 1800),
                "打磨": True, "任务类型": "solve",
            } for 种子 in 种子列]
            行 = 跑一块(任务)
            with 输出.open("a", encoding="utf-8") as f:
                for r in 行:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            好 = [r for r in 行 if "错误" not in r]
            print(f"{名} 种子 {种子列[0]}–{种子列[-1]}：{len(好)}/{len(行)} 成功，"
                  f"可行均值 {sum(r['可行数'] for r in 好) / max(1, len(好)):.1f}", flush=True)


if __name__ == "__main__":
    main()

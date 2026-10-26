"""补充 E5 的 6 区实例（20 种子）。"""
from __future__ import annotations
import json, sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))
from 实验.集成.多种子实验 import 跑任务
区 = ["S009", "S010", "S011", "S012", "S014", "S015"]
def main():
    任务 = []
    for 种子 in range(1, 21):
        任务.append({
            "实验": "e5", "配置": "6区", "实例": "6区", "服务区": 区,
            "每区箱数": 3, "每型无人机": 1, "每型电池": 2, "种子": 种子,
            "种群": 8, "代数": 2, "步长": (0,), "打磨": False, "任务类型": "solve",
        })
    行 = []
    with ProcessPoolExecutor(max_workers=8) as 池:
        表 = {池.submit(跑任务, t): t for t in 任务}
        for i, 任 in enumerate(as_completed(表), 1):
            try:
                r = 任.result()
            except Exception as e:
                t = 表[任]
                r = {**{k: t.get(k) for k in ("实验", "配置", "实例", "种子")}, "错误": repr(e)}
            print(i, r.get("配置"), r.get("种子"), r.get("可行数"), r.get("墙钟_s"))
            行.append(r)
    (项目根 / "结果/多种子/逐次_e5_6区.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in 行) + "\n", encoding="utf-8")
if __name__ == "__main__":
    main()

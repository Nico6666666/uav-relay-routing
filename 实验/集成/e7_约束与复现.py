"""E7：约束检验与复现性汇总。

- 解析标准档的十七类约束检验；
- 统计自检条目；
- 记录关键输出文件哈希；
- 用同一小实例重复运行两次，比较前沿/目标向量是否逐位一致。
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

项目根 = Path(__file__).resolve().parents[2]
if str(项目根) not in sys.path:
    sys.path.insert(0, str(项目根))

from 实验.定理验证.公共 import 写CSV  # noqa: E402

标准根 = 项目根 / "结果" / "标准档_20261025"
联合调度与中继 = 标准根 / "联合调度与中继"
检验文件 = 联合调度与中继 / "方案检验" / "通信保障与可行性检验.md"
自检文件 = 联合调度与中继 / "五目标优化" / "自检记录.md"
结果目录 = 项目根 / "结果" / "约束与复现"
结果目录.mkdir(parents=True, exist_ok=True)


def 哈希(路径: Path) -> str:
    摘要 = hashlib.sha256()
    with 路径.open("rb") as f:
        for 块 in iter(lambda: f.read(1 << 20), b""):
            摘要.update(块)
    return 摘要.hexdigest()


def 主函数() -> None:
    行 = []
    if 检验文件.exists():
        文本 = 检验文件.read_text(encoding="utf-8")
        违反类 = 0
        类别数 = 0
        for 行文本 in 文本.splitlines():
            去 = 行文本.strip()
            if 去.startswith("|") and any(ch in 去[:4] for ch in "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰"):
                类别数 += 1
                if "| 0 | 0 | 0 | 0 | 0 | 0 |" not in 去:
                    违反类 += 1
        行.append({"检查组": "十七类约束", "通过": max(0, 类别数 - 违反类),
                   "不通过": 违反类,
                   "结论": "通过" if 违反类 == 0 and 类别数 > 0 else "需核对"})
    else:
        行.append({"检查组": "十七类约束", "通过": "", "不通过": "", "结论": "文件缺失"})

    if 自检文件.exists():
        文本 = 自检文件.read_text(encoding="utf-8")
        条数 = len(re.findall(r"^\s*\d+\.\s*\[(自检|内核)", 文本, flags=re.M))
        行.append({"检查组": "自检记录", "通过": 条数, "不通过": 0,
                   "结论": "通过" if 条数 > 0 else "未识别"})

    # 关键文件哈希
    for 相对 in [
        "联合调度与中继/五目标优化/Pareto前沿.csv",
        "联合调度与中继/五目标优化/代表方案.json",
        "联合调度与中继/方案检验/通信保障与可行性检验.md",
        "哈希清单.csv",
    ]:
        p = 标准根 / 相对
        if p.exists():
            行.append({"检查组": f"哈希 {相对}", "通过": "", "不通过": "",
                       "结论": 哈希(p)})

    # 重复运行小实例
    名称 = ["e7_run1", "e7_run2"]
    for 名 in 名称:
        命令 = [
            sys.executable, str(项目根 / "实验/集成/小实例求解.py"),
            "--名称", 名, "--服务区", "S009,S010", "--每区箱数", "3",
            "--每型无人机", "1", "--每型电池", "2",
            "--种群", "4", "--代数", "1", "--步长", "0", "--进程数", "1",
        ]
        subprocess.run(命令, cwd=项目根, check=True, stdout=subprocess.DEVNULL)
    j1 = json.loads((项目根 / "结果/集成实验/e7_run1.json").read_text(encoding="utf-8"))
    j2 = json.loads((项目根 / "结果/集成实验/e7_run2.json").read_text(encoding="utf-8"))
    键 = ["前沿规模", "全可行数", "零中断数", "代表目标"]
    一致 = all(j1.get(k) == j2.get(k) for k in 键)
    行.append({"检查组": "重复运行一致性", "通过": "是" if 一致 else "否",
               "不通过": "0" if 一致 else "1",
               "结论": "通过" if 一致 else "失败"})

    写CSV(结果目录 / "e7_约束与复现.csv", 行, ["检查组", "通过", "不通过", "结论"])
    for r in 行:
        print(r)
    print(f"E7 完成：结果写入 {结果目录}")


if __name__ == "__main__":
    主函数()

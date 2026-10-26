"""本仓库的统一运行入口。

用法：
    python 运行入口.py 最大安全载荷
    python 运行入口.py 可行组批
    python 运行入口.py 精确前沿
    python 运行入口.py 余量灵敏度
    python 运行入口.py 多目标优化
    python 运行入口.py 运输方案检验
    python 运行入口.py 联合调度 --规模 快速
    python 运行入口.py 联合方案检验
    python 运行入口.py 分区配置
    python 运行入口.py 资源缺口
    python 运行入口.py 预热缓存
    python 运行入口.py 全部 --联合规模 快速

`全部` 按依赖顺序串行运行；联合调度默认「快速」，可用 `--联合规模 标准` 覆盖。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

项目根 = Path(__file__).resolve().parent
求解器 = 项目根 / "源代码" / "求解器"

命令表 = {
    "最大安全载荷": 求解器 / "单点往返与组批" / "最大安全载荷" / "主程序.py",
    "可行组批": 求解器 / "单点往返与组批" / "可行组批" / "主程序.py",
    "精确前沿": 求解器 / "单点往返与组批" / "精确前沿" / "主程序.py",
    "余量灵敏度": 求解器 / "单点往返与组批" / "余量灵敏度" / "主程序.py",
    "多目标优化": 求解器 / "多点多架次调度" / "多目标优化" / "主程序.py",
    "运输方案检验": 求解器 / "多点多架次调度" / "方案检验" / "主程序.py",
    "联合调度": 求解器 / "联合调度与中继" / "五目标优化" / "主程序.py",
    "联合方案检验": 求解器 / "联合调度与中继" / "方案检验" / "主程序.py",
    "分区配置": 求解器 / "分区与资源核算" / "分区配置" / "主程序.py",
    "资源缺口": 求解器 / "分区与资源核算" / "资源缺口" / "主程序.py",
    "预热缓存": 项目根 / "工具" / "预热缓存.py",
}

全部顺序 = [
    "最大安全载荷",
    "可行组批",
    "精确前沿",
    "余量灵敏度",
    "多目标优化",
    "运输方案检验",
    "联合调度",
    "联合方案检验",
    "分区配置",
    "资源缺口",
]


def 打印帮助() -> None:
    print(__doc__)
    print("可用命令：")
    for 名, 路径 in 命令表.items():
        print(f"  {名:<8} -> {路径.relative_to(项目根)}")


def 运行(命令: str, 参数: list[str]) -> int:
    脚本 = 命令表.get(命令)
    if 脚本 is None:
        print(f"未知命令：{命令}")
        打印帮助()
        return 2
    if not 脚本.exists():
        print(f"找不到脚本：{脚本}")
        return 2
    print(f"\n>>> {命令}：{脚本.relative_to(项目根)}")
    结果 = subprocess.run([sys.executable, str(脚本), *参数], cwd=项目根)
    return 结果.returncode


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "--帮助"):
        打印帮助()
        return 0

    命令 = sys.argv[1]
    if 命令 == "全部":
        参数 = sys.argv[2:]
        联合规模 = "快速"
        if "--联合规模" in 参数:
            位 = 参数.index("--联合规模")
            联合规模 = 参数[位 + 1]
            参数 = 参数[:位] + 参数[位 + 2:]
        for 名 in 全部顺序:
            本次 = list(参数)
            if 名 == "联合调度":
                本次 += ["--规模", 联合规模]
            if 名 == "联合方案检验" and 联合规模 == "试跑":
                print("（试跑档只验证流程，仍继续运行联合方案检验）")
            码 = 运行(名, 本次)
            if 码 != 0:
                print(f"\n命令 {名} 失败，退出码 {码}；后续命令不再执行。")
                return 码
        print("\n全部命令执行完毕。")
        return 0

    return 运行(命令, sys.argv[2:])


if __name__ == "__main__":
    raise SystemExit(main())

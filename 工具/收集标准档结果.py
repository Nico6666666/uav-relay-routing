"""收集标准档运行输出，复制到 `结果/标准档_<日期>/` 并生成哈希清单。

用法：
    python 工具/收集标准档结果.py
    python 工具/收集标准档结果.py --日期 20261025

只复制 `输出/` 目录，不改动源输出。哈希清单用于论文数字溯源。
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

项目根 = Path(__file__).resolve().parents[1]
求解器 = 项目根 / "源代码" / "求解器"

# (源输出目录, 目标子目录)
映射 = [
    (求解器 / "单点往返与组批" / "最大安全载荷" / "输出", "单点往返与组批/最大安全载荷"),
    (求解器 / "单点往返与组批" / "可行组批" / "输出", "单点往返与组批/可行组批"),
    (求解器 / "单点往返与组批" / "精确前沿" / "输出", "单点往返与组批/精确前沿"),
    (求解器 / "单点往返与组批" / "余量灵敏度" / "输出", "单点往返与组批/余量灵敏度"),
    (求解器 / "多点多架次调度" / "多目标优化" / "输出", "多点多架次调度/多目标优化"),
    (求解器 / "多点多架次调度" / "方案检验" / "输出", "多点多架次调度/方案检验"),
    (求解器 / "联合调度与中继" / "五目标优化" / "输出", "联合调度与中继/五目标优化"),
    (求解器 / "联合调度与中继" / "方案检验" / "输出", "联合调度与中继/方案检验"),
    (求解器 / "分区与资源核算" / "分区配置" / "输出", "分区与资源核算/分区配置"),
    (求解器 / "分区与资源核算" / "资源缺口" / "输出", "分区与资源核算/资源缺口"),
]


def 哈希(路径: Path) -> str:
    摘要 = hashlib.sha256()
    with 路径.open("rb") as f:
        for 块 in iter(lambda: f.read(1 << 20), b""):
            摘要.update(块)
    return 摘要.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--日期", default="20261025")
    args = parser.parse_args()

    目标根 = 项目根 / "结果" / f"标准档_{args.日期}"
    目标根.mkdir(parents=True, exist_ok=True)

    行 = ["相对路径,字节,sha256"]
    缺失 = []
    for 源, 子目录 in 映射:
        if not 源.exists():
            缺失.append(str(源.relative_to(项目根)))
            continue
        目标 = 目标根 / 子目录
        if 目标.exists():
            shutil.rmtree(目标)
        shutil.copytree(源, 目标)
        for p in sorted(目标.rglob("*")):
            if p.is_file():
                行.append(f"{p.relative_to(目标根).as_posix()},{p.stat().st_size},{哈希(p)}")

    (目标根 / "哈希清单.csv").write_text("\n".join(行) + "\n", encoding="utf-8")
    print(f"已复制到：{目标根}")
    print(f"文件数：{len(行) - 1}")
    if 缺失:
        print("缺失的输出目录：")
        for m in 缺失:
            print("  ", m)


if __name__ == "__main__":
    main()

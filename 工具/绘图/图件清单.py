"""生成论文图件清单：语言、图号、文件、哈希、生成命令、数据源。"""
from __future__ import annotations

import hashlib
from pathlib import Path

项目根 = Path(__file__).resolve().parents[2]
图根 = 项目根 / "结果" / "论文图"
清单 = 图根 / "图件清单.csv"

数据源 = {
    1: "基础数据/DEM + 调度中心与服务区",
    2: "手工绘制（求解框架）",
    3: "联合调度与中继/方案检验/各方案/最及时/通信缺口清单.csv",
    4: "联合调度与中继/五目标优化/Pareto前沿.csv + 代表方案.json",
    5: "联合调度与中继/方案检验/各方案/最及时/架次安排.csv",
    6: "中继架次与悬停站.csv + 通信保障关系.csv",
    7: "待补（E3 消融）",
    8: "待补（E4 灵敏度）",
    9: "待补（E5 可扩展性）",
}


def 哈希(路径: Path) -> str:
    摘要 = hashlib.sha256()
    with 路径.open("rb") as f:
        for 块 in iter(lambda: f.read(1 << 20), b""):
            摘要.update(块)
    return 摘要.hexdigest()


def main() -> None:
    行 = ["语言,图号,文件,字节,sha256,数据源,生成命令"]
    命令 = "python 工具/绘图/生成论文图.py --语言 all"
    for 语言 in ("中文", "英文"):
        目录 = 图根 / 语言
        if not 目录.exists():
            continue
        for p in sorted(目录.iterdir()):
            if p.suffix.lower() not in (".png", ".svg"):
                continue
            名 = p.stem
            if 名.startswith("图"):
                图号 = int(名[1:3])
            elif 名.startswith("Fig"):
                图号 = int(名[3:5])
            else:
                continue
            行.append(
                f"{语言},{图号},{p.relative_to(图根).as_posix()},{p.stat().st_size},"
                f"{哈希(p)},{数据源.get(图号, '')},{命令}"
            )
    清单.write_text("\n".join(行) + "\n", encoding="utf-8-sig")
    print(f"图件清单写入 {清单}，共 {len(行) - 1} 个文件")


if __name__ == "__main__":
    main()

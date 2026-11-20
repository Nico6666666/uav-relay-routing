# 返修核验脚本

本目录保存论文返修阶段新增的实验核验脚本，不参与主求解流程。

## 目录

```
工具/返修核验/
├── round3/
│   ├── analyze_a1.py    # A1：等预算 single-step（8×9×1=72）的 HV/IGD/配对统计
│   └── analyze_r1b.py   # R1-B：每个运行的目标向量去重后重算 E3，检查去重影响
└── README.md
```

## 运行

在仓库根目录执行：

```bash
python 实验/集成/e3_single_step_72.py          # 100 次运行，写入 结果/多种子_round3/
python 工具/返修核验/round3/analyze_a1.py      # 生成 A1_report.md、统计_A1.csv
python 工具/返修核验/round3/analyze_r1b.py     # 生成 R1B_report.md
```

依赖：`numpy`、`scipy`、`pymoo`。

## A1：等预算 single-step

- 目的：把 single-step 从 24 次评价（8×3×1）提升到 72 次（8×9×1），与 full 的 8×3×3 对齐。
- 设置：种群 8、代数 9、错峰步长 1、20 seeds、5 个实例（3–7 区）。
- 输出：`结果/多种子_round3/逐次_e3_单步长72.jsonl`。

`analyze_a1.py` 用**原始 E3 数据**重建参考前沿，只把新 single-step 作为被评价对象，不把它加入参考前沿。关键结果：

| 配置 | Mean HV | Mean IGD |
|---|---:|---:|
| Full（8×3×3） | 0.1369 | 0.1124 |
| Single step（8×9×1） | 0.1268 | 0.1476 |
| No polishing | 0.0875 | 0.2268 |

- Full vs single-step72：HV gain **0.0101**（95% CI [0.0023, 0.0217]，W/T/L 69/11/20，p=3.07e-08）；IGD difference **−0.0352**（p=5.10e-08）。
- `conclusion_changed: False`：等预算下“time staggering 有效”的结论保留并增强。

## R1-B：目标向量去重核验

- 对每次运行的 `可行目标向量` 按 9 位小数去重，再算 HV/IGD；参考前沿仍由原始数据重建。
- 结果：所有配置的 mean HV/IGD 与论文一致；随机重启 3 区从 144 点去重到 9 点，IGD 仍为 0.0514（IGD 是参考点到解集的距离，重复点不影响）。
- 结论：Table 10/11 不需要因去重而改；随机重启的 `汇总.csv` std 异常属于另一处聚合列问题。

## 与论文补充材料的关系

`补充材料/` 保存论文提交用的审计/台账文件；本目录的脚本只负责生成 `结果/多种子_round3/` 中的 A1/R1 报告。论文级的 58/65 项一致性检查脚本在论文返修工作区，不放入本仓库。

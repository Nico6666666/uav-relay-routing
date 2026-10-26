# UAV Transport–Relay Scheduling: Code and Experiments

This repository provides the code and experiments for our study on heterogeneous
UAV relief logistics under continuous communication constraints, covering payload
and batching analysis, multi-point multi-sortie scheduling, joint transport–relay
scheduling, and task partitioning with resource accounting.

中文版：[README.md](README.md)

## 1. What the code does

The pipeline has four layers. Each layer reads only the JSON output of the layer
above it.

| Layer | What is solved | Method | Main outputs |
|---|---|---|---|
| **Single-trip batching** | Maximum safe payload per aircraft type and service area; feasible box batching; exact three-objective frontier; sensitivity to the return reserve | Analytical payload, FFD packing, dynamic-programming Pareto frontier, ε-constraint | Payload tables, batching plans, Pareto front, sensitivity curves |
| **Multi-point multi-sortie scheduling** | Multi-stop visit order, aircraft assignment, sortie timing; four-objective trade-off | Seeded construction + non-dominated sorting GA + local refinement | Four-objective Pareto front, representative plans, nine-class constraint report |
| **Joint transport–relay scheduling** | Joint schedule of transport and relay UAVs; five-objective trade-off; stagger vs. first-batch deadline | Layered encoding + deterministic relay oracle; zero interruption as an admission condition | Five-objective Pareto front, six representative plans, seventeen-class constraint report |
| **Partition and resource accounting** | 2/3 task-group partitions, group-level resource demand, gaps and causes | Service-area atoms + streaming partition enumeration + interval-graph peak concurrency + gap attribution | Partition plans, peak concurrency, resource gaps and causes |

**Joint transport–relay scheduling is the main contribution**; the first two
layers provide the batching basis and a no-communication baseline.

## 2. Quick start

Requirements: Python 3.11 (3.9+ works), `numpy >= 2`, `scipy >= 1.15`,
`matplotlib >= 3.10`.

```bash
pip install -r requirements.txt

# Four layers, stage by stage
python 运行入口.py 最大安全载荷
python 运行入口.py 可行组批
python 运行入口.py 精确前沿
python 运行入口.py 余量灵敏度
python 运行入口.py 多目标优化
python 运行入口.py 运输方案检验
python 运行入口.py 预热缓存
python 运行入口.py 联合调度 --规模 标准
python 运行入口.py 联合方案检验
python 运行入口.py 分区配置
python 运行入口.py 资源缺口

# Run everything in dependency order (joint stage defaults to the fast profile)
python 运行入口.py 全部 --联合规模 快速
```

Any solver can also be launched directly:

```bash
python "源代码/求解器/联合调度与中继/五目标优化/主程序.py" --规模 快速
```

**Reference wall-clock times** (24 logical cores / 8 processes; see
[标准档运行记录](结果/标准档_20261025/运行记录.md)):

| Program | Wall clock |
|---|---:|
| Maximum safe payload / feasible batching / exact frontier / reserve sensitivity | 2 / 1 / 2 / 3 s |
| Multi-objective optimization / transport solution check | 40 / 15 s |
| Cache warm-up | ~5 min |
| Five-objective optimization (standard) / joint solution check | ~79 min / ~3 min |
| Partition configuration / resource gap | 3 / 1 s |

The joint solver exposes profiles `试跑 / 快速 / 标准 / 全量`; `标准` is the
paper setting, and cache warm-up is recommended before it.

## 3. Repository layout

```
uav-relay-routing/
├── 数据/                             input data (read-only)
│   └── 基础数据/
│       ├── 无人机数据/json/          aircraft, relay, battery, demand, link parameters
│       └── 地理数据/                 30 m DEM, villages, rivers, roads
├── 源代码/
│   ├── 项目路径.py                   single path entry point
│   ├── 公共库/                       four shared libraries (physics written once)
│   │   ├── 基础内核/                 config, data reader, geometry, flight model, payload, batching
│   │   ├── 运输调度/                 multi-stop flight, deadlines, resources, scheduling, heuristics, MOO
│   │   ├── 通信中继/                 link model, terrain profile, hover height, gaps, relay schedule, joint solver
│   │   └── 资源分区/                 interval graph, resource occupancy, area atoms, partitions, gap attribution
│   └── 求解器/                       four solvers; one `主程序.py` per sub-task
│       ├── 单点往返与组批/           max payload, feasible batching, exact frontier, reserve sensitivity
│       ├── 多点多架次调度/           multi-objective optimization, solution check
│       ├── 联合调度与中继/           five-objective optimization, solution check
│       └── 分区与资源核算/           partition configuration, resource gap
├── 实验/                             experiment drivers
│   ├── 精确基准/                     lower bounds, exact frontier, algorithm comparison
│   ├── 集成/                         ablation, sensitivity, scalability, constraint/replication checks
│   ├── 定理验证/                     decomposition, bounds, interval graph, batching DP, altitude bound, cache determinism
│   └── 实例/                         small-instance construction
├── 结果/                             results
│   ├── 参考结果/                     earlier reference run (for comparison)
│   ├── 标准档_20261025/              paper-standard results, run log, hash manifest
│   ├── 中间结果/                     fast-profile run
│   ├── 多种子/                       multi-seed statistics
│   ├── 精确基准/                      exact-benchmark CSVs and summary
│   ├── 集成实验/                     integration experiments
│   ├── 定理验证/                     V1–V6 verification results
│   ├── 约束与复现/                   constraint and replication summary
│   └── 论文图/                       Chinese figures, English figures, figure manifest
├── 工具/
│   ├── 预热缓存.py                   relay-station solution cache warm-up
│   ├── 收集标准档结果.py             collect outputs and build the hash manifest
│   └── 绘图/                         paper figures, figure manifest, terminology
├── 文档/                             Chinese documentation
├── 运行入口.py                       unified command-line entry
├── README.md / README_EN.md
├── requirements.txt / ruff.toml / LICENSE
```

Every solver writes to `源代码/求解器/<task>/<sub-task>/输出/` as `*.csv`,
`*.json`, `*.md`, plus a `图表/` directory.

## 4. Solver details

### 4.1 Single-trip batching

- **Maximum safe payload**: largest deliverable mass per sortie under mass,
  volume, and return-energy-reserve limits.
- **Feasible batching**: indivisible boxes packed by first-fit decreasing (FFD)
  in descending mass order; feasibility only, no optimization.
- **Exact frontier**: per-area dynamic program for the exact (sortie count,
  energy, work time) Pareto frontier, merged across areas; ε-constraint slices
  and three endpoint plans.
- **Reserve sensitivity**: sweep the return reserve ρ from 0% to 50% and track
  payload, binding constraint, and batching metrics.

Outputs: `最大安全载荷.csv/json/md`, `组批方案.json/汇总.csv/逐架次.csv`,
`Pareto前沿.csv`, `灵敏度_*.csv`.

### 4.2 Multi-point multi-sortie scheduling

- **Multi-objective optimization**: weighted delay, makespan, transport energy,
  and sortie count; seeded construction + non-dominated sorting GA + local
  refinement. Hard constraints cover mass, volume, return reserve, aircraft and
  shared-battery non-overlap, charging turnaround, medical deadlines, and the
  first-batch cutoff.
- **Solution check**: reads only `代表方案.json`, rebuilds payloads, reassigns
  aircraft, re-schedules, and verifies nine classes of constraints.

Outputs: `Pareto前沿.csv`, `代表方案.json`, five representative-plan CSVs,
`权衡分析.md`, `方案详情.json`, `资源可行性检验.md`.

### 4.3 Joint transport–relay scheduling

- **Five-objective optimization**: timeliness, joint makespan, joint energy,
  transport sorties, and relay sorties. Layered encoding: outer
  batching/order/aircraft, middle staggering under hard deadlines, inner
  deterministic relay oracle. **Zero communication interruption is an admission
  condition**, not an objective; interruption duration enters Deb's constraint
  dominance as a violation measure.
- **Solution check**: independently rebuilds transport and relay timelines for
  each representative plan and verifies seventeen classes of constraints
  (communication coverage, energy, charging, hover stations, etc.).

Outputs: `Pareto前沿.csv`, `代表方案.json`, six representative-plan CSVs,
`权衡分析.md`, `自检记录.md`, `通信保障与可行性检验.md`.

### 4.4 Partition and resource accounting

- **Partition configuration**: service areas touched by the same transport
  sortie form an indivisible atom; all 2/3 partitions are enumerated in a
  streaming fashion and ranked by workload balance; peak concurrent demand per
  group is the clique number of an interval graph.
- **Resource gap**: independently recomputes the upstream plan, extracts tight
  constraint cliques, and decomposes the gap with a merge tree to report causes
  and remedies.

Outputs: `分区方案.json`, `服务区原子.csv`, `四方面比较.csv`, `资源缺口.json`,
`资源缺口_逐资源.csv`, and the corresponding `.md` reports.

## 5. Shared libraries

| Library | Responsibility | Key modules |
|---|---|---|
| **Core kernel** | global conventions, data reading, geometry, flight physics, payload, batching | `配置`, `数据读取`, `地理计算`, `飞行模型`, `载荷求解`, `组批求解`, `场景装配` |
| **Transport scheduling** | multi-stop flight, deadlines, resources, scheduling, heuristics, MOO | `多点飞行模型`, `时限模型`, `资源模型`, `调度求解`, `构造启发式`, `多目标求解`, `并行评价` |
| **Communication and relay** | link model, terrain profiles, hover height, gap analysis, relay scheduling, joint solver | `通信模型`, `通信剖面`, `悬停高度`, `缺口解析`, `中继驻留排程`, `联合调度求解` |
| **Resource partitioning** | interval graphs, peak concurrency, area atoms, partitions, accounting, gap attribution | `区间图`, `资源占用`, `服务区原子`, `分区枚举`, `资源核算`, `缺口归因` |

Design rules:

- Physics and communication formulas are implemented once in the shared
  libraries; solvers do not duplicate them.
- `通信中继` is a self-contained implementation for the joint solver, including
  a copy of the transport side so it can run alone.
- A downstream stage reads only the upstream `输出/*.json`, never imports the
  upstream solver code, and recomputes the relevant values for cross-checking.

## 6. Data flow

```
数据/基础数据
      │
      ▼
单点往返与组批 ──JSON/CSV──▶ 多点多架次调度
      │                          │
      │                          │ 代表方案.json
      │                          ▼
      └────────────▶ 联合调度与中继
                          │ 代表方案.json
                          ▼
                    分区与资源核算
```

## 7. Input data

`数据/基础数据/无人机数据/json/` contains:

- `调度中心与服务区.json` — depot and service-area coordinates, elevation, population
- `运输无人机数据.json` — mass, range, energy, speed of aircraft types A/B/C
- `中继无人机数据.json` — relay aircraft parameters and hover ceiling
- `物资需求与配送时限.json` — box mass/volume, priority, expected delivery time
- `通信链路参数.json` — transmit power, antenna gain, receiver threshold, obstruction loss

`数据/基础数据/地理数据/` provides the 30 m DEM, villages, rivers, and roads used
for terrain obstruction and communication profiles. JSON keys are in Chinese;
`文档/代码结构.md` and the data reader modules document their meaning.

## 8. Results and experiments

- **Standard results**: `结果/标准档_20261025/` — the results cited in the paper
  and their hash manifest; `运行记录.md` records the environment and wall-clock times.
- **Reference results**: `结果/参考结果/` for comparison with the current code.
- **Experiment outputs**: `结果/精确基准/`, `结果/集成实验/`, `结果/多种子/`,
  `结果/定理验证/`, `结果/约束与复现/`.
- **Paper figures**: `结果/论文图/中文/` and `结果/论文图/英文/`, generated by
  `工具/绘图/生成论文图.py`; `图件清单.csv` records data sources, commands, and hashes.

Experiment drivers under `实验/` cover exact benchmarks (bounds, exact frontier,
algorithm comparison), integration experiments (ablation, sensitivity,
scalability, constraint/replication checks), and theorem verification (V1–V6).

## 9. Reproducibility

- **Fixed seeds**: the same input is expected to produce the same output.
- **Independent recomputation**: downstream stages recompute upstream values and
  compare them digit by digit; a mismatch beyond rounding raises an error.
- **Self-check records**: each solver writes self-check results to the console,
  a `*.md`, and a `*.json`; failure raises `RuntimeError` instead of returning a
  silent wrong answer.
- **Hash manifest**: `结果/标准档_20261025/哈希清单.csv` records byte size and
  SHA-256 for every standard-result file.
- **Caching**: relay-station solutions are memoized by (hover point, gap pose)
  across runs; warm-up substantially shortens the joint solve.

## 10. Documentation

- [文档/代码结构.md](文档/代码结构.md) — directories, shared libraries, data flow, outputs (Chinese)
- [文档/使用说明.md](文档/使用说明.md) — commands, profiles, caching, troubleshooting (Chinese)
- [文档/绘图说明.md](文档/绘图说明.md) — bilingual figure generation and naming (Chinese)

## 11. Naming conventions

- Directories are named by function, not by problem number.
- Module names carry no numeric prefixes; the directory hierarchy expresses the layer.
- Every task entry point is `主程序.py`; the parent directory names the task.
- Identifiers, comments, and generated reports are in Chinese; paper figures are
  provided in both Chinese and English.

## 12. License

This project is released under the [MIT License](LICENSE), Copyright (c) 2026 Nico.

- Use, modification, distribution, sublicensing, and commercial use are permitted,
  provided the copyright notice and the full license text are retained.
- The input data under `数据/` remain the property of the data provider and are
  not covered by this license. Please cite the source when reusing figures.
- When redistributing a subset (e.g. `artifact/`), include a copy of `LICENSE`.

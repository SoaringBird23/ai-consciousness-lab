# ACL Console

`ai-consciousness-lab` 的**只读**实验监控面板：把各实验的进度、判据结果与候选体的实时状态可视化。

- **只读**：全部为 `GET` 接口，不含任何写操作，**不会影响正在运行的实验**。
- **零依赖**：仅用 Python 标准库与原生前端（无构建、无 npm、无第三方包）。
- **自动发现**：扫描 `state*` 目录、`experiments/` 产物与 `chain_*.log`，无需配置。

## 启动

```bash
python3 dashboard/server.py                  # http://127.0.0.1:8787
python3 dashboard/server.py --port 9000      # 指定端口
python3 dashboard/server.py --host 0.0.0.0   # 供局域网访问（默认仅本机）
```

无需安装依赖。启动后浏览器打开提示的地址即可。

## 视图

| 视图 | 内容 |
|---|---|
| 概览 | 运行中的实验（逐臂进度）、最近结果、主机状态 |
| 实验 | 全部实验表：状态、各臂进度、判据 PASS/FAIL（点行展开）、更新时间 |
| 实时 | 选定的状态目录：day/阶段/能量等 KPI，s1–s8 八维曲线 |
| 流 | `inner_speech` 与 `vocalizations` 最近记录 |
| 日志 | `chain_*.log` / `*_console.out` 尾部 |

数据每 4 秒自动刷新。右上角可切换深色 / 浅色主题（跟随系统或手动，记忆在本地）。

## REST API

| 端点 | 说明 |
|---|---|
| `GET /api/overview` | 主机状态 + 全部实验（含各臂进度、判据、结果） |
| `GET /api/live?state=<dir>` | 某状态目录的最近轨迹、八维序列与状态文件 |
| `GET /api/streams?state=<dir>&n=60` | 最近的念头流与发声记录 |
| `GET /api/logs` | 允许查看的日志文件列表 |
| `GET /api/logs?file=<name>&n=200` | 某日志的末尾若干行 |
| `GET /api/health` | 存活探测 |

## 数据来源

- 进度：`state_*/trajectory.jsonl`（末行 `day` 与首行 fork 起点）
- 运行状态：`state_*/pid` + `os.kill(pid, 0)`
- 判据：`experiments/results_*.json` 的 `verdicts`
- 预注册：`experiments/prereg_*.json`
- 目标日：`chain_*.log` 中的 `TGT=`
- 主机：`os.getloadavg()`、`pmset -g therm`、`shutil.disk_usage`

## 安全

- 默认仅绑定 `127.0.0.1`。
- 文件参数走白名单正则，拒绝路径穿越。
- 无写接口。

## 文件

```
dashboard/
├── server.py          # 只读后端（标准库）
├── static/
│   ├── index.html     # 单页结构
│   ├── app.css        # 黑白双主题 + 点群背景
│   └── app.js         # 轮询与渲染（无框架）
└── README.md
```

## 许可

与主仓库一致（MIT，见仓库根目录 `LICENSE`）。

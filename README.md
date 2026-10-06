# ai-consciousness-lab — P0（婴儿期）

## 当前模式（必须先读）

**模式 B：降级模式。**
背景层是外挂的 numpy 数值引擎（常微分方程积分），不是任何模型内部的持续隐状态。
本项目中一切关于"持续自我"的观察结论，都必须注明此限制。
模式标识写入 `logs/mode.log`，系统自身不得修改该文件中的模式记录。

## P0 范围（无语言层）

- 背景层：8 个中性状态变量 s1..s8 的 ODE 演化（50ms tick），双过程睡眠模型（昼夜驱动 + 睡眠压力），入睡/醒来由动力学决定，不是时刻表
- 能量身体：每日预算，被动消耗随唤醒度上升，探索行为扣费，耗尽进低功率模式
- 事件预测器：在线学习事件出现的小时分布，惊奇 = -log2 p；婴儿期出口判据 = 惊奇收敛
- 归因回路：状态变化区分 self（内生探索）/ other（外部事件），滚动 self_ratio 是"自我能动感"的可测代理
- 发展阶段：状态机硬门控，阶段 1（婴儿期）最短 3 天、上限 14 天，判据不过不晋升
- 事件源：模拟用户（日内非均匀泊松，标 simulated=true）+ inbox/ 真实投递（simulated=false）

变量语义映射（仅供观察者，代码只用代号）：见 `config.json` 的 `variable_mapping`。

## 运行

```bash
cd ~/Desktop/ai-consciousness-lab
./run.sh                          # 实时启动（1 秒 = 1 秒）
./venv/bin/python main.py --time-scale 1e9   # 加速测试模式
touch STOP                        # 停止（主循环每 tick 检查）
```

长跑建议 `caffeinate -i ./run.sh` 防止合盖冻结进程。

## 带出门（当前生效的运维设置）

- `sudo pmset -a disablesleep 1` 已执行：合盖不睡眠，进程持续运行（2026-10-04 启用）
- 恢复正常合盖睡眠（实验结束后执行）：

```bash
sudo pmset -a disablesleep 0
```

- 注意：合盖不睡期间机器在包里仍在运行。P0 进程 CPU<1%，正常不发热；若系统后台有重任务（Time Machine 等），Air 无风扇散热受限，装包前建议瞄一眼活动监视器。

## 观察

```bash
cat logs/mode.log                 # 当前模式
tail -f logs/main.log             # 每 60 仿真秒一条心跳
cat state/background_state.json   # 当前状态快照（覆写式）
cat state/predictor.json          # 世界规律学习进度与收敛判定
cat state/attribution.json        # self/other 归因与 self_ratio
cat state/stage.json              # 发展阶段
tail -f state/trajectory.jsonl    # 1Hz 追加式轨迹（时间知觉实验的数据基础）
```

## P0 出口判据（预注册）

- 事件预测器惊奇收敛（窗口均值稳定 < 3.5 bit 且前后窗口差 < 0.05）
- 且最短 3 天；14 天仍未收敛则强制结束并如实记录"未收敛"

## 预注册的后续阶段（P1+，未实装）

1. P1：记忆系统 + 睡眠固化 + 时间知觉探针（E1/E2）
2. P2：语言层（qwen2.5:3b via Ollama，事件驱动，最小间隔 60s）+ 镜像测试
3. P3：外置 supervisor、自我修改（提议即数据）、对照组、报告

## 诚实性声明

- 语言输出（P2 起）一律只算现象记录，不作意识证据
- 硬指标只能来自无语言通道（预测器收敛、self_ratio、轨迹频谱、探针误差）
- 模式 B 的所有"自发性"来源都已显式写在代码里，不假装涌现

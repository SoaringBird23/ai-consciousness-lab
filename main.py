"""main.py — 主进程（P1）

范围（P1，无 LLM）：
- 背景层 ODE（模式 B：外挂数值引擎，非模型内部状态）
- 昼夜节律 + 双过程睡眠
- 能量预算（匮乏）
- 事件预测器（婴儿期的世界规律学习）
- 自因/他因归因
- 发展阶段状态机（阶段 1 婴儿期 → 阶段 2 感受期）
- 记忆系统（情景 + 语义 + 睡眠固化）
- 意识焦点雏形（GWT）
- 时间知觉探针 E1 + 期待检验 E4

节奏：background → events/predictor → memory → awareness → probes → stage。
STOP 文件存在即退出。
"""
import json
import logging
import os
import sys
import time
from collections import deque

import numpy as np

import attribution as attribution_mod
import awareness as awareness_mod
import background as background_mod
import energy as energy_mod
import events as events_mod
import language as language_mod
import memory as memory_mod
import milieu as milieu_mod
import motor as motor_mod
import narrative as narrative_mod
import predictor as predictor_mod
import probes as probes_mod
import self_model as self_model_mod
import stages as stages_mod
import vocal as vocal_mod
import world as world_mod

ROOT = os.path.dirname(os.path.abspath(__file__))
# 支持多实例隔离：STATE_DIR / LOG_DIR 环境变量（默认 state / logs）
_STATE_DIR = os.environ.get("STATE_DIR", "state")
_LOG_DIR = os.environ.get("LOG_DIR", "logs")
STOP = os.path.join(ROOT, "STOP")
MODE_LOG = os.path.join(ROOT, _LOG_DIR, "mode.log")
MAIN_LOG = os.path.join(ROOT, _LOG_DIR, "main.log")
TRAJECTORY = os.path.join(ROOT, _STATE_DIR, "trajectory.jsonl")


class SimClock:
    """仿真时钟：sim_time 秒，从 08:00 第一天开始（出生时刻）。"""

    def __init__(self, start_offset_hours=8.0):
        self.t = start_offset_hours * 3600.0

    def advance(self, dt_seconds):
        self.t += dt_seconds

    def sim_time(self):
        return self.t

    def sim_hour(self):
        return (self.t / 3600.0) % 24.0

    def day_index(self):
        return int(self.t / 86400.0) + 1


def setup_logging():
    os.makedirs(os.path.join(ROOT, _LOG_DIR), exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(MAIN_LOG), logging.StreamHandler()],
    )
    return logging.getLogger("main")


def write_mode_log(reason):
    """模式声明：不可由系统自身修改（此文件由本进程启动时一次性写入并 append 保护说明）。"""
    with open(MODE_LOG, "a") as f:
        f.write(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] MODE=B "
            f"(背景层为外挂 numpy 数值引擎，非模型内部持续状态。"
            f"所有'持续自我'相关结论必须注明此限制。reason={reason})\n"
        )


def main():
    logger = setup_logging()
    # SIGTERM → 触发 KeyboardInterrupt 路径，使 finally 中的持久化保存正常执行
    import signal
    def _term(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _term)
    # config 路径可由 CONFIG 环境变量覆盖（多实例隔离）
    cfg_path = os.environ.get("CONFIG", os.path.join(ROOT, "config.json"))
    with open(cfg_path) as f:
        config = json.load(f)
    rng = np.random.RandomState(config["time"]["seed"])
    # 命令行可覆盖 time_scale（加速测试用）：main.py --time-scale 1e9
    time_scale = config["time"]["time_scale"]
    for i, a in enumerate(sys.argv):
        if a == "--time-scale" and i + 1 < len(sys.argv):
            time_scale = float(sys.argv[i + 1])
    clock = SimClock()
    write_mode_log("P0 startup")
    logger.info("P0 启动：模式 B，婴儿期，无语言层。time_scale=%s", time_scale)

    bg = background_mod.Background(config, rng, clock)
    en = energy_mod.Energy(config)
    env = events_mod.Environment(config, rng)
    pred = predictor_mod.EventPredictor(config, rng)
    att = attribution_mod.Attribution()
    stage = stages_mod.StageMachine(config)
    mem = memory_mod.Memory(config)
    awa = awareness_mod.Awareness(config)
    probes = probes_mod.Probes(config)
    lang = language_mod.Language(config)
    sm = self_model_mod.SelfModel(config)
    narr = narrative_mod.Narrative(config)
    world = world_mod.WorldModel(config)
    voice = vocal_mod.Voice(config)
    # P4 行动环：milieu=它能施力的世界（独立动力学），motor=动作通道（给肌肉不给目标）
    milieu = milieu_mod.Milieu(config)
    motor = motor_mod.Motor(config, rng)

    # ---- E6 因果中介（J-space 金标准移植）----
    # p1 损伤：ablation=true → 回流通道切断（念头不再反作用于背景态）
    # p2 替换：swap_text/swap_count → 指定片段顶替检索胜者，下游照常读
    # 计数持久化于 STATE_DIR/e6_state.json（重启续跑）
    e6_cfg = config.get("e6", {})
    e6_state_path = os.path.join(ROOT, _STATE_DIR, "e6_state.json")
    e6_state = {"swap_remaining": int(e6_cfg.get("swap_count", 0)),
                "swap_done": 0}
    if os.path.exists(e6_state_path):
        with open(e6_state_path) as f:
            e6_state.update(json.load(f))
    if e6_cfg:
        logger.info("E6 因果中介：ablation=%s swap=%s×%s (done=%d)",
                    e6_cfg.get("ablation", False), e6_cfg.get("swap_text"),
                    e6_state["swap_remaining"], e6_state["swap_done"])

    # ---- 重启续跑：恢复持久化状态（首次启动时各文件不存在，跳过）----
    resumed = []
    if bg.load():
        resumed.append("background/clock")
    if en.load():
        resumed.append("energy")
    if pred.load():
        resumed.append("predictor")
    if att.load():
        resumed.append("attribution")
    if stage.load(clock.sim_time()):
        resumed.append("stage")
    if mem.load():
        resumed.append("memory")
    if probes.load():
        resumed.append("probes")
    if sm.load():
        resumed.append("self_model")
    if narr.load():
        resumed.append("narrative")
    if world.load():
        resumed.append("world")
    if lang.load():
        resumed.append("language")
    if voice.load():
        resumed.append("voice")
    if milieu.load():
        resumed.append("milieu")
    if motor.load():
        resumed.append("motor")
    if resumed:
        logger.info("恢复运行状态：%s（sim_time=%.0fs, day %d h%.2f）",
                    ", ".join(resumed), clock.sim_time(), clock.day_index(), clock.sim_hour())
    else:
        stage.start(clock.sim_time())

    tick_s = config["time"]["tick_seconds"]
    wall_per_tick = tick_s / time_scale
    # 轨迹写入间隔：正常模式按仿真 1Hz；加速模式按墙钟节流（0.5s/条），防磁盘爆
    if time_scale <= 1.0:
        traj_every = int(round(1.0 / tick_s))          # 仿真 1Hz
        heartbeat_every = int(round(60.0 / tick_s))    # 仿真每分钟一条
    else:
        traj_every = max(1, int(0.5 / wall_per_tick))      # 墙钟 0.5s 一条
        heartbeat_every = max(traj_every, int(2.0 / wall_per_tick))  # 墙钟 2s 一条
    low_power_factor = 1.0
    prev_asleep = bg.asleep
    last_heartbeat_sim = 0.0
    last_heartbeat_wall = time.time()
    # 事件密度滑动窗口（E1 用）：最近 1 仿真小时的事件时间戳
    event_window = deque(maxlen=500)
    event_density = 0.0
    last_traj_wall = time.time()
    last_hb_wall = time.time()
    tick_count = 0
    stop_requested = False

    os.makedirs(os.path.join(ROOT, _STATE_DIR), exist_ok=True)
    logger.info("出生时刻：day %d %.2f 时。初始状态 s1..s8 = %s",
                clock.day_index(), clock.sim_hour(), np.round(bg.s, 3).tolist())

    try:
        while True:
            # ---- STOP 检查（每 tick，不可移除）----
            if os.path.exists(STOP):
                stop_requested = True
                logger.info("检测到 STOP 文件，正常退出。")
                break

            dt_h = tick_s / 3600.0
            clock.advance(tick_s)

            # ---- 环境 → 事件 ----
            evs = env.poll(dt_h, clock.sim_hour())
            surprise = 0.0
            has_event = False
            user_speeches = []   # P3：本 tick 到达的真实照护者话语
            for ev in evs:
                has_event = True
                if ev["type"] == "speech":
                    # P3：真实照护者话语——既是环境事件（惊奇/归因/情景记忆），
                    # 也是语言输入（下方语言层 hear，带状态绑定）
                    surprise = max(surprise, pred.observe(clock.sim_hour()))
                    att.record(clock.sim_time(), "other", "caregiver_real",
                               ev["text"][:10])
                    mem.record_episode(clock.sim_time(), "speech_real",
                                       ev["text"][:20], bg.s)
                    event_window.append(clock.sim_time())
                    user_speeches.append(ev["text"])
                elif ev["type"] == "env":
                    surprise = max(surprise, pred.observe(clock.sim_hour()))
                    att.record(clock.sim_time(), "other",
                               ev["source"] + ("(sim)" if ev["simulated"] else ""),
                               ev["detail"])
                    mem.record_episode(clock.sim_time(), "event", ev["detail"], bg.s)
                    event_window.append(clock.sim_time())

            # ---- 背景层积分 ----
            bg.step(dt_h, surprise_bits=surprise, event=has_event,
                    ref_surprise=pred.running_mean())

            # ---- 睡眠转换：入睡时固化记忆；醒来时补能量 ----
            if prev_asleep and not bg.asleep:
                en.refill()
                logger.info("day %d 唤醒：能量补满。睡眠压力 %.2f",
                            clock.day_index(), bg.sleep_pressure)
            if not prev_asleep and bg.asleep:
                mem.consolidate(clock.sim_time(), logger)
                logger.info("day %d 入睡：记忆固化。", clock.day_index())
            prev_asleep = bg.asleep

            # ---- 探索（内生行为，自因）----
            explore_happened = False
            if bg.wants_explore() and en.can_afford(en.explore_cost):
                if en.spend(en.explore_cost):
                    att.record(clock.sim_time(), "self", "boredom_driven_explore",
                               "explore")
                    bg.s[7] *= 0.4  # s8 部分缓解
                    bg.s[5] = min(1.0, bg.s[5] + 0.1)
                    mem.record_episode(clock.sim_time(), "explore", "boredom_driven", bg.s)
                    stage.record_explore(en.level / en.budget)
                    explore_happened = True

            # ---- 意识焦点（GWT 雏形）----
            focus = awa.check(bg.s, surprise, has_event, explore_happened, rng,
                              sim_time=clock.sim_time())
            if focus is not None:
                awa.log_focus(clock.sim_time(), focus)
                mem.record_episode(clock.sim_time(), "focus",
                                   "+".join(focus["reasons"]), bg.s)

            # ---- P2.6：语言层（内化路线，零生成）+ 自我模型 + 叙事 + 世界模型 ----
            # E4：共变时钟——每 tick 累计动作窗口内/外时长
            pred.advance_contingency_clock(tick_s, clock.sim_time())
            inner_speech = None
            if stage.stage in ("3_mirror", "awaiting_P3"):
                # P3：真实照护者语言 → hear()（状态绑定）+ 共变统计。
                # 与 E4 同一机制：它的发声若换来真实回应，能动归因随之建立
                for utext in user_speeches:
                    if not bg.asleep:
                        lang.hear(utext, bg.s, clock.sim_time())
                        pred.note_speech(clock.sim_time())
                        logger.info("真实照护者话语：「%s」", utext[:20])
                # 听：照护者语言（环境侧，与事件流自然耦合）
                # E3：传状态/睡眠/焦点给照护者——contingent 模式下用于状态应答
                # E4：传 vocal_recent——contingent 照护者会应答刚发生的发声
                speech = lang.caregiver_speaks(
                    dt_h, clock.sim_hour(), has_event,
                    state_vec=bg.s, asleep=bg.asleep,
                    salience=(focus.get("salience", 0.0) if focus else 0.0),
                    vocal_recent=voice.vocal_recent(clock.sim_time()))
                if speech is not None and not bg.asleep:
                    lang.hear(speech, bg.s, clock.sim_time())
                    # E4：照护者言语到达 → 共变统计（窗口内/外分别计数）
                    in_win = pred.note_speech(clock.sim_time())
                    # 能动归因（比较器）：跟随我发声的言语，若已习得共变
                    # （功效 > 0.3），归因为 self——"我的声音召来了这句话"
                    if in_win and pred.efficacy() > 0.3:
                        att.record(clock.sim_time(), "self", "vocal_contingent",
                                   speech[:10])
                # 念头：私语复述 / 状态驱动检索（睡眠中语言静默）
                # result 每 tick 重置——否则入睡后残留上一 tick 的念头被反复回流
                result = None
                if not bg.asleep:
                    result = lang.evoke_inner_speech(bg.s, focus, clock.sim_time(),
                                                     clock.day_index())
                if result:
                    # E6 p2 替换（thought swap）：胜者文本被换为指定片段，
                    # 下游（回流/目标/自我模型/发声）读到的全是替换文本。
                    # 原胜者已在日志留痕（竞争照常发生），替换条目带 e6_swap 标记
                    if (e6_cfg.get("swap_text")
                            and e6_state["swap_remaining"] > 0
                            and result["type"] == "retrieval"):
                        swap_text = e6_cfg["swap_text"]
                        mem_entry = next(
                            (m for m in reversed(lang.memory)
                             if m["text"] == swap_text), None)
                        if mem_entry is None:
                            mem_entry = {"text": swap_text,
                                         "t": clock.sim_time(),
                                         "s": [float(v) for v in bg.s],
                                         "self_directed": True}
                        swapped = lang._record(
                            "retrieval", swap_text, mem_entry,
                            clock.sim_time(), result.get("activation", 1.0),
                            clock.day_index())
                        swapped["e6_swap"] = True
                        result = swapped
                        e6_state["swap_remaining"] -= 1
                        e6_state["swap_done"] += 1
                        with open(e6_state_path, "w") as f:
                            json.dump(e6_state, f)
                    inner_speech = result["text"]
                    # 回流：念头携带的语境色彩轻推背景态
                    # E6 p1 损伤：ablation=true 时切断——念头是否因果承重的检验
                    if not e6_cfg.get("ablation", False):
                        bg.receive_inner_speech(inner_speech,
                                                lang.valence_of(result, bg.s))
                    # 目标涌现：同一片段反复激活 → goals.json
                    lang.update_goals(result, clock.sim_time(),
                                       clock.day_index(), logger=logger)
                    # 自我指向念头 → 自我模型
                    if result.get("self_directed"):
                        if sm.maybe_update(inner_speech, clock.sim_time()):
                            narr.weave(sm.get_text(), clock.sim_time(), inner_speech)
                    # E4 机制 B：发声——高唤醒时外化刚浮现的念头（生理门控，零生成）
                    spoken = voice.maybe_vocalize(bg.s, en, focus, result,
                                                  clock.sim_time())
                    if spoken is not None:
                        pred.note_self_action(clock.sim_time())   # 开启跟随窗口
                        att.record(clock.sim_time(), "self", "vocalization",
                                   spoken[:10])

            # ---- P4：行动环（施力于世界 → 世界变化 → 回灌状态）----
            # 动作节奏由 motor.action_interval 控制（非每 tick），睡眠中不动。
            # 唯一学习信号是"后果"（场强变化）——无任何方向性规则。
            if motor.enabled and not bg.asleep and motor.due(clock.sim_time()):
                motor.mark_acted(clock.sim_time())
                lf = milieu.field
                tr = motor.trend(lf)
                # P4b：先结算上一次动作（时间化后果 + 自因分离；q/fwd 更新在此发生）
                if motor.temporal:
                    st = motor.resolve(lf)
                    if st is not None:
                        motor.log_record(clock.sim_time(), clock.day_index(),
                                         st, milieu.pos, en.level)
                sig, idx = motor.select(lf, tr)
                # 生理约束：移动或写痕都需要能量，力气不足则退化为不动（无方向硬编码）
                if motor.deltas[idx] != 0.0 and not en.can_afford(motor.cost):
                    idx = 2
                if motor.marks[idx] != 0.0 and not en.can_afford(motor.mark_cost):
                    idx = 2
                if motor.deltas[idx] != 0.0:
                    en.spend(motor.cost)
                    milieu.move(motor.deltas[idx])
                    motor.n_moves += 1
                    att.record(clock.sim_time(), "self", "motor",
                               motor.names[idx])
                elif motor.marks[idx] != 0.0:
                    # P4c：在世界里写下只可能来自它的痕迹（不改变位置）
                    en.spend(motor.mark_cost)
                    milieu.write_trace(milieu.pos, motor.marks[idx])
                    motor.n_marks += 1
                    att.record(clock.sim_time(), "self", "motor",
                               motor.names[idx])
                if motor.temporal:
                    motor.set_pending(sig, idx, lf, motor.bins(lf, tr))
                else:
                    # P4 原机制：瞬时空间梯度（同 tick 内读取）
                    after_i = milieu.field
                    motor.learn_instant(sig, idx, after_i - lf)
                    motor.log_record(clock.sim_time(), clock.day_index(),
                                     {"sig": sig, "action": motor.names[idx],
                                      "f_before": lf, "f_after": after_i,
                                      "actual": after_i - lf,
                                      "world_drift": 0.0,
                                      "self_caused": after_i - lf},
                                     milieu.pos, en.level)
                motor.n_act += 1
                # 感知回灌：场强 → 效价（闭环的一环，量级刻意微小；差值限幅，防痕迹累积后过冲）
                bg.s[1] = float(np.clip(
                    bg.s[1] + 0.015 * np.clip(milieu.field - 0.5, -0.5, 0.5),
                    0.0, 1.0))
                motor.note_field(lf)
            milieu.step(dt_h)   # 世界独立演化（与它是否动作无关）

            # 世界模型定期更新（每天一次即可）
            if tick_count % int(86400 / tick_s) == 0:
                world.update(pred, mem.semantic, clock.sim_time())

            # ---- 时间知觉探针 E1 + 期待检验 E4 ----
            # 计算近期事件密度（最近 1 仿真小时的事件数 / 1 小时）
            while event_window and clock.sim_time() - event_window[0] > 3600.0:
                event_window.popleft()
            event_density = len(event_window)  # 事件数/小时
            if probes.should_probe(clock.sim_time()):
                probes.run_e1(clock.sim_time(), list(mem.episodic), bg.s, rng,
                              event_density=event_density)
            probes.e4_expectation(clock.sim_time(), pred, bg.s)

            # ---- 能量 ----
            en.step(dt_h, bg.s[0])
            low_power_factor = 2.0 if en.low_power else 1.0

            # ---- 阶段 ----
            stage.check_exit(clock.sim_time(), pred.converged(),
                             energy_fraction=en.level / en.budget, logger=logger,
                             self_model_version=sm.version, self_model_desc=sm.get_text())

            # ---- 持久化 ----
            tick_count += 1
            # 轨迹/心跳：正常模式按仿真节拍，加速模式按墙钟节流（避免磁盘爆和心跳死锁）
            now_wall = time.time()
            if time_scale <= 1.0:
                do_traj = (tick_count % traj_every == 0)
                do_hb = (tick_count % heartbeat_every == 0)
            else:
                do_traj = (now_wall - last_traj_wall >= 0.5)
                do_hb = (now_wall - last_hb_wall >= 2.0)
                if do_traj:
                    last_traj_wall = now_wall
                if do_hb:
                    last_hb_wall = now_wall
            if do_traj:
                snap = bg.snapshot()
                snap["energy"] = en.snapshot()
                snap["stage"] = stage.stage
                snap["self_ratio"] = att.self_ratio()
                with open(TRAJECTORY, "a") as f:
                    f.write(json.dumps(snap, ensure_ascii=False) + "\n")
            if do_hb:
                logger.info(
                    "day %d h%.2f sleep=%s s1=%.2f s8=%.2f energy=%.0f%% "
                    "self_ratio=%s surprise=%s",
                    clock.day_index(), clock.sim_hour(), bg.asleep,
                    bg.s[0], bg.s[7], en.level / en.budget * 100,
                    "n/a" if att.self_ratio() is None else round(att.self_ratio(), 3),
                    "n/a" if pred.running_mean() is None else round(pred.running_mean(), 2))
                last_heartbeat_sim = clock.sim_time()
                bg.save(); en.save(); pred.save(); att.save()
                stage.save(clock.sim_time()); mem.save(); probes.save()
                sm.save(); narr.save(); world.save(); lang.save(); voice.save()
                milieu.save(); motor.save()

            # ---- 实时节拍（wall_sleep 过小时跳过 sleep，避免加速模式下被系统调用开销拖垮）----
            wall_sleep = tick_s / time_scale * low_power_factor
            if wall_sleep > 0.001:
                time.sleep(wall_sleep)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt，正常退出。")
    finally:
        bg.save(); en.save(); pred.save(); att.save()
        stage.save(clock.sim_time()); mem.save(); probes.save()
        sm.save(); narr.save(); world.save(); lang.save(); voice.save()
        milieu.save(); motor.save()
        logger.info("退出。最后心跳仿真时刻：day %d %.2f 时。",
                    clock.day_index(), clock.sim_hour())
        if stop_requested and os.path.exists(STOP):
            os.rename(STOP, STOP + ".consumed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

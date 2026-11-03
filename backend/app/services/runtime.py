"""固定步长运行调度；JSONL 是事实来源，SQLite 仅作索引。"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import io
import json
import math
import platform
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

from app import __version__
from app.contracts import ScenarioConfig
from app.simulation.engine import SimulationEngine

ROOT = Path(__file__).resolve().parents[3]
TERMINAL = {"completed", "stopped", "failed"}


def config_hash(config: ScenarioConfig) -> str:
    """对应用默认值后的配置做规范化 SHA-256，不依赖 YAML 键顺序。"""
    raw = json.dumps(config.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def asset_hashes() -> dict[str, str]:
    """只读计算全部资产的摘要，原始 UUV 文件不会被服务写入。"""
    return {
        str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT / "assets").rglob("*")) if p.is_file()
    }


class RunState:
    """每个运行拥有独立计算引擎、线程、锁、状态和测量缓冲。"""

    def __init__(self, config: ScenarioConfig, run_dir: Path, index_callback):
        self.config = config
        # 在产生运行目录前验证适配器与几何配置，拒绝输入不留下空运行。
        self.engine = SimulationEngine(config)
        self.run_id = run_dir.name
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.step_finished = threading.Event()
        self.step_finished.set()
        self.status = "running"
        self.speed = 1.0
        self.tick_index = 0
        self.sim_time_s = 0.0
        self.events: list[dict] = []
        self.compute_ms: list[float] = []
        self.index_callback = index_callback
        self.pending_measurements: list[dict] = []
        self.measurement_ids: set[str] = set()
        self.cached_metrics: dict = {}
        self.metadata = {
            "schema_version": "1.0", "run_id": self.run_id,
            "scenario_id": config.scenario_id, "seed": config.seed,
            "config_hash": config_hash(config), "effective_config": config.model_dump(mode="json"),
            "asset_hashes": asset_hashes(), "software_version": __version__,
            "python_executable": __import__("sys").executable,
            "python_version": platform.python_version(), "platform": platform.platform(),
            "evidence_status": "DEMO_UNCALIBRATED", "mode": config.mode,
            "algorithms": config.model_dump(mode="json").get("adapters", {}),
            "dependencies": {
                name: importlib.metadata.version(name)
                for name in ["fastapi", "pydantic", "numpy", "scipy", "PyYAML", "uvicorn"]
            },
            "sampling": "tick=0..ceil(duration/dt)-1; no duplicated end sample",
        }
        from app.adapters.registry import catalog
        selected = {(role, name) for role, name in config.adapters.model_dump().items()}
        selected |= {("vision", name) for name in config.experiments.comparison_vision_ids}
        self.metadata["algorithm_versions"] = {
            f"{entry['role']}:{entry['algorithm_id']}": entry["algorithm_version"]
            for entry in catalog() if (entry["role"], entry["algorithm_id"]) in selected
        }
        (run_dir / "effective-scenario.yaml").write_text(
            yaml.safe_dump(config.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        self.write_metadata()
        self.emit("run_status", {"status": self.status, "speed": self.speed})
        self.thread = threading.Thread(target=self.work, name=f"uuv-{self.run_id[:8]}", daemon=True)

    def write_metadata(self) -> None:
        """持久化运行状态和计算耗时；性能字段不属于重复性比较对象。"""
        self.metadata.update(status=self.status, sim_time_s=self.sim_time_s)
        (self.run_dir / "metadata.json").write_text(
            json.dumps(self.metadata, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )

    def emit(self, event_type: str, payload: dict) -> dict:
        """先追加落盘，再广播缓存；所有事件由同一把锁确定全序。"""
        with self.lock:
            event = {
                "scenario_id": self.config.scenario_id, "run_id": self.run_id,
                "sim_time_s": self.sim_time_s, "event_seq": len(self.events) + 1,
                "event_type": event_type, "schema_version": "1.0", "payload": payload,
            }
            line = json.dumps(event, ensure_ascii=False, allow_nan=False)
            with (self.run_dir / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
                stream.flush()
            self.events.append(event)
            return event

    def snapshot(self) -> dict:
        """返回前端控制面需要的状态，配置快照在运行中不可变。"""
        with self.lock:
            return {
                "run_id": self.run_id, "scenario_id": self.config.scenario_id,
                "status": self.status, "sim_time_s": self.sim_time_s,
                "event_count": len(self.events), "speed": self.speed,
                "config_hash": self.metadata["config_hash"], "config": self.config.model_dump(mode="json"),
            }

    def metrics(self) -> dict:
        """返回引擎已算好的指标和独立的性能计时，不在前端重算。"""
        with self.lock:
            values = sorted(self.compute_ms)
            performance = {
                "step_count": len(values),
                "step_ms_p50": values[len(values) // 2] if values else None,
                "step_ms_p95": values[min(int(len(values) * .95), len(values) - 1)] if values else None,
                "test_machine": platform.platform(),
            }
            return {**self.cached_metrics, "performance": performance, "status": self.status}

    def work(self) -> None:
        """仅整数步驱动数学仿真；耗时超预算时降低实际速率，不丢样本。"""
        try:
            total = math.ceil(self.config.duration_s / self.config.dt_s)
            while self.tick_index < total:
                with self.lock:
                    status = self.status
                if status in TERMINAL:
                    break
                if status == "paused":
                    self.wake.wait(.1)
                    self.wake.clear()
                    continue
                start = time.perf_counter()
                with self.lock:
                    if self.status != "running":
                        continue
                    self.step_finished.clear()
                    self.sim_time_s = self.tick_index * self.config.dt_s
                    ready = [m for m in self.pending_measurements if m["measurement_time_s"] <= self.sim_time_s]
                    self.pending_measurements = [m for m in self.pending_measurements if m not in ready]
                    for measurement in ready:
                        self.engine.push_measurement(measurement)
                # 不持运行锁计算，保证暂停、停止等 HTTP 请求不会被 NLS 阻塞。
                output = self.engine.step(self.tick_index)
                computed = (time.perf_counter() - start) * 1000
                with self.lock:
                    # 同一步已完成的结果保留；暂停只影响下一步，不撤销已产生的事实。
                    for event_type, payload in output:
                        self.emit(event_type, payload)
                    self.compute_ms.append(computed)
                    self.cached_metrics = self.engine.metrics()
                    self.tick_index += 1
                    self.step_finished.set()
                    delay = max(0.0, self.config.dt_s / self.speed - (time.perf_counter() - start))
                self.wake.wait(delay)
                self.wake.clear()
            with self.lock:
                if self.status not in TERMINAL:
                    self.status = "completed"
                self.emit("run_status", {"status": self.status, "speed": self.speed})
        except Exception as exc:
            with self.lock:
                self.status = "failed"
                self.metadata["failure"] = f"{type(exc).__name__}: {exc}"
                self.emit("run_status", {"status": "failed", "reason": self.metadata["failure"]})
        finally:
            self.step_finished.set()
            with self.lock:
                for measurement in self.pending_measurements:
                    self.emit("measurement_unused", {
                        "measurement_id": measurement["measurement_id"],
                        "reason": "运行已结束，测量未交付算法", "status": "UNUSED_RUN_ENDED",
                    })
                self.pending_measurements.clear()
                self.metadata["metrics"] = self.metrics()
                self.write_metadata()
                self.export_metrics()
                self.index_callback(self.snapshot())

    def control(self, action: str, speed: float | None = None) -> dict:
        """控制下一步节奏；非法转换显式拒绝。"""
        if action in {"pause", "stop"}:
            with self.lock:
                if self.status in TERMINAL:
                    raise ValueError(f"运行已结束：{self.status}")
                if action == "pause" and self.status != "running":
                    raise ValueError("只有运行中可以暂停")
                self.status = "paused" if action == "pause" else "stopped"
                self.wake.set()
            # 不持锁等待当前步完成；先落盘完整观测与波面，再发出暂停确认。
            if not self.step_finished.wait(timeout=30):
                raise ValueError("当前数学步尚未完成，暂停数据仍在同步")
            if action == "stop":
                # 终止事件由工作线程最后写入，确认后才允许完整历史回放。
                self.thread.join(timeout=30)
                if self.thread.is_alive():
                    raise ValueError("运行停止数据仍在落盘，请稍后重试")
                return self.snapshot()
            with self.lock:
                if self.status != "paused":
                    raise ValueError(f"等待暂停期间运行状态已变为 {self.status}")
                self.emit("run_status", {"status": "paused", "speed": self.speed, "action": action})
                self.write_metadata()
                return self.snapshot()
        with self.lock:
            if self.status in TERMINAL:
                raise ValueError(f"运行已结束：{self.status}")
            if action == "resume":
                if self.status != "paused":
                    raise ValueError("只有暂停后可以继续")
                self.status = "running"
            elif action == "speed":
                self.speed = float(speed)
            else:
                raise ValueError("未知控制动作")
            self.emit("run_status", {"status": self.status, "speed": self.speed, "action": action})
            self.write_metadata()
            self.wake.set()
            return self.snapshot()

    def inject(self, measurement: dict) -> dict:
        """接入已映射仿真时钟的测量，防止重复、未知目标和无限未来缓冲。"""
        with self.lock:
            if self.status in TERMINAL:
                raise ValueError("运行已经结束")
            from app.adapters.validation import validate_measurement_calibration
            from app.contracts import AcousticRangeObservation, CommunicationObservation
            observation_model = (AcousticRangeObservation if measurement.get("event_type") == "acoustic_range"
                                 else CommunicationObservation)
            observation = observation_model.model_validate({k: v for k, v in measurement.items() if k != "event_type"})
            context = self.config.fusion_context.model_copy(update={"anchors_world_m": self.config.anchors_world_m})
            validate_measurement_calibration(observation, context)
            total = math.ceil(self.config.duration_s / self.config.dt_s)
            if self.tick_index >= total:
                raise ValueError("最后一个数学步已完成，没有可接收测量的后续步")
            mid = measurement["measurement_id"]
            if mid in self.measurement_ids:
                raise ValueError("重复 measurement_id")
            if measurement["target_id"] not in {t.target_id for t in self.config.targets}:
                raise ValueError("未知 target_id")
            if measurement.get("event_type") == "acoustic_range" and measurement.get("anchor_id") not in self.config.anchors_world_m:
                raise ValueError("未知 anchor_id")
            measured = measurement["measurement_time_s"]
            if measured > (total - 1) * self.config.dt_s + 1e-9:
                raise ValueError("测量时刻超出最后一个数学采样时刻")
            if measured < self.sim_time_s - 2 or measured > min(self.config.duration_s, self.sim_time_s + 5):
                raise ValueError("测量超过允许的过去 2s / 未来 5s 时间窗")
            if len(self.pending_measurements) >= 1000:
                raise ValueError("测量缓冲已满")
            # 保留未来测量预排功能，观测最早在自身测量时刻才能到达算法。
            measurement["received_sim_time_s"] = max(self.sim_time_s, measured)
            self.pending_measurements.append(measurement)
            self.measurement_ids.add(mid)
            self.emit("measurement_received", {
                "measurement_id": mid, "measurement": dict(measurement),
                "status": "BUFFERED", "fusion_status": "PASSTHROUGH_NOT_FUSED",
            })
            return {"accepted": True, "measurement_id": mid, "fusion_status": "PASSTHROUGH_NOT_FUSED"}

    def export_metrics(self) -> Path:
        """从已落盘评价事件导出 CSV，保留所有失败样本及其状态。"""
        target = self.run_dir / "metrics.csv"
        rows = [e["payload"] for e in self.events if e["event_type"] == "evaluation_sample"]
        keys = sorted({k for row in rows for k in row})
        with target.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=keys)
            writer.writeheader()
            writer.writerows({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in r.items()} for r in rows)
        return target


class RunManager:
    """场景加载和运行索引；每个 SQLite 操作建立独立连接。"""

    def __init__(self, data_root: Path | None = None, scenario_root: Path | None = None):
        self.data_root = data_root or ROOT / "data"
        self.scenario_root = scenario_root or ROOT / "scenarios"
        self.data_root.mkdir(parents=True, exist_ok=True)
        (self.data_root / "runs").mkdir(exist_ok=True)
        self.scenario_root.mkdir(parents=True, exist_ok=True)
        self.runs: dict[str, RunState] = {}
        self.db_path = self.data_root / "index.sqlite3"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, snapshot TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS scenarios (scenario_id TEXT PRIMARY KEY, path TEXT NOT NULL)")

    def index(self, snapshot: dict) -> None:
        """索引不存事件，只存轻量运行状态与标识。"""
        brief = {k: v for k, v in snapshot.items() if k != "config"}
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO runs VALUES (?,?)", (snapshot["run_id"], json.dumps(brief)))

    def scenarios(self) -> list[dict]:
        """列出已经验证的 YAML 场景。"""
        return [self.load_scenario(p.stem).model_dump(mode="json") for p in sorted(self.scenario_root.glob("*.yaml"))]

    def load_scenario(self, scenario_id: str) -> ScenarioConfig:
        """使用受限标识符定位场景，避免路径逃逸。"""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", scenario_id):
            raise ValueError("非法场景 ID")
        path = self.scenario_root / f"{scenario_id}.yaml"
        if not path.exists():
            raise KeyError(scenario_id)
        return ScenarioConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    def save_scenario(self, config: ScenarioConfig) -> ScenarioConfig:
        """保存为新的版本文件，不覆盖已有场景和原始材料。"""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", config.scenario_id):
            raise ValueError("场景 ID 只允许字母、数字、下划线和短横线")
        if (self.scenario_root / f"{config.scenario_id}.yaml").exists():
            config = config.model_copy(update={"scenario_id": f"{config.scenario_id[:70]}-{uuid.uuid4().hex[:6]}"})
        path = self.scenario_root / f"{config.scenario_id}.yaml"
        path.write_text(yaml.safe_dump(config.model_dump(mode="json"), allow_unicode=True, sort_keys=False), encoding="utf-8")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO scenarios VALUES (?,?)", (config.scenario_id, str(path)))
        return config

    def create(self, config: ScenarioConfig) -> RunState:
        """创建不可变配置快照，并启动独立计算线程。"""
        active = sum(r.status not in TERMINAL for r in self.runs.values())
        if active >= 4:
            raise ValueError("基础版本最多同时运行四个场景，请先停止已有运行")
        state = RunState(config, self.data_root / "runs" / str(uuid.uuid4()), self.index)
        self.runs[state.run_id] = state
        self.index(state.snapshot())
        state.thread.start()
        return state

    def get(self, run_id: str) -> RunState:
        """获得本进程的运行；历史运行只能回放，不能恢复计算线程。"""
        if run_id not in self.runs:
            raise KeyError(run_id)
        return self.runs[run_id]

    def run_path(self, run_id: str) -> Path:
        """验证 UUID 与目录存在性后定位历史产物。"""
        try:
            if str(uuid.UUID(run_id)) != run_id:
                raise ValueError
        except ValueError as exc:
            raise KeyError(run_id) from exc
        path = self.data_root / "runs" / run_id
        if not path.is_dir():
            raise KeyError(run_id)
        return path

    def events(self, run_id: str, after_seq: int = 0) -> list[dict]:
        """运行中读取已落盘缓存，历史运行从 JSONL 恢复原事件。"""
        if run_id in self.runs:
            state = self.runs[run_id]
            with state.lock:
                return [e for e in state.events if e["event_seq"] > after_seq]
        path = self.run_path(run_id) / "events.jsonl"
        return [e for line in path.read_text(encoding="utf-8").splitlines() if (e := json.loads(line))["event_seq"] > after_seq]

    def list_runs(self) -> list[dict]:
        """合并当前和历史索引；异常退出的活跃记录标为进程已结束。"""
        with sqlite3.connect(self.db_path) as conn:
            rows = [json.loads(s) for (s,) in conn.execute("SELECT snapshot FROM runs ORDER BY rowid DESC")]
        for row in rows:
            if row["run_id"] in self.runs:
                row.update(self.runs[row["run_id"]].snapshot())
            elif row["status"] not in TERMINAL:
                row["status"] = "interrupted"
        return rows

    def close(self) -> None:
        """服务退出时停止并等待工作线程，保留运行文件。"""
        for state in self.runs.values():
            if state.status not in TERMINAL:
                state.control("stop")
            state.thread.join(timeout=30)


def metrics_csv_preview(metrics: dict[str, Any]) -> str:
    """提供汇总指标的文本形式，便于无 GUI 联调。"""
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["algorithm_id", "metrics_json"])
    for key, value in metrics.get("algorithms", {}).items():
        writer.writerow([key, json.dumps(value, ensure_ascii=False)])
    return stream.getvalue()

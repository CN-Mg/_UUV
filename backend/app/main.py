"""本地 REST / WebSocket 入口；计算在运行线程中执行。"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app import __version__
from app.contracts import (
    FusionBatch,
    FusionContext,
    FusionEstimate,
    LayoutEvaluation,
    LayoutEvaluationRequest,
    LayoutRequest,
    LayoutResult,
    ScenarioConfig,
    VisionEstimate,
    VisionRequest,
)
from app.services.runtime import ROOT, TERMINAL, RunManager


class StartRequest(BaseModel):
    """启动参数：可引用已存场景，也可提交完整配置快照。"""

    model_config = ConfigDict(extra="forbid")
    scenario_id: str | None = None
    config: ScenarioConfig | None = None


class SpeedRequest(BaseModel):
    """播放节奏倍率；不改变数学步长。"""

    speed: float = Field(ge=.1, le=16, description="节奏倍率，范围 0.1～16")


class LayoutEvaluationCall(BaseModel):
    """2.1 独立几何评价调用；不需要启动 GUI 或完整仿真。"""

    model_config = ConfigDict(extra="forbid")
    algorithm_id: str = "fixed_layout_v1"
    request: LayoutEvaluationRequest


class LayoutOptimizationCall(BaseModel):
    """2.1 优化调用；返回布局仍须满足请求约束。"""

    model_config = ConfigDict(extra="forbid")
    algorithm_id: str = "fixed_layout_v1"
    request: LayoutRequest


class VisionCall(BaseModel):
    """2.2 单帧联调；有状态连续算法应通过运行引擎调用。"""

    model_config = ConfigDict(extra="forbid")
    algorithm_id: str = "flat_snell_baseline_v1"
    request: VisionRequest


class FusionCall(BaseModel):
    """2.3 一次更新联调；标定独立于观测，不接收真值。"""

    model_config = ConfigDict(extra="forbid")
    algorithm_id: str = "noop_fusion_v1"
    context: FusionContext = Field(default_factory=FusionContext)
    batch: FusionBatch


def checked_estimate(value, model, target_id: str, sim_time_s: float,
                     algorithm_id: str, measurement_ids: set[str], algorithm_version: str):
    """拒绝目标/时刻错误和不合法输出，防止适配器污染事件链路。"""
    from app.adapters.validation import validate_estimate_result
    return validate_estimate_result(target_id, sim_time_s, value, model_type=model,
                                    expected_algorithm_id=algorithm_id,
                                    allowed_measurement_ids=measurement_ids,
                                    expected_algorithm_version=algorithm_version)


def create_app(data_root: Path | None = None, scenario_root: Path | None = None) -> FastAPI:
    """创建可注入临时存储的应用，供真实服务与 REST/WS 测试复用。"""
    manager = RunManager(data_root, scenario_root)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await asyncio.to_thread(manager.close)

    app = FastAPI(title="微型 UUV 视觉定位仿真 · DEMO_UNCALIBRATED", version=__version__, lifespan=lifespan)
    app.state.manager = manager
    app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5180", "http://localhost:5180"], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(KeyError)
    async def missing_handler(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": f"未找到：{exc}"})

    @app.exception_handler(ValueError)
    async def value_handler(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.get("/api/health")
    def health():
        """返回服务、软件版本和解释器，便于检查是否使用了指定环境。"""
        import sys
        return {"status": "ok", "version": __version__, "evidence_status": "DEMO_UNCALIBRATED", "python_executable": sys.executable}

    @app.get("/api/scenarios")
    def scenarios():
        """列出有效场景。"""
        return manager.scenarios()

    @app.get("/api/scenarios/{scenario_id}")
    def scenario(scenario_id: str):
        """读取单个完整场景。"""
        return manager.load_scenario(scenario_id)

    @app.post("/api/scenarios")
    def save_scenario(config: ScenarioConfig):
        """保存独立场景版本。"""
        return manager.save_scenario(config)

    @app.get("/api/adapters")
    def adapters():
        """列出实际注册实现，避免前端把占位误报为研究算法。"""
        from app.adapters.registry import catalog
        return catalog()

    @app.post("/api/layout/evaluate", response_model=LayoutEvaluation)
    def evaluate_layout(call: LayoutEvaluationCall):
        """2.1：在指定深度网格上评价覆盖与交会几何，不虚构真实精度。"""
        from app.adapters.registry import create_adapter
        result = create_adapter("layout", call.algorithm_id).evaluate(call.request)
        return LayoutEvaluation.model_validate(result.model_dump() if isinstance(result, BaseModel) else result)

    @app.post("/api/layout/optimize", response_model=LayoutResult)
    def optimize_layout(call: LayoutOptimizationCall):
        """2.1：调用可替换布局模块；固定布局保持 NOT_OPTIMIZED。"""
        from app.adapters.registry import create_adapter
        from app.adapters.validation import validate_layout_result
        result = create_adapter("layout", call.algorithm_id).optimize(call.request)
        return validate_layout_result(call.request, result)

    @app.post("/api/vision/localize", response_model=VisionEstimate)
    def vision_localize(call: VisionCall):
        """2.2：只给观测和白名单标定的单帧接口。"""
        from app.adapters.registry import create_adapter
        adapter = create_adapter("vision", call.algorithm_id)
        result = adapter.localize(call.request)
        return checked_estimate(result, VisionEstimate, call.request.target_id, call.request.sim_time_s,
                                call.algorithm_id, {o.measurement_id for o in call.request.observations},
                                adapter.algorithm_version)

    @app.post("/api/fusion/update", response_model=FusionEstimate)
    def fusion_update(call: FusionCall):
        """2.3：保留观测各自时间与来源，每次单独创建并重置联调实例。"""
        from app.adapters.registry import create_adapter
        adapter = create_adapter("fusion", call.algorithm_id)
        adapter.reset(call.context)
        result = adapter.update(call.batch)
        allowed = {o.measurement_id for o in [*call.batch.acoustic, *call.batch.communication]}
        if call.batch.vision:
            allowed.update(call.batch.vision.used_measurement_ids)
        return checked_estimate(result, FusionEstimate, call.batch.target_id, call.batch.sim_time_s,
                                call.algorithm_id, allowed, adapter.algorithm_version)

    @app.get("/api/runs")
    def runs():
        """列出可控制运行和可回放历史。"""
        return manager.list_runs()

    @app.post("/api/runs")
    def start(request: StartRequest):
        """创建配置快照并启动固定步长运行。"""
        config = request.config or manager.load_scenario(request.scenario_id or "demo_uncalibrated")
        return manager.create(config).snapshot()

    @app.get("/api/runs/{run_id}")
    def run_info(run_id: str):
        """返回当前状态或历史元数据。"""
        if run_id in manager.runs:
            return manager.get(run_id).snapshot()
        return json.loads((manager.run_path(run_id) / "metadata.json").read_text(encoding="utf-8"))

    @app.post("/api/runs/{run_id}/speed")
    def speed(run_id: str, request: SpeedRequest):
        """调整播放节奏。"""
        return manager.get(run_id).control("speed", request.speed)

    @app.post("/api/runs/{run_id}/pause")
    def pause(run_id: str):
        """暂停后续数学步。"""
        return manager.get(run_id).control("pause")

    @app.post("/api/runs/{run_id}/resume")
    def resume(run_id: str):
        """恢复后续数学步。"""
        return manager.get(run_id).control("resume")

    @app.post("/api/runs/{run_id}/stop")
    def stop(run_id: str):
        """停止并保留全部运行记录。"""
        return manager.get(run_id).control("stop")

    @app.get("/api/runs/{run_id}/events")
    @app.get("/api/runs/{run_id}/replay")
    def events(run_id: str, after_seq: int = Query(default=0, ge=0)):
        """增量读取已记录事件，回放不调用定位算法。"""
        return manager.events(run_id, after_seq)

    @app.get("/api/runs/{run_id}/metrics")
    def metrics(run_id: str):
        """读取后端科学评价与计算耗时。"""
        if run_id in manager.runs:
            return manager.get(run_id).metrics()
        return json.loads((manager.run_path(run_id) / "metadata.json").read_text(encoding="utf-8")).get("metrics", {})

    @app.post("/api/runs/{run_id}/measurements")
    def measurements(run_id: str, payload: dict):
        """校验声学/通信输入；当前 NoOp 仅接收而不进行融合计权。"""
        from app.contracts import AcousticRangeObservation, CommunicationObservation
        kind = payload.get("event_type", payload.get("kind", "acoustic_range"))
        raw = payload.get("payload", payload)
        if not isinstance(raw, dict):
            raise ValueError("payload 必须是 JSON 对象")
        raw = {k: v for k, v in raw.items() if k not in {"kind", "event_type"}}
        now = manager.get(run_id).sim_time_s
        measured = raw.get("measurement_time_s", now)
        # 未来输入是仿真预排计划；不得把它描述成提前取得的物理测量。
        raw.setdefault("received_sim_time_s", max(now, measured) if isinstance(measured, (int, float)) else now)
        if kind not in {"acoustic_range", "communication_observation"}:
            raise ValueError("仅支持 acoustic_range / communication_observation")
        model = AcousticRangeObservation if kind == "acoustic_range" else CommunicationObservation
        try:
            data = model.model_validate(raw).model_dump(mode="json")
        except ValidationError as exc:
            raise HTTPException(422, detail=json.loads(exc.json(include_url=False))) from exc
        data["event_type"] = kind
        return manager.get(run_id).inject(data)

    @app.get("/api/runs/{run_id}/export/{artifact}")
    def export(run_id: str, artifact: str):
        """仅开放四种明确产物，禁止任意文件路径。"""
        filenames = {"scenario.yaml": "effective-scenario.yaml", "metadata.json": "metadata.json", "events.jsonl": "events.jsonl", "metrics.csv": "metrics.csv"}
        if artifact not in filenames:
            raise HTTPException(404, "未知产物")
        path = manager.run_path(run_id) / filenames[artifact]
        if run_id in manager.runs:
            with manager.get(run_id).lock:
                if artifact == "metrics.csv":
                    manager.get(run_id).export_metrics()
                content = path.read_bytes()
        else:
            content = path.read_bytes()
        # 小型 M1 产物取锁内完整快照，避免边写边流式下载产生截断 JSON/JSONL。
        return Response(content, media_type="application/octet-stream", headers={
            "Content-Disposition": f'attachment; filename="{run_id}-{artifact}"'
        })

    @app.websocket("/ws/runs/{run_id}")
    async def websocket(websocket: WebSocket, run_id: str, after_seq: int = 0):
        """按严格事件序号补发后续事件，发送端从不生成数学仿真结果。"""
        await websocket.accept()
        try:
            manager.run_path(run_id)
            while True:
                for event in manager.events(run_id, after_seq):
                    await websocket.send_json(event)
                    after_seq = event["event_seq"]
                if run_id not in manager.runs or manager.get(run_id).status in TERMINAL:
                    # 工作线程完成尾部记录后才结束连接，避免丢失终止事件。
                    if run_id not in manager.runs or not manager.get(run_id).thread.is_alive():
                        for event in manager.events(run_id, after_seq):
                            await websocket.send_json(event)
                            after_seq = event["event_seq"]
                        break
                await asyncio.sleep(.05)
            await websocket.close()
        except KeyError:
            await websocket.close(code=4404, reason="未知运行")
        except WebSocketDisconnect:
            pass

    app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")
    return app


app = create_app()

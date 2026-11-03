"""真实 API、JSONL、WebSocket 与运行控制的集成验收。"""

import json
import time
from pathlib import Path

import pytest
from app.contracts import (
    CameraObservation,
    EvaluationSample,
    EventEnvelope,
    FusionEstimate,
    RunMetadata,
    ScenarioConfig,
    UuvTruth,
    VisionEstimate,
)
from app.main import create_app
from app.services.runtime import config_hash
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    """临时存储隔离测试运行，不污染正式演示记录。"""
    app = create_app(tmp_path / "data", tmp_path / "scenarios")
    config = ScenarioConfig().model_copy(update={"duration_s": .3})
    app.state.manager.save_scenario(config)
    with TestClient(app) as result:
        yield result


def finish(client, run_id):
    """有上限地等待实际后端计算结束，失败状态原样触发断言。"""
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}").json()
        if response["status"] in {"completed", "failed", "stopped"}:
            # 终态计算线程还要写元数据和 CSV，等待其完成。
            state = client.app.state.manager.get(run_id)
            state.thread.join(10)
            return response
        time.sleep(.01)
    raise AssertionError("运行超过测试时间上限")


def test_health_environment(client):
    data = client.get("/api/health").json()
    assert data["status"] == "ok"
    assert "UUV" in data["python_executable"]


def test_api_record_replay_and_exports(client):
    scenarios = client.get("/api/scenarios").json()
    assert len(scenarios) == 1
    run = client.post("/api/runs", json={"scenario_id": scenarios[0]["scenario_id"]})
    assert run.status_code == 200, run.text
    rid = run.json()["run_id"]
    assert finish(client, rid)["status"] == "completed"
    events = client.get(f"/api/runs/{rid}/events").json()
    assert [e["event_seq"] for e in events] == list(range(1, len(events) + 1))
    kinds = {e["event_type"] for e in events}
    assert {"uuv_truth", "camera_observation", "vision_estimate", "evaluation_sample"} <= kinds
    payload_models = {"uuv_truth": UuvTruth, "camera_observation": CameraObservation,
                      "vision_estimate": VisionEstimate, "evaluation_sample": EvaluationSample,
                      "fusion_estimate": FusionEstimate}
    for event in events:
        EventEnvelope.model_validate(event)
        if event["event_type"] in payload_models:
            payload_models[event["event_type"]].model_validate(event["payload"])
    assert client.get(f"/api/runs/{rid}/replay").json() == events
    assert client.get(f"/api/runs/{rid}/events?after_seq=3").json() == events[3:]
    assert client.get(f"/api/runs/{rid}/metrics").json()["algorithms"]
    raw = client.get(f"/api/runs/{rid}/export/events.jsonl")
    assert [json.loads(s) for s in raw.text.splitlines()] == events
    for name in ["metadata.json", "scenario.yaml", "metrics.csv"]:
        assert client.get(f"/api/runs/{rid}/export/{name}").status_code == 200
    RunMetadata.model_validate(client.get(f"/api/runs/{rid}/export/metadata.json").json())
    assert client.get(f"/api/runs/{rid}/export/secret").status_code == 404


def test_websocket_replays_exact_recorded_sequence(client):
    run = client.post("/api/runs", json={}).json()
    rid = run["run_id"]
    expected = []
    with client.websocket_connect(f"/ws/runs/{rid}?after_seq=0") as websocket:
        while True:
            event = websocket.receive_json()
            expected.append(event)
            if event["event_type"] == "run_status" and event["payload"]["status"] in {"completed", "failed"}:
                break
    assert finish(client, rid)["status"] == "completed"
    assert expected == client.get(f"/api/runs/{rid}/events").json()


def test_pause_resume_stop_and_config_snapshot(client):
    config = ScenarioConfig().model_dump(mode="json")
    config["duration_s"] = 5
    response = client.post("/api/runs", json={"config": config, "speed": .5})
    assert response.status_code == 200, response.text
    assert response.json()["speed"] == .5
    rid = response.json()["run_id"]
    assert client.post(f"/api/runs/{rid}/pause").json()["status"] == "paused"
    paused_events = client.get(f"/api/runs/{rid}/events").json()
    assert paused_events[0]["payload"]["speed"] == .5
    assert paused_events[-1]['event_type'] == 'run_status'
    assert paused_events[-1]['payload']['status'] == 'paused'
    time.sleep(.25)
    assert client.get(f"/api/runs/{rid}/events").json() == paused_events
    t1 = client.get(f"/api/runs/{rid}").json()["sim_time_s"]
    time.sleep(.2)
    assert client.get(f"/api/runs/{rid}").json()["sim_time_s"] == t1
    assert client.post(f"/api/runs/{rid}/speed", json={"speed": 2}).json()["speed"] == 2
    assert client.post(f"/api/runs/{rid}/speed", json={"speed": -1}).status_code == 422
    assert client.post(f"/api/runs/{rid}/resume").json()["status"] == "running"
    assert client.post(f"/api/runs/{rid}/stop").json()["status"] == "stopped"
    assert finish(client, rid)["status"] == "stopped"
    assert client.post(f"/api/runs/{rid}/resume").status_code == 422
    assert client.get(f"/api/runs/{rid}").json()["config"] == config


def test_unknown_ids_and_invalid_configuration(client):
    assert client.get("/api/scenarios/missing").status_code == 404
    assert client.get("/api/runs/not-a-uuid/events").status_code == 404
    assert client.post("/api/runs", json={"config": {"dt_s": 0}}).status_code == 422
    assert client.post("/api/runs", json={"speed": 0}).status_code == 422
    assert client.post("/api/runs", json={"unexpected": True}).status_code == 422


def test_configuration_hash_and_saved_scene(client):
    config = ScenarioConfig()
    reordered = ScenarioConfig.model_validate(dict(reversed(list(config.model_dump().items()))))
    assert config_hash(config) == config_hash(reordered)
    modified = config.model_dump(mode="json")
    modified["cameras"][0]["position_m"][0] += .2
    saved = client.post("/api/scenarios", json=modified).json()
    assert saved["scenario_id"] != config.scenario_id
    assert client.get(f"/api/scenarios/{saved['scenario_id']}").json() == saved
    assert config_hash(config) != config_hash(ScenarioConfig.model_validate(modified))


def test_history_replays_after_process_recreation(client):
    rid = client.post("/api/runs", json={}).json()["run_id"]
    assert finish(client, rid)["status"] == "completed"
    expected = client.get(f"/api/runs/{rid}/events").json()
    manager = client.app.state.manager
    restored = create_app(Path(manager.data_root), Path(manager.scenario_root))
    with TestClient(restored) as history:
        assert history.get(f"/api/runs/{rid}/replay").json() == expected
        assert any(row["run_id"] == rid for row in history.get("/api/runs").json())


def test_measurement_input_route_duplicate_and_anchor_validation(client):
    """测量可被接入但 NoOp 不虚报融合；无效锚点和重复 ID 显式拒绝。"""
    config = ScenarioConfig().model_dump(mode="json")
    config["duration_s"] = .7
    rid = client.post("/api/runs", json={"config": config}).json()["run_id"]
    client.post(f"/api/runs/{rid}/pause")
    measurement = {"event_type": "acoustic_range", "payload": {
        "measurement_id": "test-range", "target_id": "UUV-001", "measurement_time_s": 0,
        "anchor_id": "A1", "range_m": 1.5, "variance_m2": .01,
    }}
    assert client.post(f"/api/runs/{rid}/measurements", json=measurement).status_code == 200
    assert client.post(f"/api/runs/{rid}/measurements", json=measurement).status_code == 422
    bad = {"event_type": "acoustic_range", "payload": {**measurement["payload"], "measurement_id": "bad", "anchor_id": "missing"}}
    assert client.post(f"/api/runs/{rid}/measurements", json=bad).status_code == 422
    communication = {"event_type": "communication_observation", "payload": {
        "measurement_id": "test-comms", "target_id": "UUV-001", "measurement_time_s": 0,
        "source_id": "radio1", "message": "联调状态信息",
    }}
    assert client.post(f"/api/runs/{rid}/measurements", json=communication).status_code == 200
    assert client.post(f"/api/runs/{rid}/measurements", json={"payload": []}).status_code == 422
    client.post(f"/api/runs/{rid}/resume")
    assert finish(client, rid)["status"] == "completed"
    events = client.get(f"/api/runs/{rid}/events").json()
    assert {"acoustic_range", "communication_observation"} <= {e["event_type"] for e in events}
    fusion = [e["payload"] for e in events if e["event_type"] == "fusion_estimate"]
    assert fusion and all(e["fusion_status"] == "PASSTHROUGH_NOT_FUSED" for e in fusion)
    assert all("acoustic" not in e["used_sources"] for e in fusion)


def test_future_measurement_preserved_when_stopped(client):
    """已接收但尚未交付的测量在停止时留有完整输入与未使用原因。"""
    config = ScenarioConfig().model_dump(mode="json")
    config["duration_s"] = 3
    rid = client.post("/api/runs", json={"config": config}).json()["run_id"]
    client.post(f"/api/runs/{rid}/pause")
    measurement = {"measurement_id": "future", "target_id": "UUV-001", "measurement_time_s": 2,
                   "anchor_id": "A1", "range_m": 2}
    assert client.post(f"/api/runs/{rid}/measurements", json=measurement).status_code == 200
    client.post(f"/api/runs/{rid}/stop")
    finish(client, rid)
    events = client.get(f"/api/runs/{rid}/events").json()
    assert any(e["event_type"] == "measurement_received" and e["payload"]["measurement_id"] == "future" for e in events)
    assert any(e["event_type"] == "measurement_unused" and e["payload"]["measurement_id"] == "future" for e in events)

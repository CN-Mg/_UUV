"""三项研究模块无需 GUI 的公开联调接口验收。"""

import json
from pathlib import Path

import pytest
from app.contracts import ScenarioConfig
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    """联调测试隔离索引和运行目录。"""
    with TestClient(create_app(tmp_path / 'data', tmp_path / 'scenarios')) as result:
        yield result


def vision_request():
    """已保存的测量/标定样例不包含任何真值字段。"""
    path = Path(__file__).resolve().parents[1] / 'contracts/fixtures/vision-request.json'
    return json.loads(path.read_text(encoding='utf-8'))


def test_layout_evaluate_and_optimization_status(client):
    config = ScenarioConfig()
    request = {'tank': config.tank.model_dump(), 'cameras': [c.model_dump() for c in config.cameras],
               'depths_m': [1.], 'grid_size': 3}
    response = client.post('/api/layout/evaluate', json={'request': request})
    assert response.status_code == 200, response.text
    assert response.json()['metric_kind'] == 'GEOMETRIC_POINT_COVERAGE'
    assert response.json()['sample_count'] == 9
    response = client.post('/api/layout/optimize', json={'request': {**request, 'camera_count': 3}})
    assert response.status_code == 200, response.text
    assert response.json()['optimization_status'] == 'NOT_OPTIMIZED'
    assert len(response.json()['cameras']) == 3
    response = client.post('/api/layout/evaluate', json={'algorithm_id': 'missing', 'request': request})
    assert response.status_code == 422


def test_visual_and_fusion_standalone_calls(client):
    request = vision_request()
    response = client.post('/api/vision/localize', json={'request': request})
    assert response.status_code == 200, response.text
    estimate = response.json()
    assert estimate['valid'] and estimate['target_id'] == request['target_id']
    response = client.post('/api/fusion/update', json={'batch': {
        'target_id': request['target_id'], 'sim_time_s': request['sim_time_s'], 'vision': estimate,
    }})
    assert response.status_code == 200, response.text
    fused = response.json()
    assert fused['fusion_status'] == 'PASSTHROUGH_NOT_FUSED'
    assert fused['position_m'] == estimate['position_m']
    assert fused['used_sources'] == ['vision']
    bad = {**request, 'schema_version': '9.0'}
    assert client.post('/api/vision/localize', json={'request': bad}).status_code == 422
    assert client.post('/api/vision/localize', json={'request': {**request, 'truth': [0, 0, -1]}}).status_code == 422


def test_invalid_configuration_does_not_create_empty_run(client):
    config = ScenarioConfig().model_dump(mode='json')
    config['adapters']['vision'] = 'not_registered'
    assert client.post('/api/runs', json={'config': config}).status_code == 422
    assert list((client.app.state.manager.data_root / 'runs').iterdir()) == []

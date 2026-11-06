"""几何与折射的独立解析性质、数值一致性、波纹与失败保留。"""

import numpy as np
import pytest
from app.adapters.geometry import camera_rotation, load_markers, marker_corners, yaw_rotation
from app.adapters.refraction import PinholeRefraction, SnellRefraction
from app.adapters.wave import SeededMultiSineSurface
from app.contracts import (
    BackprojectionRequest,
    CameraCalibration,
    OpticsConfig,
    ProjectionRequest,
    ScenarioConfig,
    TargetConfig,
    WaveConfig,
)
from app.simulation.engine import SimulationEngine


def test_coordinate_roundtrip_and_right_handed_camera():
    camera = ScenarioConfig().cameras[0]
    rotation = camera_rotation(camera)
    np.testing.assert_allclose(rotation @ rotation.T, np.eye(3), atol=1e-12)
    assert np.linalg.det(rotation) == pytest.approx(1)
    point = np.array([.3, -.2, -1.2])
    np.testing.assert_allclose(rotation.T @ (rotation @ (point-camera.position_m))+camera.position_m, point)
    np.testing.assert_allclose(yaw_rotation(np.pi/2) @ [1, 0, 0], [0, 1, 0], atol=1e-12)


def test_encoded_marker_is_012_not_016():
    for marker in load_markers():
        corners = marker_corners(marker)
        assert np.linalg.norm(corners[1]-corners[0]) == pytest.approx(.12)
        np.testing.assert_allclose(corners.mean(axis=0), marker.center_m)
        assert np.linalg.norm(corners[1]-corners[0]) != pytest.approx(.16)


def test_pinhole_center_behind_and_outside():
    camera = CameraCalibration(camera_id='vertical', position_m=(0, 0, 1.5))
    model = PinholeRefraction()
    center = model.project(ProjectionRequest(point_world_m=(0, 0, -1), camera=camera))
    np.testing.assert_allclose(center.pixel_px, [640, 360])
    assert center.in_image
    assert not model.project(ProjectionRequest(point_world_m=(0, 0, 3), camera=camera)).valid
    assert not model.project(ProjectionRequest(point_world_m=(10, 0, -1), camera=camera)).in_image


@pytest.mark.parametrize('point', [(0, 0, -1), (.8, .2, -1.1), (-1, 1.4, -1.6)])
def test_snell_normal_incidence_and_reciprocity(point):
    camera = CameraCalibration(camera_id='vertical', position_m=(0, 0, 1.5))
    model = SnellRefraction()
    projected = model.project(ProjectionRequest(point_world_m=point, camera=camera))
    assert projected.valid
    back = model.backproject(BackprojectionRequest(pixel_px=projected.pixel_px, camera=camera))
    assert back.valid
    q = np.asarray(back.intersection_world_m)
    difference = np.asarray(point)-q
    difference /= np.linalg.norm(difference)
    np.testing.assert_allclose(back.water_direction_world, difference, atol=1e-9)
    air = np.asarray(back.air_direction_world)
    water = np.asarray(back.water_direction_world)
    assert 1.00029*np.linalg.norm(air[:2]) == pytest.approx(1.333*np.linalg.norm(water[:2]), abs=1e-10)
    if point[:2] == (0, 0):
        np.testing.assert_allclose(projected.pixel_px, (640, 360))


def test_equal_indices_give_straight_light_and_invalid_geometry():
    camera = ScenarioConfig().cameras[0]
    optics = OpticsConfig(n_air=1.1, n_water=1.1)
    request = ProjectionRequest(point_world_m=(.4, .2, -1), camera=camera, optics=optics)
    np.testing.assert_allclose(SnellRefraction().project(request).pixel_px,
                               PinholeRefraction().project(request).pixel_px, atol=1e-8)
    assert not SnellRefraction().project(request.model_copy(update={'point_world_m': (0, 0, .1)})).valid


def test_wave_seed_gradient_and_shared_time():
    a = SeededMultiSineSurface(WaveConfig(), 123)
    b = SeededMultiSineSurface(WaveConfig(), 123)
    assert a.sample(.2, -.4, 1.2) == b.sample(.2, -.4, 1.2)
    sample = a.sample(.2, -.4, 1.2)
    h = 1e-6
    derivative_x = (a.sample(.2+h, -.4, 1.2).height_m-a.sample(.2-h, -.4, 1.2).height_m)/(2*h)
    assert sample.gradient[0] == pytest.approx(derivative_x, abs=1e-9)
    assert np.linalg.norm(sample.normal_world) == pytest.approx(1)
    assert abs(sample.height_m) <= .02
    assert a.sample(.2, -.4, 1.2) == sample


def test_wavy_path_uses_actual_local_normal():
    surface = SeededMultiSineSurface(WaveConfig(), 20261102)
    model = SnellRefraction(surface)
    camera = ScenarioConfig().cameras[0]
    projected = model.project(ProjectionRequest(point_world_m=(.7, .1, -1), camera=camera, sim_time_s=.4))
    assert projected.valid
    q = np.asarray(projected.ray.intersection_world_m)
    sample = surface.sample(*q[:2], .4)
    assert q[2] == pytest.approx(sample.height_m)
    back = model.backproject(BackprojectionRequest(pixel_px=projected.pixel_px, camera=camera, sim_time_s=.4))
    np.testing.assert_allclose(back.water_direction_world, projected.ray.water_direction_world, atol=1e-7)


@pytest.mark.parametrize('mode', ['IDEAL_NO_REFRACTION', 'FLAT_SNELL_REFRACTION'])
def test_ideal_and_flat_numerical_consistency(mode):
    engine = SimulationEngine(ScenarioConfig(mode=mode))
    events = engine.step(0)
    estimate = next(p for kind, p in events if kind == 'vision_estimate' and p['algorithm_id'] == 'flat_snell_baseline_v1')
    np.testing.assert_allclose(estimate['position_m'], [.7, 0, -1], atol=1e-6)
    assert estimate['yaw_rad'] == pytest.approx(np.pi/2, abs=1e-6)
    observations = [p for kind, p in events if kind == 'camera_observation']
    for camera in engine.config.cameras:
        visible = {p['marker_id'] for p in observations if p['camera_id'] == camera.camera_id}
        assert visible & {0, 1, 2}
        assert not (visible & {3, 4} and visible & {5, 6})
    if mode == 'FLAT_SNELL_REFRACTION':
        metrics = engine.metrics()['algorithms']
        assert metrics['pinhole_baseline_v1']['rmse_m'] > .01


def test_deterministic_events_with_noise_and_independent_runs():
    config = ScenarioConfig(pixel_noise_std_px=.2)
    first, second = SimulationEngine(config), SimulationEngine(config)
    for tick in range(3):
        assert first.step(tick) == second.step(tick)


def test_two_target_identity_and_failure_samples_retained():
    engine = SimulationEngine(ScenarioConfig(targets=[TargetConfig(), TargetConfig(target_id='UUV-002', phase_rad=np.pi)]))
    truth = [p for k, p in engine.step(0) if k == 'uuv_truth']
    assert {p['target_id'] for p in truth} == {'UUV-001', 'UUV-002'}
    assert engine.metrics()['algorithms']['flat_snell_baseline_v1']['valid_count'] == 2
    failed = SimulationEngine(ScenarioConfig(cameras=ScenarioConfig().cameras[:1]))
    failed.step(0)
    metrics = failed.metrics()['algorithms']['flat_snell_baseline_v1']
    assert metrics['sample_count'] == 1 and metrics['valid_count'] == 0
    assert metrics['rmse_m'] is None
    assert metrics['failure_counts']['INSUFFICIENT_GEOMETRY'] == 1


def test_smoothing_lag_is_not_hidden_on_noise_free_motion():
    engine = SimulationEngine(ScenarioConfig())
    for tick in range(3):
        engine.step(tick)
    metrics = engine.metrics()['algorithms']
    assert metrics['flat_snell_smoothed_v1']['rmse_m'] > metrics['flat_snell_baseline_v1']['rmse_m']
    assert metrics['flat_snell_smoothed_v1']['filter_lag_nominal_s'] > 0

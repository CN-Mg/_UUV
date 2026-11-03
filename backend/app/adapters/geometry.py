"""坐标、标记和向量化投影公式。"""

import json
from pathlib import Path

import numpy as np

from app.contracts import CameraCalibration, MarkerGeometry, OpticsConfig


def unit(vector: np.ndarray) -> np.ndarray:
    """返回归一化向量，零向量为输入错误。"""
    length = np.linalg.norm(vector)
    if length < 1e-12:
        raise ValueError('不能归一化零向量')
    return vector / length


def camera_rotation(camera: CameraCalibration) -> np.ndarray:
    """T_camera_world 的旋转块：行向量依次是右、下、前。"""
    forward = unit(np.asarray(camera.look_at_m) - camera.position_m)
    up = np.array([0., 0., 1.])
    if abs(forward @ up) > .999:
        up = np.array([0., 1., 0.])
    right = unit(np.cross(forward, up))
    down = np.cross(forward, right)
    return np.array([right, down, forward])


def yaw_rotation(yaw_rad: float) -> np.ndarray:
    """机体系到世界的水平旋转；正 yaw 绕世界 +Z。"""
    c, s = np.cos(yaw_rad), np.sin(yaw_rad)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def load_markers(asset_path: Path | None = None) -> list[MarkerGeometry]:
    """只读元数据，从中心和轴向重建 0.12 m 编码标记。"""
    path = asset_path or Path(__file__).resolve().parents[3] / 'assets/models/uuv_001_metadata.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    return [MarkerGeometry(marker_id=m['id'], **{k: m[k] for k in
            ['center_m', 'u_axis', 'v_axis', 'outward_normal', 'black_square_size_m']})
            for m in data['markers']]


def marker_corners(marker: MarkerGeometry) -> np.ndarray:
    """依次为贴图左下、右下、右上、左上，边长不使用白板 0.16 m。"""
    signs = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])
    return (np.array(marker.center_m) + marker.black_square_size_m / 2
            * (signs[:, :1] * marker.u_axis + signs[:, 1:] * marker.v_axis))


def pinhole_many(points: np.ndarray, camera: CameraCalibration) -> np.ndarray:
    """候选世界点针孔投影；可见性由调用者另外检查。"""
    q = (points - camera.position_m) @ camera_rotation(camera).T
    z = np.where(abs(q[:, 2]) < 1e-12, 1e-12, q[:, 2])
    return np.column_stack((camera.fx_px * q[:, 0] / z + camera.cx_px,
                            camera.fy_px * q[:, 1] / z + camera.cy_px))


def flat_intersections(points: np.ndarray, camera: CameraCalibration,
                       optics: OpticsConfig) -> np.ndarray:
    """平面 Snell 求交：水平距离 s 满足 n_air sinθa=n_water sinθw。"""
    c = np.asarray(camera.position_m)
    delta = points[:, :2] - c[:2]
    distance = np.linalg.norm(delta, axis=1)
    ha = c[2]
    hw = np.maximum(-points[:, 2], 1e-8)
    na, nw = optics.n_air, optics.n_water
    s = distance * nw * ha / (nw * ha + na * hw)
    lo, hi = np.zeros(len(points)), distance.copy()
    # 有界 Newton：偏导为正，避免界面求解跳出两端点之间。
    for _ in range(12):
        w = distance - s
        f = na * s / np.sqrt(s*s + ha*ha) - nw * w / np.sqrt(w*w + hw*hw)
        if np.max(np.abs(f), initial=0) < 1e-12:
            break
        lo = np.where(f < 0, s, lo)
        hi = np.where(f > 0, s, hi)
        derivative = na * ha*ha / (s*s + ha*ha)**1.5 + nw * hw*hw / (w*w + hw*hw)**1.5
        candidate = s - f / derivative
        s = np.where((candidate < lo) | (candidate > hi), (lo+hi)/2, candidate)
    ratio = np.divide(s, distance, out=np.zeros_like(s), where=distance > 1e-12)
    return np.column_stack((c[:2] + delta * ratio[:, None], np.zeros(len(points))))


def flat_project_many(points: np.ndarray, camera: CameraCalibration,
                      optics: OpticsConfig) -> np.ndarray:
    """先求水面交点，再按空气中的针孔相机投影。"""
    return pinhole_many(flat_intersections(points, camera, optics), camera)

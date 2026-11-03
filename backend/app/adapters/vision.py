"""只使用像素、标定和历史估计的四自由度重投影基线。"""

import numpy as np
from scipy.optimize import least_squares

from app.contracts import BackprojectionRequest, VisionEstimate, VisionRequest

from .geometry import flat_project_many, marker_corners, pinhole_many, yaw_rotation
from .refraction import PinholeRefraction, SnellRefraction


class LeastSquaresLocalizer:
    """水平航行 xyz+yaw，roll/pitch=0 是声明的模型假设。"""

    algorithm_version = '1.0.0'

    def __init__(self, algorithm_id='flat_snell_baseline_v1', correction=True, smoothing=False):
        """初始化独立估计器状态，不接收场景、真值或生成器种子。"""
        self.algorithm_id = algorithm_id
        self.correction = correction
        self.smoothing = smoothing
        self._history: dict[str, VisionEstimate] = {}

    def _initial(self, request, observations, cameras, markers, corrected):
        # 按同一标记和角点交会射线，再由已知机体系几何求水平刚体变换。
        model = SnellRefraction() if corrected else PinholeRefraction()
        points, bodies = [], []
        for marker_id in sorted({o.marker_id for o in observations}):
            related = [o for o in observations if o.marker_id == marker_id]
            if len({o.camera_id for o in related}) < 2:
                continue
            for corner_index in range(4):
                a, b = np.zeros((3, 3)), np.zeros(3)
                count = 0
                for obs in related:
                    ray = model.backproject(BackprojectionRequest(pixel_px=obs.corners_px[corner_index],
                        camera=cameras[obs.camera_id], optics=request.calibration.optics,
                        sim_time_s=request.sim_time_s))
                    if not ray.valid:
                        continue
                    d = np.asarray(ray.water_direction_world)
                    origin = np.asarray(ray.intersection_world_m or ray.origin_world_m)
                    projector = np.eye(3)-np.outer(d, d)
                    a += projector
                    b += projector @ origin
                    count += 1
                if count >= 2 and np.linalg.cond(a) < 1e8:
                    points.append(np.linalg.solve(a, b))
                    bodies.append(marker_corners(markers[marker_id])[corner_index])
        if len(points) < 4:
            return None
        p, body = np.array(points), np.array(bodies)
        pc, bc = p-p.mean(axis=0), body-body.mean(axis=0)
        angle = np.arctan2(np.sum(bc[:, 0]*pc[:, 1]-bc[:, 1]*pc[:, 0]),
                           np.sum(bc[:, 0]*pc[:, 0]+bc[:, 1]*pc[:, 1]))
        translation = p.mean(axis=0)-yaw_rotation(angle) @ body.mean(axis=0)
        return np.array([*translation, angle])

    def localize(self, request: VisionRequest) -> VisionEstimate:
        """以所有有效角点的像素重投影残差求解，无真值初始化。"""
        result = VisionEstimate(target_id=request.target_id, sim_time_s=request.sim_time_s,
                                algorithm_id=self.algorithm_id,
                                correction_status='MODEL_AWARE_DEMO' if self.correction else 'UNCORRECTED')
        calibration = request.calibration
        cameras = {c.camera_id: c for c in calibration.cameras}
        markers = {m.marker_id: m for m in calibration.markers}
        observations = [o for o in request.observations if o.valid and o.target_id == request.target_id
                        and o.camera_id in cameras and o.marker_id in markers]
        if not observations:
            return result
        if any(abs(o.measurement_time_s-request.sim_time_s) > 1e-6 for o in observations):
            return result.model_copy(update={'status': 'TIME_MISMATCH', 'reason': 'M1 视觉基线要求同步相机观测'})
        if len({o.camera_id for o in observations}) < 2:
            return result.model_copy(update={'status': 'INSUFFICIENT_GEOMETRY', 'reason': '基线要求至少两相机'})
        corrected = self.correction and calibration.use_refraction
        prior = request.prior_estimate
        if prior and prior.valid and prior.position_m is not None and prior.target_id == request.target_id:
            initial = np.array([*prior.position_m, prior.yaw_rad or 0])
        else:
            initial = self._initial(request, observations, cameras, markers, corrected)
        if initial is None:
            return result.model_copy(update={'status': 'INSUFFICIENT_GEOMETRY', 'reason': '射线交会病态'})
        initial[2] = np.clip(initial[2], -19.99, -.251)
        groups = []
        for camera_id in sorted({o.camera_id for o in observations}):
            subset = [o for o in observations if o.camera_id == camera_id]
            groups.append((cameras[camera_id], np.concatenate([marker_corners(markers[o.marker_id]) for o in subset]),
                           np.concatenate([np.asarray(o.corners_px) for o in subset])))

        def residual(parameters):
            rotation = yaw_rotation(parameters[3])
            values = []
            for camera, body, pixels in groups:
                points = body @ rotation.T + parameters[:3]
                projected = (flat_project_many(points, camera, calibration.optics) if corrected
                             else pinhole_many(points, camera))
                values.append((projected-pixels).ravel())
            return np.concatenate(values)

        try:
            solved = least_squares(residual, initial, bounds=([-100, -100, -20, -np.inf], [100, 100, -.25, np.inf]),
                                   max_nfev=40, ftol=1e-9, xtol=1e-9, gtol=1e-8)
            singular = np.linalg.svd(solved.jac, compute_uv=False)
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
            return result.model_copy(update={'status': 'SOLVER_FAILED', 'reason': str(exc)})
        if not solved.success or not np.all(np.isfinite(solved.x)):
            return result.model_copy(update={'status': 'SOLVER_FAILED', 'reason': str(solved.message)})
        if singular[-1] < 1e-5 or singular[0]/singular[-1] > 1e8:
            return result.model_copy(update={'status': 'INSUFFICIENT_GEOMETRY', 'reason': '重投影雅可比病态'})
        position, yaw = solved.x[:3], float(solved.x[3])
        lag = 0.
        if self.smoothing and request.target_id in self._history:
            previous = self._history[request.target_id]
            alpha = .35
            position = alpha*position + (1-alpha)*np.asarray(previous.position_m)
            lag = (1-alpha)/alpha * max(0., request.sim_time_s-previous.sim_time_s)
        result = result.model_copy(update={'valid': True, 'status': 'SUCCESS', 'position_m': tuple(position),
            'yaw_rad': yaw, 'orientation_wxyz': (float(np.cos(yaw/2)), 0., 0., float(np.sin(yaw/2))),
            'reprojection_rmse_px': float(np.sqrt(np.mean(solved.fun**2))),
            'used_measurement_ids': [o.measurement_id for o in observations], 'filter_lag_nominal_s': lag})
        self._history[request.target_id] = result
        return result

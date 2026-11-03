"""单界面 Snell 传播；波面交点由费马光程驻值求出。"""

from math import hypot

import numpy as np
from scipy.optimize import brentq, root

from app.contracts import BackprojectionRequest, ProjectionRequest, ProjectionResult, RayPath

from .geometry import camera_rotation, flat_intersections, pinhole_many, unit
from .wave import FlatSurface, SeededMultiSineSurface


def projection_result(point, camera, intersection, water_direction) -> ProjectionResult:
    """汇总有效光路与图像范围；范围外像素保留但 in_image=false。"""
    r = camera_rotation(camera)
    if (r @ (point - camera.position_m))[2] <= 0:
        return ProjectionResult(status='BEHIND_CAMERA')
    pixel = pinhole_many(np.asarray(point)[None, :], camera)[0]
    ray = RayPath(valid=True, status='SUCCESS', origin_world_m=camera.position_m,
                  intersection_world_m=None if intersection is None else tuple(intersection),
                  air_direction_world=tuple(unit(np.asarray(point)-camera.position_m)),
                  water_direction_world=tuple(water_direction))
    return ProjectionResult(valid=True, status='SUCCESS', pixel_px=tuple(pixel), ray=ray,
                            in_image=bool(0 <= pixel[0] < camera.width_px and 0 <= pixel[1] < camera.height_px))


class PinholeRefraction:
    """理想直线模型，用于理想模式与无校正估计。"""

    algorithm_id = 'pinhole_refraction_v1'
    algorithm_version = '1.0.0'

    def project(self, request: ProjectionRequest) -> ProjectionResult:
        """针孔正投影。"""
        p = np.asarray(request.point_world_m)
        if np.linalg.norm(p-request.camera.position_m) < 1e-12:
            return ProjectionResult(status='POINT_AT_CAMERA_CENTER')
        return projection_result(p, request.camera, None, unit(p-request.camera.position_m))

    def backproject(self, request: BackprojectionRequest) -> RayPath:
        """理想像素射线，不存在折射交点。"""
        c = request.camera
        u, v = request.pixel_px
        d = unit(camera_rotation(c).T @ np.array([(u-c.cx_px)/c.fx_px, (v-c.cy_px)/c.fy_px, 1]))
        return RayPath(valid=True, status='SUCCESS', origin_world_m=c.position_m,
                       air_direction_world=tuple(d), water_direction_world=tuple(d))


class SnellRefraction:
    """波面由模型实例持有；估计器只能建立 FlatSurface 实例。"""

    algorithm_id = 'snell_single_interface_v1'
    algorithm_version = '1.0.0'

    def __init__(self, surface=None):
        """允许生成器使用真实波面，基线估计器独立使用平均平面。"""
        self.surface = surface or FlatSurface()
        # 第三方波面始终走公开的 sample 契约。
        self._height_gradient = (self.surface.height_gradient if type(self.surface) is SeededMultiSineSurface
                                 else self._sample_height_gradient)

    def _sample_height_gradient(self, x, y, time):
        sample = self.surface.sample(x, y, time)
        return sample.height_m, *sample.gradient

    def project(self, request: ProjectionRequest) -> ProjectionResult:
        """求满足 Snell 条件的界面交点，再投影空气段。"""
        p = np.asarray(request.point_world_m)
        c = np.asarray(request.camera.position_m)
        time = request.sim_time_s
        if p[2] >= self._height_gradient(*p[:2], time)[0] or c[2] <= 0:
            return ProjectionResult(status='INVALID_MEDIA_GEOMETRY')
        q = flat_intersections(p[None, :], request.camera, request.optics)[0]
        if not isinstance(self.surface, FlatSurface):
            px, py, pz = p.tolist()
            cx, cy, cz = c.tolist()
            nw, na = request.optics.n_water, request.optics.n_air

            # 费马光程 L=nw|Q-P|+na|Q-C| 对界面参数 x,y 的梯度为零。
            def gradient(xy):
                x, y = xy.tolist()
                height, gx, gy = self._height_gradient(x, y, time)
                wx, wy, wz = x-px, y-py, height-pz
                ax, ay, az = x-cx, y-cy, height-cz
                water_length, air_length = hypot(wx, wy, wz), hypot(ax, ay, az)
                if min(water_length, air_length) < 1e-12:
                    raise ValueError('不能归一化零向量')
                water_scale, air_scale = nw/water_length, na/air_length
                dz = water_scale*wz + air_scale*az
                return (water_scale*wx + air_scale*ax + dz*gx,
                        water_scale*wy + air_scale*ay + dz*gy)

            result = root(gradient, q[:2], tol=1e-9)
            if not result.success or np.linalg.norm(gradient(result.x)) > 1e-7:
                return ProjectionResult(status='SURFACE_SOLVER_FAILED')
            q = np.array([*result.x, self._height_gradient(*result.x, time)[0]])
            # 检查直线段中没有额外穿越波面，避免把多次折射当单界面路径。
            for endpoint, above in [(c, True), (p, False)]:
                for fraction in (.25, .5, .75):
                    test = q + fraction*(endpoint-q)
                    h = self._height_gradient(*test[:2], time)[0]
                    if (above and test[2] < h-1e-8) or (not above and test[2] > h+1e-8):
                        return ProjectionResult(status='MULTIPLE_INTERSECTIONS')
        return projection_result(q, request.camera, q, unit(p-q))

    def backproject(self, request: BackprojectionRequest) -> RayPath:
        """沿空气射线求界面交点，以向量 Snell 定律进入水中。"""
        c = request.camera
        direction = PinholeRefraction().backproject(request).air_direction_world
        d = np.asarray(direction)
        origin = np.asarray(c.position_m)
        if d[2] >= -1e-8:
            return RayPath(status='NO_SURFACE_INTERSECTION')

        def distance_to_surface(s):
            q = origin + s*d
            return q[2] - self.surface.sample(*q[:2], request.sim_time_s).height_m

        upper = (origin[2]+.1)/-d[2]
        try:
            along = brentq(distance_to_surface, 0, upper)
        except ValueError:
            return RayPath(status='NO_SURFACE_INTERSECTION')
        q = origin + along*d
        normal = np.asarray(self.surface.sample(*q[:2], request.sim_time_s).normal_world)
        cosine = -float(d@normal)
        eta = request.optics.n_air/request.optics.n_water
        discriminant = 1 - eta*eta*(1-cosine*cosine)
        if cosine <= 0 or discriminant < 0:
            return RayPath(status='TOTAL_INTERNAL_REFLECTION_OR_BACKFACE')
        water = unit(eta*d + (eta*cosine-np.sqrt(discriminant))*normal)
        return RayPath(valid=True, status='SUCCESS', origin_world_m=c.position_m,
                       intersection_world_m=tuple(q), air_direction_world=tuple(d),
                       water_direction_world=tuple(water))

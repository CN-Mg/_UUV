"""固定种子的参数化波面，不作水动力学标定声明。"""

from math import cos, sin, sqrt

import numpy as np

from app.contracts import SurfaceSample, WaveConfig


class FlatSurface:
    """平均水面 z=0。"""

    algorithm_id = 'flat_surface_v1'
    algorithm_version = '1.0.0'

    def sample(self, x_m: float, y_m: float, sim_time_s: float) -> SurfaceSample:
        """返回常高、零坡度平面。"""
        return SurfaceSample(height_m=0, gradient=(0, 0), normal_world=(0, 0, 1))

    def sample_grid(self, xs, ys, sim_time_s):
        """可选批量加速，与逐点 sample 完全相同，不改变数学状态。"""
        heights = np.zeros((len(ys), len(xs)))
        normals = np.zeros((*heights.shape, 3))
        normals[:, :, 2] = 1
        return heights, normals


class SeededMultiSineSurface:
    """各相机共享同一组相位；采样不推进 RNG 状态。"""

    algorithm_id = 'seeded_multisine_v1'
    algorithm_version = '1.0.0'

    def __init__(self, config: WaveConfig, seed: int):
        """相位只在初始化时生成，振幅均分且绝对值总和为配置上界。"""
        self.amplitudes = np.full(len(config.wavelengths_m), config.amplitude_m / len(config.wavelengths_m))
        k = 2 * np.pi / np.array(config.wavelengths_m)
        self.kx = k * np.cos(config.directions_rad)
        self.ky = k * np.sin(config.directions_rad)
        self.omega = 2 * np.pi / np.array(config.periods_s)
        self.phase = np.random.default_rng(seed).uniform(0, 2*np.pi, len(k))
        self._components = tuple(zip(*(values.tolist() for values in
            (self.amplitudes, self.kx, self.ky, self.omega, self.phase)), strict=True))

    def sample(self, x_m: float, y_m: float, sim_time_s: float) -> SurfaceSample:
        """显式计算 ∂h/∂x、∂h/∂y 并归一化界面法向量。"""
        h, gx, gy = self.height_gradient(x_m, y_m, sim_time_s)
        length = sqrt(1 + gx*gx + gy*gy)
        return SurfaceSample(height_m=h, gradient=(gx, gy), normal_world=(-gx/length, -gy/length, 1/length))

    def height_gradient(self, x_m: float, y_m: float, sim_time_s: float) -> tuple[float, float, float]:
        """返回高度与两个偏导，供内置折射求解器的迭代内环使用。"""
        h = gx = gy = 0.
        for amplitude, kx, ky, omega, phase0 in self._components:
            phase = kx*x_m + ky*y_m - omega*sim_time_s + phase0
            h += amplitude*sin(phase)
            slope = amplitude*cos(phase)
            gx += kx*slope
            gy += ky*slope
        return h, gx, gy

    def sample_grid(self, xs, ys, sim_time_s):
        """同一组系数批量采样显示网格；无独立显示波场、无 RNG 推进。"""
        x, y = np.meshgrid(xs, ys)
        phase = (x[:, :, None]*self.kx + y[:, :, None]*self.ky
                 - self.omega*sim_time_s + self.phase)
        heights = np.sum(self.amplitudes*np.sin(phase), axis=-1)
        gx = np.sum(self.amplitudes*self.kx*np.cos(phase), axis=-1)
        gy = np.sum(self.amplitudes*self.ky*np.cos(phase), axis=-1)
        normals = np.stack((-gx, -gy, np.ones_like(gx)), axis=-1)
        normals /= np.linalg.norm(normals, axis=-1)[:, :, None]
        return heights, normals

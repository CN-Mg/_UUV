"""共享的算法边界校验；API 与运行调度复用，不实现研究优化/融合。"""

import math

from pydantic import BaseModel

from app.contracts import FusionContext, LayoutRequest, LayoutResult, VisionEstimate


def layout_constraint_violations(request: LayoutRequest, cameras) -> list[str]:
    """检查输出数量、身份、位置和架高约束，不把不可行布局当最优结果。"""
    violations = []
    if not cameras:
        violations.append('没有相机布局')
    if request.camera_count is not None and len(cameras) != request.camera_count:
        violations.append('相机数量不符')
    if len({c.camera_id for c in cameras}) != len(cameras):
        violations.append('相机 ID 重复')
    for camera in cameras:
        if camera.position_m[2] <= 0:
            violations.append(f'{camera.camera_id} 不在水面上方')
        if request.height_bounds_m and not request.height_bounds_m[0] <= camera.position_m[2] <= request.height_bounds_m[1]:
            violations.append(f'{camera.camera_id} 超出架高约束')
        if request.position_bounds_m and any(value < lo or value > hi for value, lo, hi in
                zip(camera.position_m, *request.position_bounds_m)):
            violations.append(f'{camera.camera_id} 超出位置约束')
    return violations


def validate_layout_result(request: LayoutRequest, result) -> LayoutResult:
    """重新解析适配器返回值，包括绕过 Pydantic 的 model_copy 更新结果。"""
    result = LayoutResult.model_validate(result.model_dump() if isinstance(result, BaseModel) else result)
    if result.optimization_status not in {'INVALID_LAYOUT', 'INFEASIBLE', 'FAILED'}:
        violations = layout_constraint_violations(request, result.cameras)
        if violations:
            raise ValueError('布局返回值违反约束：' + '；'.join(violations))
    return result


def validate_estimate_result(target_id: str, sim_time_s: float, result,
                             model_type=VisionEstimate, expected_algorithm_id: str | None = None,
                             allowed_measurement_ids: set[str] | None = None,
                             expected_algorithm_version: str | None = None):
    """拒绝错误版本、目标、时刻、坐标、有限性和未知测量来源的算法输出。"""
    parsed = model_type.model_validate(result.model_dump() if isinstance(result, BaseModel) else result)
    if parsed.target_id != target_id or not math.isclose(parsed.sim_time_s, sim_time_s, abs_tol=1e-6, rel_tol=0):
        raise ValueError('算法输出目标或参考时刻与请求不一致')
    if expected_algorithm_id is not None and parsed.algorithm_id != expected_algorithm_id:
        raise ValueError('算法输出 ID 与所选实现不一致')
    if expected_algorithm_version is not None and parsed.algorithm_version != expected_algorithm_version:
        raise ValueError('算法输出版本与所选实现不一致')
    if allowed_measurement_ids is not None and not set(parsed.used_measurement_ids) <= allowed_measurement_ids:
        raise ValueError('算法输出声称使用了请求中不存在的测量')
    return parsed


def validate_measurement_calibration(observation, context: FusionContext) -> None:
    """校验已知时钟映射与原始来源说明，不宣称完成未知设备时钟估计。"""
    if observation.source_clock_id is not None:
        clock = observation.source_clock_id
        if clock not in context.clock_offsets_s:
            raise ValueError(f'缺少设备时钟 {clock} 的已知映射')
        mapped = observation.source_time_s*context.clock_scales.get(clock, 1.) + context.clock_offsets_s[clock]
        if not math.isclose(mapped, observation.measurement_time_s,
                            abs_tol=context.alignment_tolerance_s, rel_tol=0):
            raise ValueError('原始设备时间与声明的仿真观测时刻不一致')
    source_frame = observation.source_frame_id
    if source_frame and source_frame != 'LOCAL_TANK_RH' and source_frame not in context.sensor_extrinsics:
        raise ValueError(f'缺少来源坐标系 {source_frame} 的标定外参')

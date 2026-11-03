"""显式注册工厂；场景只选择已注册 ID，不执行任意代码。"""

from app.contracts import AdapterDescriptor

from .baselines import BufferedRangeSource, FixedLayoutAdapter, NoOpFusion
from .interfaces import (
    AcousticRangeSource,
    FusionLocalizer,
    LayoutOptimizer,
    RefractionModel,
    VisionLocalizer,
    WaveSurfaceModel,
)
from .refraction import PinholeRefraction, SnellRefraction
from .vision import LeastSquaresLocalizer
from .wave import FlatSurface, SeededMultiSineSurface

REGISTRY = {
    'layout': {'fixed_layout_v1': lambda **kw: FixedLayoutAdapter()},
    'vision': {
        'pinhole_baseline_v1': lambda **kw: LeastSquaresLocalizer('pinhole_baseline_v1', correction=False),
        'flat_snell_baseline_v1': lambda **kw: LeastSquaresLocalizer(),
        'flat_snell_smoothed_v1': lambda **kw: LeastSquaresLocalizer('flat_snell_smoothed_v1', smoothing=True),
    },
    'refraction': {'snell_single_interface_v1': lambda **kw: SnellRefraction(kw.get('surface')),
                   'pinhole_refraction_v1': lambda **kw: PinholeRefraction()},
    'wave': {'seeded_multisine_v1': lambda **kw: SeededMultiSineSurface(kw['config'], kw['seed']),
             'flat_surface_v1': lambda **kw: FlatSurface()},
    'acoustic': {'buffered_ranges_v1': lambda **kw: BufferedRangeSource()},
    'fusion': {'noop_fusion_v1': lambda **kw: NoOpFusion()},
}

PROTOCOLS = {'layout': LayoutOptimizer, 'vision': VisionLocalizer, 'refraction': RefractionModel,
             'wave': WaveSurfaceModel, 'acoustic': AcousticRangeSource, 'fusion': FusionLocalizer}
DESCRIPTORS = {}
for _role, _entries in REGISTRY.items():
    for _name in _entries:
        _caps = {'layout': ['geometric_coverage', 'configured_layout_passthrough'],
                 'vision': ['analytic_marker_xyz_yaw', 'synchronous_observations'],
                 'refraction': ['project', 'backproject'], 'wave': ['height', 'gradient', 'normal'],
                 'acoustic': ['buffered_input'], 'fusion': ['visual_passthrough_only']}[_role]
        DESCRIPTORS[(_role, _name)] = AdapterDescriptor(role=_role, algorithm_id=_name,
            algorithm_version='1.0.0', capabilities=_caps,
            status='NOT_OPTIMIZED' if _role == 'layout' else 'PASSTHROUGH_NOT_FUSED' if _role == 'fusion' else 'BASELINE')


def register_adapter(role: str, algorithm_id: str, factory, *, algorithm_version: str,
                     supported_schema_versions=('1.0',), capabilities=(), replace=False) -> None:
    """研究员显式注册工厂与能力，拒绝无意覆盖已有实现和不支持的契约版本。"""
    if role not in REGISTRY or not algorithm_id or not algorithm_version:
        raise ValueError('角色、算法 ID 和版本必须明确')
    if algorithm_id in REGISTRY[role] and not replace:
        raise ValueError('算法 ID 已注册；主动替换须指定 replace=True')
    if '1.0' not in supported_schema_versions:
        raise ValueError('当前调度只支持 schema_version=1.0')
    descriptor = AdapterDescriptor(role=role, algorithm_id=algorithm_id, algorithm_version=algorithm_version,
        supported_schema_versions=list(supported_schema_versions), capabilities=list(capabilities), status='EXTERNAL_ADAPTER')
    REGISTRY[role][algorithm_id] = factory
    DESCRIPTORS[(role, algorithm_id)] = descriptor


def create_adapter(role: str, algorithm_id: str, **kwargs):
    """创建声明的适配器；未知 ID 明确拒绝，不静默降级。"""
    if role not in REGISTRY or algorithm_id not in REGISTRY[role]:
        raise ValueError(f'未知适配器 {role}:{algorithm_id}')
    schema_version = kwargs.pop('schema_version', '1.0')
    descriptor = DESCRIPTORS.get((role, algorithm_id))
    if schema_version != '1.0' or (descriptor and schema_version not in descriptor.supported_schema_versions):
        raise ValueError('适配器不支持请求契约版本')
    adapter = REGISTRY[role][algorithm_id](**kwargs)
    if not isinstance(adapter, PROTOCOLS[role]):
        raise ValueError(f'{role}:{algorithm_id} 没有实现对应协议的全部入口')
    if getattr(adapter, 'algorithm_id', None) != algorithm_id:
        raise ValueError('适配器自身 algorithm_id 与注册 ID 不一致')
    if descriptor and getattr(adapter, 'algorithm_version', None) != descriptor.algorithm_version:
        raise ValueError('适配器实现版本与注册声明不一致')
    return adapter


def catalog() -> list[dict]:
    """返回已注册算法的角色、版本、证据状态和占位标识。"""
    return [DESCRIPTORS[(role, name)].model_dump(mode='json') if (role, name) in DESCRIPTORS else
            {'role': role, 'algorithm_id': name, 'algorithm_version': 'UNREPORTED',
             'schema_version': '1.0', 'supported_schema_versions': ['1.0'], 'capabilities': [],
             'status': 'UNDECLARED_TEST_ADAPTER', 'evidence_status': 'DEMO_UNCALIBRATED'}
            for role, entries in REGISTRY.items() for name in entries]

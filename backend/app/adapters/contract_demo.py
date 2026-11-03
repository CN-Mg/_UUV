"""无需前端的三模块接入烟测；只输出基线，不宣称正式研究成果。"""

import json

from app.contracts import CameraObservation, LayoutRequest, ScenarioConfig, VisionRequest
from app.simulation.engine import SimulationEngine

from .baselines import FixedLayoutAdapter
from .vision import LeastSquaresLocalizer


def main() -> None:
    """依次展示布局、视觉输入/输出及 NoOp 透传。"""
    config = ScenarioConfig()
    engine = SimulationEngine(config)
    events = engine.step(0)
    observations = [CameraObservation.model_validate(p) for kind, p in events if kind == 'camera_observation']
    request = VisionRequest(target_id='UUV-001', sim_time_s=0, observations=observations, calibration=engine.calibration)
    estimate = LeastSquaresLocalizer().localize(request)
    result = {
        'evidence_status': 'DEMO_UNCALIBRATED',
        'layout': FixedLayoutAdapter().optimize(LayoutRequest(tank=config.tank, cameras=config.cameras)).model_dump(mode='json'),
        'vision': estimate.model_dump(mode='json'),
        'fusion': next(p for kind, p in events if kind == 'fusion_estimate'),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

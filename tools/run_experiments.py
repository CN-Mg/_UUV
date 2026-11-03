"""预先固定的小型演示实验；保留失败运行，不选择有利种子。"""

import json
import sys
import time

from app.contracts import ScenarioConfig
from app.services.runtime import ROOT, TERMINAL, RunManager


def main() -> None:
    """运行理想、平面、有波和噪声对照；结果属于未标定机制演示。"""
    manager = RunManager()
    specs = [("ideal", "IDEAL_NO_REFRACTION", 0., 20261102, 0.),
             ("flat", "FLAT_SNELL_REFRACTION", 0., 20261102, 0.)]
    specs += [(f"wave-{amplitude}-{seed}", "WAVY_SNELL_REFRACTION", amplitude, seed, 0.)
              for amplitude in [.01, .02] for seed in [20261102, 20261103, 20261104]]
    specs.append(("pixel-noise", "FLAT_SNELL_REFRACTION", 0., 20261102, .5))
    report = {"evidence_status": "DEMO_UNCALIBRATED", "python_executable": sys.executable,
              "preregistered_cases": specs, "duration_s": 3., "results": []}
    output = ROOT / "data" / "experiments"
    output.mkdir(exist_ok=True)
    # 新命名空间保留每次运行，重复执行不会覆盖原结果。
    namespace = output / time.strftime("m1-%Y%m%d-%H%M%S")
    namespace.mkdir(exist_ok=False)
    (namespace / "plan.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    try:
        for name, mode, amplitude, seed, noise in specs:
            raw = ScenarioConfig().model_dump(mode="json")
            raw.update(mode=mode, duration_s=3., seed=seed, pixel_noise_std_px=noise)
            raw["wave"]["amplitude_m"] = amplitude
            state = manager.create(ScenarioConfig.model_validate(raw))
            state.control("speed", 16)
            while state.status not in TERMINAL:
                state.thread.join(.5)
            state.thread.join()
            row = {"case": name, "run_id": state.run_id, "status": state.status,
                   "mode": mode, "amplitude_m": amplitude, "seed": seed,
                   "pixel_noise_std_px": noise, "metrics": state.metrics()}
            report["results"].append(row)
            (namespace / "results.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(name, state.status, state.run_id, flush=True)
        print("RESULT", namespace, flush=True)
    finally:
        manager.close()


if __name__ == "__main__":
    main()

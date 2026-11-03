"""导出公开模型 JSON Schema；供同学无需 GUI 即可联调接口。"""

import argparse
import json
from pathlib import Path

import app.contracts as contracts
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]


def build_schemas() -> dict:
    """构造命名公开契约集合；不导入 API、存储或启动仿真。"""
    return {
        name: model.model_json_schema() for name in sorted(dir(contracts))
        if isinstance(model := getattr(contracts, name), type)
        and issubclass(model, BaseModel) and name not in {'BaseModel', 'Contract'}
    }


def main() -> None:
    """从后端权威模型导出命名模型集合。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='只检查已导出契约是否与代码一致')
    args = parser.parse_args()
    schemas = build_schemas()
    output = ROOT / "docs" / "contracts.schema.json"
    if args.check:
        if not output.exists() or json.loads(output.read_text(encoding='utf-8')) != schemas:
            raise SystemExit('契约已变化，请先重新导出 tools/export_contracts.py')
        print('公共契约 JSON Schema 与后端一致')
        return
    output.write_text(json.dumps(schemas, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()

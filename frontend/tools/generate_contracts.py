"""从后端 Pydantic 契约生成前端有效配置与事件类型；不生成定位算法。"""

import argparse
import importlib
import json
import sys
from pathlib import Path


def ts_type(schema: dict) -> str:
    """将本项目使用的 JSON Schema 类型投影成 TypeScript。"""
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]
    if "const" in schema:
        return json.dumps(schema["const"], ensure_ascii=False)
    if "enum" in schema:
        return " | ".join(json.dumps(v, ensure_ascii=False) for v in schema["enum"])
    if "anyOf" in schema:
        return " | ".join(ts_type(v) for v in schema["anyOf"])
    kind = schema.get("type")
    if kind in {"number", "integer"}:
        return "number"
    if kind == "string":
        return "string"
    if kind == "boolean":
        return "boolean"
    if kind == "null":
        return "null"
    if kind == "array":
        if "prefixItems" in schema:
            return "[" + ", ".join(ts_type(v) for v in schema["prefixItems"]) + "]"
        return f"Array<{ts_type(schema.get('items', {}))}>"
    if kind == "object":
        if "properties" in schema:
            return "{ " + "; ".join(f"{key}: {ts_type(v)}" for key, v in schema["properties"].items()) + " }"
        additional = schema.get("additionalProperties", {})
        value_type = ts_type(additional) if isinstance(additional, dict) else "unknown"
        return f"Record<string, {value_type}>"
    return "unknown"


def generate() -> str:
    """使用后端有效配置的全部默认字段，避免前后端手写两份契约。"""
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "backend"))
    contracts = importlib.import_module("app.contracts")
    models = [contracts.ScenarioConfig, contracts.EventEnvelope, contracts.WaterSurfaceSnapshot]
    definitions = {}
    for model in models:
        schema = model.model_json_schema(mode="serialization")
        definitions.update(schema.pop("$defs", {}))
        definitions[model.__name__] = schema
    lines = [
        "// 自动生成：frontend/tools/generate_contracts.py；请修改后端模型后重新生成。",
        "// 这是 model_dump 后有效配置/响应的类型，含已补齐的默认值；不是宽松输入类型。",
        "",
    ]
    for name, schema in sorted(definitions.items()):
        description = schema.get("description", "后端契约投影").replace("*/", "")
        lines.append(f"/** {description} */")
        lines.append(f"export type {name} = {ts_type(schema)}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    """生成文件，或在 --check 下拒绝与后端模型不一致的文件。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[1] / "src" / "generated-contracts.ts"
    expected = generate()
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != expected:
            raise SystemExit("前端契约类型已过期，请执行 frontend/tools/generate_contracts.py")
        print("Frontend contracts match backend Pydantic schemas")
    else:
        target.write_text(expected, encoding="utf-8")
        print(f"Generated {target}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Kotlin Instruction 파일을 스캔해 instructionMetadata.ts 스니펫을 생성한다.

Usage:
  python3 scan_instruction.py <kotlin_file> [ec_code_file]

자동으로 탐지하는 패턴:
  - ctx.requestOptions["key"]          → requestInputs 후보
  - throw BaseException(EcCode.X, ...) → possibleErrors 후보
  - // @schema <type> <desc> (SlotDefinition 바로 위) → outputSchema 후보
"""
import re
import sys
from pathlib import Path


def find_ec_code_file(start: Path) -> Path | None:
    for ancestor in [start, *start.parents]:
        for candidate in ancestor.rglob("EcCode.kt"):
            return candidate
    return None


def parse_ec_codes(ec_code_path: Path) -> dict:
    codes = {}
    content = ec_code_path.read_text(encoding="utf-8")
    # 패턴: CODE_NAME(9401, "description", ...)
    for m in re.finditer(r'([A-Z_]{4,})\s*\(\s*(\d+)\s*,\s*"([^"]*)"', content):
        codes[m.group(1)] = {"errorCode": int(m.group(2)), "description": m.group(3)}
    return codes


def parse_request_options(content: str) -> list[dict]:
    results = []
    seen = set()
    # ctx.requestOptions["key"] as? Type  또는  ctx.requestOptions["key"]!!
    pattern = re.compile(r'ctx\.requestOptions\["([^"]+)"\](?:\s*as\??\s*(\w[\w<>?]+))?')
    for m in pattern.finditer(content):
        key = m.group(1)
        if key in seen:
            continue
        seen.add(key)

        kt_type = (m.group(2) or "String").split("<")[0].rstrip("?")
        ts_type = {"String": "string", "Int": "number", "Long": "number",
                   "Double": "number", "Boolean": "boolean", "Map": "object"}.get(kt_type, "string")

        # required 판단: 뒤에 ?: throw / !! 가 있으면 필수
        tail = content[m.start(): min(m.end() + 120, len(content))]
        required = bool(re.search(r'\?\s*:\s*throw|!!', tail))

        results.append({"key": key, "type": ts_type, "required": required})
    return results


def parse_possible_errors(content: str) -> list[str]:
    seen = set()
    codes = []
    for m in re.finditer(r'BaseException\s*\(\s*EcCode\.([A-Z_]+)', content):
        code = m.group(1)
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def extract_instruction_name(content: str, fallback: str) -> str:
    m = re.search(r'override val name\s*=\s*"([^"]+)"', content)
    return m.group(1) if m else fallback


# ── outputSchema 파싱 ──────────────────────────────────────────────────────────

def parse_type_string(type_str: str) -> dict:
    """
    간단한 타입 문자열을 OutputFieldSchema dict로 변환.

    지원 형식:
      string | number | boolean | object | array
      array<string>
      array<{k1:t1, k2:t2}>
      {k1:t1, k2:t2}
      map<string>   → Record<string, string>
    """
    type_str = type_str.strip()

    # map<T> → {type: 'object', items: T} (Record 표현)
    m = re.match(r'^map<(.+)>$', type_str, re.IGNORECASE)
    if m:
        inner = m.group(1).strip()
        return {"type": "object", "items": parse_type_string(inner)}

    # array<...>
    m = re.match(r'^array<(.+)>$', type_str, re.IGNORECASE)
    if m:
        inner = m.group(1).strip()
        return {"type": "array", "items": parse_type_string(inner)}

    # {k1:t1, k2:t2}
    m = re.match(r'^\{(.+)\}$', type_str)
    if m:
        props = {}
        for entry in re.split(r',\s*', m.group(1)):
            kv = entry.strip().split(":", 1)
            if len(kv) == 2:
                k, v = kv[0].strip(), kv[1].strip()
                props[k] = parse_type_string(v)
        return {"type": "object", "properties": props}

    # primitives
    primitives = {"string", "number", "boolean", "object", "array"}
    t = type_str.lower()
    return {"type": t if t in primitives else "string"}


def schema_to_ts(schema: dict, indent: int = 6) -> str:
    """OutputFieldSchema dict → TypeScript 객체 문자열 (중첩 지원)."""
    pad = " " * indent
    inner_pad = " " * (indent + 2)

    parts = [f"type: '{schema['type']}'"]

    if "description" in schema:
        parts.append(f"description: '{schema['description']}'")

    lines = ["{"]
    lines.append(f"{inner_pad}" + f",\n{inner_pad}".join(parts) + ",")

    if "items" in schema:
        lines.append(f"{inner_pad}items: {schema_to_ts(schema['items'], indent + 2)},")

    if "properties" in schema:
        lines.append(f"{inner_pad}properties: {{")
        for k, v in schema["properties"].items():
            lines.append(f"{inner_pad}  {k}: {schema_to_ts(v, indent + 4)},")
        lines.append(f"{inner_pad}}},")

    lines.append(f"{pad}}}")
    return "\n".join(lines)


def parse_output_schemas(content: str) -> dict[str, dict]:
    """
    outputSlots() 블록 안에서
      // @schema <type_string> [설명]
      SlotDefinition("slotName", ...)
    패턴을 찾아 {slotName: schema_dict} 반환.
    """
    schemas = {}
    lines = content.splitlines()

    for i, line in enumerate(lines):
        m = re.match(r'\s*//\s*@schema\s+(\S+)(?:\s+(.+))?', line)
        if not m:
            continue
        type_str = m.group(1)
        description = (m.group(2) or "").strip()

        # 다음 비어있지 않은 줄에서 SlotDefinition 찾기
        for j in range(i + 1, min(i + 4, len(lines))):
            slot_m = re.search(r'SlotDefinition\s*\(\s*"([^"]+)"', lines[j])
            if slot_m:
                slot_name = slot_m.group(1)
                schema = parse_type_string(type_str)
                if description:
                    schema["description"] = description
                schemas[slot_name] = schema
                break

    return schemas


# ── TypeScript 스니펫 생성 ─────────────────────────────────────────────────────

def generate_ts(request_inputs: list, possible_errors: list, ec_codes: dict,
                output_schemas: dict) -> str:
    lines = []

    if request_inputs:
        lines.append("    requestInputs: [")
        for inp in request_inputs:
            req = "true" if inp["required"] else "false"
            lines.append(f"      reqInput('bodyFields', '{inp['key']}', '{inp['type']}', {req}, '/* TODO: 설명 */'),")
        lines.append("    ],")
    else:
        lines.append("    requestInputs: [],")

    if possible_errors:
        lines.append("    possibleErrors: [")
        for code in possible_errors:
            ec = ec_codes.get(code, {})
            error_code = ec.get("errorCode", "/* TODO */")
            description = ec.get("description", "/* TODO */")
            lines.append(f"      {{ code: '{code}', errorCode: {error_code}, description: '{description}' }},")
        lines.append("    ],")
    else:
        lines.append("    possibleErrors: [],")

    if output_schemas:
        lines.append("    outputSchema: {")
        for slot_name, schema in output_schemas.items():
            lines.append(f"      {slot_name}: {schema_to_ts(schema, 6)},")
        lines.append("    },")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("사용법: scan_instruction.py <kotlin_file> [ec_code_file]")
        sys.exit(1)

    kt_path = Path(sys.argv[1])
    if not kt_path.exists():
        print(f"파일을 찾을 수 없음: {kt_path}")
        sys.exit(1)

    ec_code_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else find_ec_code_file(kt_path.parent)

    ec_codes = parse_ec_codes(ec_code_path) if ec_code_path and ec_code_path.exists() else {}
    content = kt_path.read_text(encoding="utf-8")
    instruction_name = extract_instruction_name(content, kt_path.stem)
    request_inputs = parse_request_options(content)
    possible_errors = parse_possible_errors(content)
    output_schemas = parse_output_schemas(content)

    print(f"\n{'='*60}")
    print(f"Instruction: {instruction_name}  ({kt_path.name})")
    if ec_code_path:
        print(f"EcCode:      {ec_code_path}")
    print(f"{'='*60}")

    print("\n[requestInputs] — ctx.requestOptions 탐지")
    if request_inputs:
        for inp in request_inputs:
            req = "필수" if inp["required"] else "선택"
            print(f"  {inp['key']}: {inp['type']} ({req})")
    else:
        print("  (없음)")

    print("\n[possibleErrors] — throw BaseException(EcCode.X) 탐지")
    if possible_errors:
        for code in possible_errors:
            ec = ec_codes.get(code, {})
            print(f"  {code}: errorCode={ec.get('errorCode', '?')}, \"{ec.get('description', '?')}\"")
    else:
        print("  (없음)")

    print("\n[outputSchema] — // @schema 주석 탐지")
    if output_schemas:
        for slot_name, schema in output_schemas.items():
            print(f"  {slot_name}: {schema.get('type', '?')} — {schema.get('description', '')}")
    else:
        print("  (없음) ← outputSlots() 위에 // @schema 주석을 추가하면 자동 생성됩니다")

    print("\n[생성된 TypeScript 스니펫] — instructionMetadata.ts에 붙여넣기")
    print("-" * 60)
    print(generate_ts(request_inputs, possible_errors, ec_codes, output_schemas))
    print("-" * 60)

    if any("/* TODO */" in l for l in generate_ts(request_inputs, possible_errors, ec_codes, output_schemas)):
        print("\n⚠  TODO 항목이 있습니다. 수동으로 확인 후 채워주세요.")


if __name__ == "__main__":
    main()

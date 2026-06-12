"""Validate params chiến thuật theo `param_schema` (cho UI + API).

Schema mỗi key: {type: "int"|"float", min?: số, max?: số, default?: số}.
Trả về dict đã ép kiểu + điền default; raise ValueError nếu sai kiểu/ngoài khoảng.
"""


class ParamError(ValueError):
    pass


def validate_params(schema: dict, params: dict) -> dict:
    out: dict = {}
    for key, spec in schema.items():
        raw = params.get(key, spec.get("default"))
        if raw is None:
            raise ParamError(f"thiếu param '{key}'")
        ptype = spec.get("type", "float")
        try:
            val = int(raw) if ptype == "int" else float(raw)
        except (TypeError, ValueError) as e:
            raise ParamError(f"param '{key}' phải là {ptype}") from e
        if "min" in spec and val < spec["min"]:
            raise ParamError(f"param '{key}'={val} < min {spec['min']}")
        if "max" in spec and val > spec["max"]:
            raise ParamError(f"param '{key}'={val} > max {spec['max']}")
        out[key] = val
    # giữ các key ngoài schema (không bắt buộc khai báo) nguyên trạng
    for k, v in params.items():
        if k not in out:
            out[k] = v
    return out

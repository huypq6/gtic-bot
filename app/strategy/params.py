"""Validate strategy params against `param_schema` (for the UI + API).

Schema per key: {type: "int"|"float", min?: number, max?: number, default?: number}.
Returns a dict with values coerced + defaults filled in; raises ValueError on a wrong type
or an out-of-range value.
"""


class ParamError(ValueError):
    pass


def validate_params(schema: dict, params: dict) -> dict:
    out: dict = {}
    for key, spec in schema.items():
        raw = params.get(key, spec.get("default"))
        if raw is None:
            raise ParamError(f"missing param '{key}'")
        ptype = spec.get("type", "float")
        try:
            val = int(raw) if ptype == "int" else float(raw)
        except (TypeError, ValueError) as e:
            raise ParamError(f"param '{key}' must be {ptype}") from e
        if "min" in spec and val < spec["min"]:
            raise ParamError(f"param '{key}'={val} < min {spec['min']}")
        if "max" in spec and val > spec["max"]:
            raise ParamError(f"param '{key}'={val} > max {spec['max']}")
        out[key] = val
    # keep keys outside the schema (declaring them is optional) as-is
    for k, v in params.items():
        if k not in out:
            out[k] = v
    return out

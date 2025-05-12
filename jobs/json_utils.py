import json

def to_json(data, pretty=False):
    try:
        if pretty:
            return json.dumps(data, indent=2, sort_keys=True)
        return json.dumps(data)
    except (TypeError, ValueError) as e:
        raise RuntimeError(f"JSON serialization error: {e}")

def from_json(json_str):
    try:
        return json.loads(json_str)
    except (TypeError, ValueError) as e:
        raise RuntimeError(f"JSON deserialization error: {e}") 
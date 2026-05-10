from pathlib import Path

import yaml

from .models import Schema


def load_schema(path: str | Path) -> Schema:
    with open(path) as f:
        data = yaml.safe_load(f)
    return Schema.model_validate(data)

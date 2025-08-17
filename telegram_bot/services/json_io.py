from __future__ import annotations

from typing import Any
import orjson


def json_load(path: str) -> Any:
    with open(path, 'rb') as f:
        return orjson.loads(f.read())


def json_dump(path: str, data: Any) -> None:
    with open(path, 'wb') as f:
        f.write(orjson.dumps(data))



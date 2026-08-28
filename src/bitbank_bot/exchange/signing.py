from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def hmac_sha256(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def compact_json(body: dict[str, Any]) -> str:
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False)


def sign_get(secret: str, nonce: str, path_with_query: str) -> str:
    return hmac_sha256(secret, nonce + path_with_query)


def sign_post(secret: str, nonce: str, body_json: str) -> str:
    return hmac_sha256(secret, nonce + body_json)

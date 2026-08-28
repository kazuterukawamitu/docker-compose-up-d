"""Bitbank HMAC-SHA256 signing (ACCESS-TIME-WINDOW and ACCESS-NONCE)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Mapping


def unix_ms() -> int:
    return int(time.time() * 1000)


def compact_json(body: Mapping[str, Any]) -> str:
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False)


def sign(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def sign_get_nonce(secret: str, nonce: str, path_with_query: str) -> str:
    return sign(secret, f"{nonce}{path_with_query}")


def sign_post_nonce(secret: str, nonce: str, body: str) -> str:
    return sign(secret, f"{nonce}{body}")


def sign_get_time_window(secret: str, request_time: str, time_window: str, path_with_query: str) -> str:
    return sign(secret, f"{request_time}{time_window}{path_with_query}")


def sign_post_time_window(secret: str, request_time: str, time_window: str, body: str) -> str:
    return sign(secret, f"{request_time}{time_window}{body}")


def private_headers_get(
    api_key: str,
    api_secret: str,
    path_with_query: str,
    *,
    time_window_ms: int = 5000,
) -> dict[str, str]:
    request_time = str(unix_ms())
    window = str(time_window_ms)
    signature = sign_get_time_window(api_secret, request_time, window, path_with_query)
    return {
        "ACCESS-KEY": api_key,
        "ACCESS-REQUEST-TIME": request_time,
        "ACCESS-TIME-WINDOW": window,
        "ACCESS-SIGNATURE": signature,
    }


def private_headers_post(
    api_key: str,
    api_secret: str,
    body: str,
    *,
    time_window_ms: int = 5000,
) -> dict[str, str]:
    request_time = str(unix_ms())
    window = str(time_window_ms)
    signature = sign_post_time_window(api_secret, request_time, window, body)
    return {
        "ACCESS-KEY": api_key,
        "ACCESS-REQUEST-TIME": request_time,
        "ACCESS-TIME-WINDOW": window,
        "ACCESS-SIGNATURE": signature,
        "Content-Type": "application/json",
    }

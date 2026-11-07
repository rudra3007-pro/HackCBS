"""
CycloSense — Lightweight In-Memory Rate Limiter
Prevents DoS flooding on CPU-intensive ML inference and LLM endpoints.
"""

import time
import threading
from functools import wraps
from flask import request, jsonify

_rate_limit_lock = threading.Lock()
_request_history = {}  # { ip_address: [timestamp, ...] }

def _get_client_ip():
    """Extract client IP respecting X-Forwarded-For if behind a proxy."""
    if request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


def rate_limit(max_per_minute: int = 30):
    """
    Sliding window rate limit decorator.
    
    Args:
        max_per_minute: Maximum allowed requests per IP within 60 seconds.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            ip = _get_client_ip()
            now = time.time()
            window_start = now - 60.0

            with _rate_limit_lock:
                timestamps = _request_history.get(ip, [])
                # Prune timestamps older than 60s
                valid_timestamps = [t for t in timestamps if t > window_start]

                if len(valid_timestamps) >= max_per_minute:
                    retry_after = int(60.0 - (now - valid_timestamps[0])) + 1
                    return jsonify({
                        "error": "Rate limit exceeded. Too many requests.",
                        "limit_per_minute": max_per_minute,
                        "retry_after_seconds": max(1, retry_after)
                    }), 429

                valid_timestamps.append(now)
                _request_history[ip] = valid_timestamps

                # Periodically clean up stale IPs if history grows large
                if len(_request_history) > 1000:
                    for k in list(_request_history.keys()):
                        if not _request_history[k] or _request_history[k][-1] < window_start:
                            del _request_history[k]

            return fn(*args, **kwargs)
        return wrapper
    return decorator


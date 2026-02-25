"""Tests for trusted client IP extraction with signed headers."""

import hmac
from hashlib import sha256
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.main as m


class _DummyRequest:
    def __init__(self, headers=None, host: str = "203.0.113.10"):
        self.headers = headers or {}
        self.client = SimpleNamespace(host=host)


def _build_sig(secret: str, ip: str, ts: str) -> str:
    return hmac.new(secret.encode("utf-8"), f"{ip}.{ts}".encode("utf-8"), sha256).hexdigest()


def test_signed_ip_is_used(monkeypatch):
    monkeypatch.setattr(m, "PROXY_SIGNING_SECRET", "test-secret")
    monkeypatch.setattr(m, "SIGNED_IP_WINDOW_SECONDS", 60)
    ts = str(int(time.time()))
    ip = "198.51.100.7"
    req = _DummyRequest(
        headers={
            "X-Arcbrief-Client-Ip": ip,
            "X-Arcbrief-Client-Ts": ts,
            "X-Arcbrief-Client-Sig": _build_sig("test-secret", ip, ts),
            "X-Forwarded-For": "1.1.1.1",
        },
        host="203.0.113.5",
    )
    assert m._client_ip(req) == ip


def test_invalid_signature_falls_back_to_client_host(monkeypatch):
    monkeypatch.setattr(m, "PROXY_SIGNING_SECRET", "test-secret")
    monkeypatch.setattr(m, "SIGNED_IP_WINDOW_SECONDS", 60)
    ts = str(int(time.time()))
    req = _DummyRequest(
        headers={
            "X-Arcbrief-Client-Ip": "198.51.100.7",
            "X-Arcbrief-Client-Ts": ts,
            "X-Arcbrief-Client-Sig": "bad-signature",
            "X-Forwarded-For": "1.1.1.1",
        },
        host="203.0.113.5",
    )
    assert m._client_ip(req) == "203.0.113.5"


def test_expired_signature_falls_back_to_client_host(monkeypatch):
    monkeypatch.setattr(m, "PROXY_SIGNING_SECRET", "test-secret")
    monkeypatch.setattr(m, "SIGNED_IP_WINDOW_SECONDS", 1)
    ts = str(int(time.time()) - 10)
    ip = "198.51.100.7"
    req = _DummyRequest(
        headers={
            "X-Arcbrief-Client-Ip": ip,
            "X-Arcbrief-Client-Ts": ts,
            "X-Arcbrief-Client-Sig": _build_sig("test-secret", ip, ts),
        },
        host="203.0.113.5",
    )
    assert m._client_ip(req) == "203.0.113.5"


def test_spoofed_xff_is_ignored_without_valid_signature(monkeypatch):
    monkeypatch.setattr(m, "PROXY_SIGNING_SECRET", "test-secret")
    monkeypatch.setattr(m, "SIGNED_IP_WINDOW_SECONDS", 60)
    req = _DummyRequest(
        headers={"X-Forwarded-For": "8.8.8.8"},
        host="203.0.113.5",
    )
    assert m._client_ip(req) == "203.0.113.5"

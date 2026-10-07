"""Gửi nhịp hoạt động của phiên hiện tại lên Worker, không giữ khóa ở ổ đĩa."""
from __future__ import annotations

import secrets
import threading
import time

import requests


class PresenceClient:
    def __init__(self, app):
        self.app = app
        self.session_id = None
        self.username = None
        self.key = None
        self.sequence = 0
        self.last_tick = None
        self.job = None

    def _request(self, route, data):
        base = self.app.API_BASE_URL

        def send():
            try:
                requests.post(f'{base}{route}', json=data, timeout=5)
            except requests.RequestException:
                pass  # Tạm mất mạng: nhịp tiếp theo tự thử lại.
        threading.Thread(target=send, daemon=True).start()

    def start(self, username, key):
        self.stop()
        self.username, self.key = username, key
        self.session_id = secrets.token_hex(16)
        self.sequence = 0
        self.last_tick = time.monotonic()
        self._beat(0)
        self.job = self.app.after(60000, self._tick)

    def _beat(self, active_seconds):
        if self.session_id is None:
            return
        self._request('/api/activity/heartbeat', {
            'username': self.username, 'key': self.key,
            'session_id': self.session_id, 'sequence': self.sequence,
            'active_seconds': active_seconds,
        })
        self.sequence += 1

    def _tick(self):
        if self.session_id is None:
            return
        now = time.monotonic()
        elapsed = max(0.0, min(60.0, now - self.last_tick))
        self.last_tick = now
        self._beat(elapsed if self.app.focus_displayof() is not None else 0)
        self.job = self.app.after(60000, self._tick)

    def stop(self):
        if self.job is not None:
            try:
                self.app.after_cancel(self.job)
            except Exception:
                pass
            self.job = None
        if self.session_id is not None:
            self._request('/api/activity/logout', {
                'username': self.username, 'key': self.key,
                'session_id': self.session_id,
            })
        self.session_id = self.username = self.key = self.last_tick = None

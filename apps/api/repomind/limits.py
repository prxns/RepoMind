"""Bounded admission control for public POST requests."""

import time
from collections import OrderedDict, deque
from threading import Lock


class PostRateLimiter:
    def __init__(self, per_client: int, global_limit: int, max_clients: int = 1024):
        if min(per_client, global_limit, max_clients) < 1:
            raise ValueError("Rate limits must be positive.")
        self.per_client = per_client
        self.global_limit = global_limit
        self.max_clients = max_clients
        self.clients: OrderedDict[str, deque[float]] = OrderedDict()
        self.global_window: deque[float] = deque()
        self.lock = Lock()

    def allow(self, client: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        cutoff = now - 60
        with self.lock:
            while self.global_window and self.global_window[0] <= cutoff:
                self.global_window.popleft()
            # Idle entries are removed before the hard key limit is checked.
            for key, stored_window in list(self.clients.items()):
                if not stored_window or stored_window[-1] <= cutoff:
                    del self.clients[key]
            if len(self.global_window) >= self.global_limit:
                return False
            window = self.clients.get(client)
            if window is None:
                if len(self.clients) >= self.max_clients:
                    return False
                window = deque()
                self.clients[client] = window
            while window and window[0] <= cutoff:
                window.popleft()
            if len(window) >= self.per_client:
                return False
            window.append(now)
            self.global_window.append(now)
            return True

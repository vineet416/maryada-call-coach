"""Event log of one session: monotonic seq, t_ms since call start, fan-out to WebSocket listeners."""
import asyncio
import time


class EventLog:
    def __init__(self) -> None:
        self.events: list[dict] = []  # the full ordered envelope stream (also what the recorder saves)
        self._t0 = time.perf_counter()
        self._waiters: list[asyncio.Event] = []
        self.done = False

    def now_ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)

    def emit(self, type_: str, data: dict) -> dict:
        env = {"seq": len(self.events) + 1, "type": type_, "t_ms": self.now_ms(), "data": data}
        self.events.append(env)
        self._wake()
        return env

    def push(self, env: dict) -> None:
        """Append a recorded envelope unchanged (replay keeps seq and t_ms as recorded)."""
        self.events.append(env)
        self._wake()

    def close(self) -> None:
        self.done = True
        self._wake()

    def _wake(self) -> None:
        for w in self._waiters:
            w.set()

    async def follow(self, last_seq: int = 0):
        """Yield envelopes with seq > last_seq, then new ones until the session is closed (resume uses last_seq)."""
        w = asyncio.Event()
        self._waiters.append(w)
        try:
            i = last_seq
            while True:
                while i < len(self.events):
                    yield self.events[i]
                    i += 1
                if self.done:
                    return
                w.clear()
                await w.wait()
        finally:
            self._waiters.remove(w)

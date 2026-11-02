"""Validated runtime knobs for bounded delivery under shared congestion."""

from __future__ import annotations

import os
from dataclasses import dataclass
from collections.abc import Mapping


@dataclass(frozen=True)
class Config:
    write_limit: int = 1024
    max_queue: int = 16
    compression: str | None = "deflate"
    finals_cap: int = 512
    delivery: str = "semantic"
    backlog: int = 4096

    def serve_kwargs(self):
        return {
            "backlog": self.backlog,
            "write_limit": self.write_limit,
            "max_queue": self.max_queue,
            "compression": self.compression,
        }

    def delivery_config(self):
        from .hub import DeliveryConfig

        return DeliveryConfig(
            finals_cap=self.finals_cap,
            write_limit=self.write_limit,
            delivery=self.delivery,
        )


def load_from_env(env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env

    def positive(name, default):
        raw = env.get(name, str(default))
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a positive integer") from exc
        if value < 1:
            raise ValueError(f"{name} must be a positive integer")
        return value

    compression = env.get("LR_COMPRESSION", "deflate")
    delivery = env.get("LR_DELIVERY", "semantic")
    if compression not in ("none", "deflate"):
        raise ValueError("LR_COMPRESSION must be none or deflate")
    if delivery not in ("semantic", "fifo"):
        raise ValueError("LR_DELIVERY must be semantic or fifo")
    return Config(
        write_limit=positive("LR_WRITE_LIMIT", 1024),
        max_queue=positive("LR_MAX_QUEUE", 16),
        finals_cap=positive("LR_FINALS_CAP", 512),
        compression=None if compression == "none" else compression,
        delivery=delivery,
    )


CONFIG = load_from_env()

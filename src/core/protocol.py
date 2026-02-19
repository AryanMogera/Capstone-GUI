# src/core/protocol.py

from __future__ import annotations
from typing import Dict, Any, Optional
import json

ParsedPacket = Dict[str, Any]


def parse_packet(line: str) -> Optional[ParsedPacket]:
    """
    Parse a newline-delimited JSON telemetry packet.

    Expected keys (all optional):
      - v    : list of cell voltages
      - tc   : list of temperatures
      - i    : pack current (A)
      - soc  : 0..1 float
      - fault: integer bitfield
    """
    try:
        data = json.loads(line)
        if not isinstance(data, dict):
            return None
        return data
    except json.JSONDecodeError:
        return None

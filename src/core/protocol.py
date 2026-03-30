# src/core/protocol.py

from __future__ import annotations
from typing import Dict, Any, Optional
import json

ParsedPacket = Dict[str, Any]

def parse_packet(line: str) -> Optional[ParsedPacket]:
    """
    Parse newline-delimited JSON telemetry packet from STM32.

    Expected (recommended) keys:
      - s     : int state (0..7)
      - v     : list[float] length 4 (series-group voltages)
      - tc    : list[float] length 8 (temps; 2 per series group: A,B)
      - i     : float pack current (A)
      - soc   : float 0..1
      - fault : int bitfield
    """
    try:
        data = json.loads(line)
        if not isinstance(data, dict):
            return None
        return data
    except json.JSONDecodeError:
        return None
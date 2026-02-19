# src/core/serial_worker.py

from __future__ import annotations

from typing import Dict, Any

from PySide6 import QtCore
import serial

from .protocol import parse_packet, ParsedPacket


class SerialWorker(QtCore.QObject):
    """
    Runs in a QThread, reads newline-delimited JSON packets from the STM32
    and emits them to the GUI.
    """

    packet = QtCore.Signal(dict)   # ParsedPacket
    status = QtCore.Signal(str)

    def __init__(self, port: str, baud: int = 115200) -> None:
        super().__init__()
        self._port = port
        self._baud = baud
        self._stop = False
        self._ser: serial.Serial | None = None

    @QtCore.Slot()
    def run(self) -> None:
        try:
            self._ser = serial.Serial(self._port, self._baud, timeout=1)
            self.status.emit(f"Connected to {self._port}")
        except Exception as e:
            self.status.emit(f"Connection failed: {e}")
            return

        while not self._stop:
            try:
                line = self._ser.readline()
                if not line:
                    continue
                text = line.decode("utf-8", errors="ignore").strip()
                pkt: ParsedPacket | None = parse_packet(text)
                if pkt is not None:
                    self.packet.emit(pkt)
            except Exception:
                # ignore parse/IO errors for now; could be logged
                continue

        if self._ser and self._ser.is_open:
            self._ser.close()
        self.status.emit("Disconnected")

    def stop(self) -> None:
        self._stop = True

    def send_command(self, payload: str) -> None:
        """
        Send a JSON command line to the MCU.
        The GUI is responsible for passing valid JSON strings.
        """
        if not self._ser or not self._ser.is_open:
            return

        if not payload.endswith("\n"):
            payload += "\n"

        try:
            self._ser.write(payload.encode("utf-8"))
        except Exception:
            # swallow errors for now
            pass

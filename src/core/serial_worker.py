# # -----------------------------
# # src/core/serial_worker.py
# # -----------------------------
# from __future__ import annotations
# from typing import Optional
# from PySide6 import QtCore      #type: ignore
# import serial                   #type: ignore

# from .protocol import parse_packet, ParsedPacket

# class SerialWorker(QtCore.QObject):
#     """
#     Runs in a QThread, reads newline-delimited JSON packets from STM32,
#     and emits them to the GUI.
#     """
#     packet = QtCore.Signal(dict)   # ParsedPacket
#     status = QtCore.Signal(str)

#     def __init__(self, port: str, baud: int = 115200) -> None:
#         super().__init__()
#         self._port = port
#         self._baud = baud
#         self._stop = False
#         self._ser: Optional[serial.Serial] = None

#     @QtCore.Slot()
#     def run(self) -> None:
#         try:
#             self._ser = serial.Serial(self._port, self._baud, timeout=1)
#             self.status.emit(f"Connected to {self._port} @ {self._baud}")
#         except Exception as e:
#             self.status.emit(f"Connection failed: {e}")
#             return

#         while not self._stop:
#             try:
#                 raw = self._ser.readline()
#                 if not raw:
#                     continue
#                 text = raw.decode("utf-8", errors="ignore").strip()
#                 pkt: ParsedPacket | None = parse_packet(text)
#                 if pkt is not None:
#                     self.packet.emit(pkt)
#             except Exception:
#                 continue

#         try:
#             if self._ser and self._ser.is_open:
#                 self._ser.close()
#         except Exception:
#             pass
#         self.status.emit("Disconnected")

#     def stop(self) -> None:
#         self._stop = True


# src/core/serial_worker.py
from __future__ import annotations
from typing import Optional
from PySide6 import QtCore  # type: ignore
import serial  # type: ignore

from .protocol import parse_packet, ParsedPacket

class SerialWorker(QtCore.QObject):
    packet = QtCore.Signal(dict)
    status = QtCore.Signal(str)

    # NEW: GUI -> worker thread command signal
    send_cmd = QtCore.Signal(str)

    def __init__(self, port: str, baud: int = 115200) -> None:
        super().__init__()
        self._port = port
        self._baud = baud
        self._stop = False
        self._ser: Optional[serial.Serial] = None

        # NEW: connect signal to slot (queued across threads)
        self.send_cmd.connect(self._on_send_cmd)

    @QtCore.Slot()
    def run(self) -> None:
        try:
            self._ser = serial.Serial(self._port, self._baud, timeout=1)
            self.status.emit(f"Connected to {self._port} @ {self._baud}")
        except Exception as e:
            self.status.emit(f"Connection failed: {e}")
            return

        while not self._stop:
            try:
                raw = self._ser.readline()
                if not raw:
                    continue
                text = raw.decode("utf-8", errors="ignore").strip()
                pkt: ParsedPacket | None = parse_packet(text)
                if pkt is not None:
                    self.packet.emit(pkt)
            except Exception:
                continue

        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
        except Exception:
            pass
        self.status.emit("Disconnected")

    @QtCore.Slot(str)
    def _on_send_cmd(self, cmd: str) -> None:
        """Runs in the worker thread; safe place to write to serial."""
        try:
            if not self._ser or not self._ser.is_open:
                return
            line = (cmd.strip() + "\n").encode("utf-8")
            self._ser.write(line)
            self._ser.flush()
        except Exception as e:
            self.status.emit(f"TX failed: {e}")

    def stop(self) -> None:
        self._stop = True

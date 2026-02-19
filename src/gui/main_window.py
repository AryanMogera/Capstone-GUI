# src/gui/main_window.py

from __future__ import annotations

import json
import math
from typing import List, Dict, Any

from PySide6 import QtWidgets, QtCore
import serial.tools.list_ports as list_ports

from core.serial_worker import SerialWorker

# ---- local config (so we don't depend on core.config) ----
DEFAULT_BAUD = 115200
DEMO_MODE = True   # set False later when using real hardware


class MainWindow(QtWidgets.QWidget):
    """Top-level BMS GUI window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Modular Sodium-Ion BMS – GUI")

        # --- widgets ---
        self.portBox = QtWidgets.QComboBox()
        self.refreshBtn = QtWidgets.QPushButton("Refresh")
        self.connectBtn = QtWidgets.QPushButton("Connect")
        self.statusLab = QtWidgets.QLabel("Disconnected")

        # 4S2P-friendly headers
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Series Group", "Voltage (V)", "Temp (°C) (Cell A / Cell B)"])
        self.table.horizontalHeader().setStretchLastSection(True)

        self.packLab = QtWidgets.QLabel("Pack I: -- A | SOC: -- % | Fault: 0x00")
        self.balEnableChk = QtWidgets.QCheckBox("Enable Balancing")

        # --- layout ---
        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Port:"))
        top.addWidget(self.portBox)
        top.addWidget(self.refreshBtn)
        top.addWidget(self.connectBtn)
        top.addStretch(1)
        top.addWidget(self.statusLab)

        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(self.balEnableChk)
        controls.addStretch(1)

        main = QtWidgets.QVBoxLayout(self)
        main.addLayout(top)
        main.addWidget(self.table)
        main.addLayout(controls)
        main.addWidget(self.packLab)

        # --- background worker & demo timer ---
        self.workerThread: QtCore.QThread | None = None
        self.worker: SerialWorker | None = None

        self.demoTimer: QtCore.QTimer | None = None
        self._demoStep: int = 0

        # --- signals ---
        self.refreshBtn.clicked.connect(self.refreshPorts)
        self.connectBtn.clicked.connect(self.toggleConnection)
        self.balEnableChk.stateChanged.connect(self.onBalancingChanged)

        self.refreshPorts()

        # start demo mode if enabled
        if DEMO_MODE:
            self.startDemoMode()

    # ------------------------------------------------------------------
    # Serial port handling
    # ------------------------------------------------------------------

    def refreshPorts(self) -> None:
        """Populate the COM port dropdown."""
        self.portBox.clear()
        ports = [p.device for p in list_ports.comports()]
        self.portBox.addItems(ports)

    def toggleConnection(self) -> None:
        """
        Connect or disconnect from the STM32.
        When connecting to real hardware, demo mode is disabled.
        """
        # If currently connected, disconnect
        if self.workerThread:
            if self.worker:
                self.worker.stop()
            self.workerThread.quit()
            self.workerThread.wait()
            self.workerThread = None
            self.worker = None

            self.connectBtn.setText("Connect")
            self.statusLab.setText("Disconnected")

            # Optionally resume demo after disconnect
            if DEMO_MODE:
                self.startDemoMode()
            return

        # Start a real connection → stop demo
        if DEMO_MODE:
            self.stopDemoMode()

        port = self.portBox.currentText()
        if not port:
            self.statusLab.setText("No port selected")
            return

        self.worker = SerialWorker(port=port, baud=DEFAULT_BAUD)
        self.workerThread = QtCore.QThread(self)
        self.worker.moveToThread(self.workerThread)

        self.workerThread.started.connect(self.worker.run)
        self.worker.packet.connect(self.onPacket)
        self.worker.status.connect(self.statusLab.setText)

        self.workerThread.start()
        self.connectBtn.setText("Disconnect")

    # ------------------------------------------------------------------
    # Incoming packets
    # ------------------------------------------------------------------

    @QtCore.Slot(dict)
    def onPacket(self, pkt: Dict[str, Any]) -> None:
        """Handle a parsed telemetry packet from the worker or demo."""
        series_voltages: List[float] = pkt.get("v", [])   # length should be 4
        temps: List[float] = pkt.get("tc", [])            # length can be 8 (two per group)

        num_series = len(series_voltages)
        if num_series == 0:
            self.table.setRowCount(0)
            return

        self.table.setRowCount(num_series)

        for i in range(num_series):
            # Group label
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(f"S{i+1}"))

            # Voltage
            v_str = f"{series_voltages[i]:.3f}"
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(v_str))

            # Two temps per series group (Cell A / Cell B)
            t1 = temps[2 * i] if (2 * i) < len(temps) else None
            t2 = temps[2 * i + 1] if (2 * i + 1) < len(temps) else None

            if t1 is not None and t2 is not None:
                t_str = f"{t1:.1f} / {t2:.1f}"
            elif t1 is not None:
                t_str = f"{t1:.1f}"
            else:
                t_str = ""

            self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(t_str))

        pack_i = pkt.get("i")
        soc = pkt.get("soc")
        fault = int(pkt.get("fault", 0))

        if pack_i is not None and soc is not None:
            soc_pct = max(0.0, min(1.0, float(soc))) * 100.0
            self.packLab.setText(
                f"Pack I: {pack_i:.2f} A | SOC: {soc_pct:.0f} % | Fault: 0x{fault:02X}"
            )

    # ------------------------------------------------------------------
    # Commands from GUI → MCU
    # ------------------------------------------------------------------

    def onBalancingChanged(self, state: int) -> None:
        """Send a simple balancing enable/disable command to MCU."""
        if not self.worker:
            return
        enable = state == QtCore.Qt.CheckState.Checked
        cmd = {"cmd": "bal", "enable": enable}
        self.worker.send_command(json.dumps(cmd))

    # ------------------------------------------------------------------
    # Demo mode: mock data generator
    # ------------------------------------------------------------------

    def startDemoMode(self) -> None:
        """Start generating mock BMS data for demo/presentation."""
        if self.demoTimer is None:
            self.demoTimer = QtCore.QTimer(self)
            self.demoTimer.timeout.connect(self._demoTick)

        self._demoStep = 0
        self.demoTimer.start(500)  # update every 500 ms
        self.statusLab.setText("Demo mode: showing mock data")

    def stopDemoMode(self) -> None:
        if self.demoTimer is not None:
            self.demoTimer.stop()
            self.statusLab.setText("Disconnected")

    def _demoTick(self) -> None:
        """Generate a fake telemetry packet and feed it to onPacket()."""
        self._demoStep += 1

        num_series = 4   # 4S2P -> 4 series voltages
        num_temps = 8    # 8 cells -> 8 temps (2 per series group)

        base_v = 3.60

        series_voltages = [
            base_v + 0.03 * math.sin(self._demoStep / 8.0 + i * 0.6)
            for i in range(num_series)
        ]

        temps = [
            28.0 + i * 0.5 + 1.0 * math.sin(self._demoStep / 15.0 + i * 0.2)
            for i in range(num_temps)
        ]

        pack_current = 0.8 * math.sin(self._demoStep / 12.0)  # A
        soc = 0.5 + 0.4 * math.sin(self._demoStep / 50.0)    # 0..1
        soc = max(0.0, min(1.0, soc))

        pkt = {
            "v": series_voltages,  # length = 4
            "tc": temps,           # length = 8
            "i": pack_current,
            "soc": soc,
            "fault": 0,
        }

        self.onPacket(pkt)

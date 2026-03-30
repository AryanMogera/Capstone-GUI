# src/gui/main_window.py
from __future__ import annotations

import math
from collections import deque
import importlib
from typing import List, Dict, Any

from PySide6 import QtWidgets, QtCore
import serial.tools.list_ports as list_ports
pg = None

from core.serial_worker import SerialWorker

DEFAULT_BAUD = 115200
DEMO_MODE = True


class MainWindow(QtWidgets.QWidget):
    """Read-only BMS dashboard (telemetry viewer)."""
    MAX_GRAPH_POINTS = 240

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Modular Sodium-Ion BMS – Dashboard")
        self._sample_idx = 0
        self._x_hist: deque[int] = deque(maxlen=self.MAX_GRAPH_POINTS)
        self._voltage_hist: List[deque[float]] = []
        self._temp_hist: List[deque[float]] = []
        self._voltage_curves = []
        self._temp_curves = []

        # -------------------------
        # Top bar widgets
        # -------------------------
        self.portBox = QtWidgets.QComboBox()
        self.refreshBtn = QtWidgets.QPushButton("Refresh")
        self.connectBtn = QtWidgets.QPushButton("Connect")
        self.statusLab = QtWidgets.QLabel("Disconnected")

        # -------------------------
        # Main table (4S2P)
        # -------------------------
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Series Group", "Voltage (V)", "Temp A (°C)", "Temp B (°C)"]
        )
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)

        vheader = self.table.verticalHeader()
        vheader.setVisible(False)

        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.setWordWrap(False)
        self.table.setSortingEnabled(False)
        self.table.setSizeAdjustPolicy(
            QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        self.table.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.table.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.table.setStyleSheet("QTableWidget { border: 1px solid #e5e7eb; }")
        self.table.setRowCount(4)
        self.table.setVerticalHeaderLabels(["1", "2", "3", "4"])

        # -------------------------
        # Status + faults
        # -------------------------
        self.stateLab = QtWidgets.QLabel("State: --")
        self.chgLab = QtWidgets.QLabel("Charger: --")
        self.deepLab = QtWidgets.QLabel("Deep mode: --")
        self.packLab = QtWidgets.QLabel("Pack I: -- A | SOC: -- %")
        self.faultSummaryLab = QtWidgets.QLabel("Faults: --")

        self.faultBox = QtWidgets.QGroupBox("Fault Details")
        self.faultText = QtWidgets.QLabel("—")
        self.faultText.setWordWrap(True)
        faultLayout = QtWidgets.QVBoxLayout(self.faultBox)
        faultLayout.addWidget(self.faultText)

        # -------------------------
        # Graphs
        # -------------------------
        self.graphBox = QtWidgets.QGroupBox("Live Graphs")
        self.graphBox.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.graphBox.setMaximumHeight(320)
        graphLayout = QtWidgets.QVBoxLayout(self.graphBox)
        self._graphsRow = QtWidgets.QHBoxLayout()
        self._graphsRow.setSpacing(12)
        graphLayout.addLayout(self._graphsRow)
        self.graphStatusLab = QtWidgets.QLabel("Loading graphs…")
        graphLayout.addWidget(self.graphStatusLab)
        self.voltagePlot = None
        self.tempPlot = None

        # -------------------------
        # Layout
        # -------------------------
        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Port:"))
        top.addWidget(self.portBox)
        top.addWidget(self.refreshBtn)
        top.addWidget(self.connectBtn)
        top.addStretch(1)
        top.addWidget(self.statusLab)

        main = QtWidgets.QVBoxLayout(self)
        main.addLayout(top)
        main.addWidget(self.table, 3)
        main.addWidget(self.stateLab)
        main.addWidget(self.chgLab)
        main.addWidget(self.deepLab)
        main.addWidget(self.packLab)
        main.addWidget(self.faultSummaryLab)
        main.addWidget(self.faultBox)
        main.addWidget(self.graphBox, 0)

        # -------------------------
        # Worker thread + demo timer
        # -------------------------
        self.workerThread: QtCore.QThread | None = None
        self.worker: SerialWorker | None = None

        self.demoTimer: QtCore.QTimer | None = None
        self._demoStep = 0
        # When STM toggles MEASURE ↔ CHARGE/DISCHARGE quickly, show only Charge/Discharge.
        self._last_energy_display: str | None = None

        # -------------------------
        # Signals
        # -------------------------
        self.refreshBtn.clicked.connect(self.refreshPorts)
        self.connectBtn.clicked.connect(self.toggleConnection)

        self.refreshPorts()

        if DEMO_MODE:
            self.startDemoMode()

        # Lazy-load pyqtgraph/numpy after window shows (faster startup).
        QtCore.QTimer.singleShot(0, self._init_graphs)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _init_graphs(self) -> None:
        global pg
        if pg is None:
            try:
                pg = importlib.import_module("pyqtgraph")
            except Exception as e:
                self.graphStatusLab.setText(
                    f"Graphs unavailable: {e}\nInstall with: pip install pyqtgraph numpy"
                )
                return

        try:
            layout = self.graphBox.layout()
            if layout is None:
                return

            # Replace status label with plots
            self.graphStatusLab.deleteLater()

            self.voltagePlot = pg.PlotWidget(title="Series Voltages (V)")
            self.tempPlot = pg.PlotWidget(title="Temperature Channels (°C)")
            self._setup_plot(self.voltagePlot, y_label="Voltage (V)")
            self._setup_plot(self.tempPlot, y_label="Temp (°C)")
            self.voltagePlot.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )
            self.tempPlot.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            self.voltagePlot.setMinimumHeight(240)
            self.voltagePlot.setMaximumHeight(240)
            self.tempPlot.setMinimumHeight(240)
            self.tempPlot.setMaximumHeight(240)
            self._graphsRow.addWidget(self.voltagePlot, 1)
            self._graphsRow.addWidget(self.tempPlot, 1)
        except Exception as e:
            self.graphStatusLab.setText(
                f"Graphs failed to initialize: {e}"
            )

    def _setup_plot(self, plot_widget: Any, y_label: str) -> None:
        if pg is None:
            return
        plot_widget.setBackground("#ffffff")
        plot_widget.showGrid(x=True, y=True, alpha=0.2)
        plot_widget.setLabel("bottom", "Samples")
        plot_widget.setLabel("left", y_label)
        plot_widget.getAxis("left").setTextPen("#111827")
        plot_widget.getAxis("bottom").setTextPen("#111827")
        plot_widget.getPlotItem().getViewBox().setBorder(pg.mkPen("#d1d5db"))

    def _ensure_graph_channels(self, channel_count: int, is_voltage: bool) -> None:
        if pg is None or channel_count <= 0:
            return

        colors = [
            "#2563eb", "#16a34a", "#dc2626", "#9333ea",
            "#ea580c", "#0f766e", "#ca8a04", "#4f46e5",
            "#be185d", "#0891b2", "#65a30d", "#b91c1c",
        ]

        if is_voltage:
            if len(self._voltage_hist) >= channel_count:
                return
            for i in range(len(self._voltage_hist), channel_count):
                self._voltage_hist.append(deque(maxlen=self.MAX_GRAPH_POINTS))
                curve = self.voltagePlot.plot(
                    pen=pg.mkPen(colors[i % len(colors)], width=2),
                    name=f"S{i + 1}",
                )
                self._voltage_curves.append(curve)
        else:
            if len(self._temp_hist) >= channel_count:
                return
            for i in range(len(self._temp_hist), channel_count):
                self._temp_hist.append(deque(maxlen=self.MAX_GRAPH_POINTS))
                curve = self.tempPlot.plot(
                    pen=pg.mkPen(colors[i % len(colors)], width=2),
                    name=f"T{i + 1}",
                )
                self._temp_curves.append(curve)

    def _update_graphs(self, series_voltages: List[float], temps: List[float]) -> None:
        if pg is None:
            return

        self._sample_idx += 1
        self._x_hist.append(self._sample_idx)
        x_vals = list(self._x_hist)

        self._ensure_graph_channels(len(series_voltages), is_voltage=True)
        self._ensure_graph_channels(len(temps), is_voltage=False)

        for i, value in enumerate(series_voltages):
            self._voltage_hist[i].append(float(value))
            self._voltage_curves[i].setData(x_vals, list(self._voltage_hist[i]))

        for i, value in enumerate(temps):
            self._temp_hist[i].append(float(value))
            self._temp_curves[i].setData(x_vals, list(self._temp_hist[i]))

    def decode_faults(self, fault: int) -> List[str]:
        items: List[str] = []
        if fault & (1 << 0): items.append("Over-voltage")
        if fault & (1 << 1): items.append("Under-voltage")
        if fault & (1 << 2): items.append("Over-temperature")
        if fault & (1 << 3): items.append("Over-current")
        if fault & (1 << 4): items.append("Sensor fault")
        return items

    def state_name(self, s: int) -> str:
        # Match STM firmware (no BALANCING state): FAULT is 6.
        state_map = {
            0: "INIT",
            1: "STANDBY",
            2: "MEASURE",
            3: "CHARGING",
            4: "DISCHARGING",
            5: "DEEP DISCHARGING",
            6: "FAULT",
        }
        return state_map.get(s, "UNKNOWN")

    def _set_state_label_from_code(self, s_int: int) -> None:
        if s_int == 3:
            self._last_energy_display = "Charge"
            self.stateLab.setText("State: Charge")
            return
        if s_int == 4:
            self._last_energy_display = "Discharge"
            self.stateLab.setText("State: Discharge")
            return
        if s_int == 2:
            if self._last_energy_display is not None:
                self.stateLab.setText(f"State: {self._last_energy_display}")
            else:
                self.stateLab.setText("State: Measure")
            return
        self.stateLab.setText(f"State: {self.state_name(s_int)} (S={s_int})")

    # ------------------------------------------------------------------
    # Serial port handling
    # ------------------------------------------------------------------
    def refreshPorts(self) -> None:
        self.portBox.clear()
        ports = [p.device for p in list_ports.comports()]
        self.portBox.addItems(ports)

    def toggleConnection(self) -> None:
        # Disconnect
        if self.workerThread:
            if self.worker:
                self.worker.stop()
            self.workerThread.quit()
            self.workerThread.wait()
            self.workerThread = None
            self.worker = None

            self.connectBtn.setText("Connect")
            self.statusLab.setText("Disconnected")

            if DEMO_MODE:
                self.startDemoMode()
            return

        # Connect (real hardware)
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
        series_voltages: List[float] = pkt.get("v", []) or []
        temps: List[float] = pkt.get("tc", []) or []
        self._update_graphs(series_voltages, temps)

        # Table
        n = 4
        self.table.setRowCount(n)

        for i in range(n):
            it0 = QtWidgets.QTableWidgetItem(f"S{i+1}")
            it0.setTextAlignment(
                int(QtCore.Qt.AlignmentFlag.AlignVCenter)
                | int(QtCore.Qt.AlignmentFlag.AlignLeft)
            )
            self.table.setItem(i, 0, it0)

            v_val = series_voltages[i] if i < len(series_voltages) else None
            it1 = QtWidgets.QTableWidgetItem("" if v_val is None else f"{float(v_val):.3f}")
            it1.setTextAlignment(
                int(QtCore.Qt.AlignmentFlag.AlignVCenter)
                | int(QtCore.Qt.AlignmentFlag.AlignRight)
            )
            self.table.setItem(i, 1, it1)

            tA = temps[2 * i] if (2 * i) < len(temps) else None
            tB = temps[2 * i + 1] if (2 * i + 1) < len(temps) else None

            it2 = QtWidgets.QTableWidgetItem("" if tA is None else f"{float(tA):.1f}")
            it2.setTextAlignment(
                int(QtCore.Qt.AlignmentFlag.AlignVCenter)
                | int(QtCore.Qt.AlignmentFlag.AlignRight)
            )
            self.table.setItem(i, 2, it2)

            it3 = QtWidgets.QTableWidgetItem("" if tB is None else f"{float(tB):.1f}")
            it3.setTextAlignment(
                int(QtCore.Qt.AlignmentFlag.AlignVCenter)
                | int(QtCore.Qt.AlignmentFlag.AlignRight)
            )
            self.table.setItem(i, 3, it3)

            self.table.setRowHeight(i, 28)

        # State (supports either "s" or "st")
        s_val = pkt.get("s", None)
        if s_val is None:
            s_val = pkt.get("st", None)
        if s_val is not None:
            try:
                s_int = int(s_val)
                self._set_state_label_from_code(s_int)
            except Exception:
                self.stateLab.setText("State: --")

        # Charger / Deep mode
        chg = pkt.get("chg", None)
        deep = pkt.get("deep", None)

        if chg is not None:
            try:
                self.chgLab.setText(f"Charger: {'Connected' if int(chg) else 'Not connected'}")
            except Exception:
                self.chgLab.setText("Charger: --")

        if deep is not None:
            try:
                self.deepLab.setText(f"Deep mode: {'ON' if int(deep) else 'OFF'}")
            except Exception:
                self.deepLab.setText("Deep mode: --")

        # Pack info (SOC optional)
        pack_i = pkt.get("i", None)
        soc = pkt.get("soc", None)
        if pack_i is not None and soc is not None:
            try:
                soc_pct = max(0.0, min(1.0, float(soc))) * 100.0
                self.packLab.setText(f"Pack I: {float(pack_i):.2f} A | SOC: {soc_pct:.0f} %")
            except Exception:
                pass
        elif pack_i is not None:
            try:
                self.packLab.setText(f"Pack I: {float(pack_i):.2f} A | SOC: -- %")
            except Exception:
                pass

        # Faults
        try:
            fault = int(pkt.get("fault", 0))
        except Exception:
            fault = 0

        fault_list = self.decode_faults(fault)
        if not fault_list:
            self.faultSummaryLab.setText("Faults:  None")
            self.faultText.setText(" No faults detected.")
        else:
            self.faultSummaryLab.setText(f"Faults: {len(fault_list)} active (0x{fault:02X})")
            self.faultText.setText(" " + "\n ".join(fault_list))

    # ------------------------------------------------------------------
    # Demo mode
    # ------------------------------------------------------------------
    def startDemoMode(self) -> None:
        if self.demoTimer is None:
            self.demoTimer = QtCore.QTimer(self)
            self.demoTimer.timeout.connect(self._demoTick)

        self._demoStep = 0
        self.demoTimer.start(500)
        self.statusLab.setText("Demo mode: showing mock data")

    def stopDemoMode(self) -> None:
        if self.demoTimer is not None:
            self.demoTimer.stop()
        self.statusLab.setText("Disconnected")

    def _demoTick(self) -> None:
        self._demoStep += 1

        num_series = 4
        base_v = 3.60
        series_voltages = [
            base_v + 0.03 * math.sin(self._demoStep / 8.0 + i * 0.6)
            for i in range(num_series)
        ]

        temps = [
            28.0 + 0.8 * math.sin(self._demoStep / 10.0 + i * 0.35)
            for i in range(8)
        ]

        s = 3 if (self._demoStep // 20) % 2 == 0 else 4
        chg = 1 if s == 3 else 0

        # Simulate deep toggle occasionally
        deep = 1 if (self._demoStep // 60) % 2 == 1 else 0

        pkt = {
            "s": s,
            "v": series_voltages,
            "tc": temps,
            "i": 0.8 * math.sin(self._demoStep / 12.0),
            "soc": max(0.0, min(1.0, 0.5 + 0.4 * math.sin(self._demoStep / 50.0))),
            "chg": chg,
            "deep": deep,
            "fault": 0,
        }
        self.onPacket(pkt)
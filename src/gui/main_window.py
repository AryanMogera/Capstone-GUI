# # src/gui/main_window.py
# from __future__ import annotations

# import math
# import time
# from collections import deque
# import importlib
# from typing import List, Dict, Any

# from PySide6 import QtWidgets, QtCore
# import serial.tools.list_ports as list_ports
# pg = None

# from core.serial_worker import SerialWorker

# DEFAULT_BAUD = 115200
# DEMO_MODE = True
# # EMA blend each packet: lower = slower Pack I display (0 < alpha <= 1).
# PACK_I_DISPLAY_SMOOTH_ALPHA = 0.12

# # UART command to ask STM to clear faults / restart.
# # NOTE: change this string to whatever your STM UART command handler expects.
# STM_RESET_CMD = "RESET"

# # Deadband for current direction decisions (only used if `chg` is missing).
# ENERGY_I_DEADBAND_A = 0.15


# class MainWindow(QtWidgets.QWidget):
#     """Read-only BMS dashboard (telemetry viewer)."""
#     MAX_GRAPH_POINTS = 240

#     def __init__(self) -> None:
#         super().__init__()
#         self.setWindowTitle("Modular Sodium-Ion BMS – Dashboard")
#         self._sample_idx = 0
#         self._x_hist: deque[int] = deque(maxlen=self.MAX_GRAPH_POINTS)
#         self._voltage_hist: List[deque[float]] = []
#         self._temp_hist: List[deque[float]] = []
#         self._voltage_curves = []
#         self._temp_curves = []

#         # -------------------------
#         # Top bar widgets
#         # -------------------------
#         self.portBox = QtWidgets.QComboBox()
#         self.refreshBtn = QtWidgets.QPushButton("Refresh")
#         self.connectBtn = QtWidgets.QPushButton("Connect")
#         self.resetBtn = QtWidgets.QPushButton("Reset STM")
#         self.resetBtn.setEnabled(False)
#         self.statusLab = QtWidgets.QLabel("Disconnected")

#         # -------------------------
#         # Main table (4S2P)
#         # -------------------------
#         self.table = QtWidgets.QTableWidget(0, 4)
#         self.table.setHorizontalHeaderLabels(
#             ["Series Group", "Voltage (V)", "Temp A (°C)", "Temp B (°C)"]
#         )
#         header = self.table.horizontalHeader()
#         header.setStretchLastSection(False)
#         header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
#         header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
#         header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
#         header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)

#         vheader = self.table.verticalHeader()
#         vheader.setVisible(False)

#         self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
#         self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
#         self.table.setAlternatingRowColors(True)
#         self.table.setShowGrid(True)
#         self.table.setWordWrap(False)
#         self.table.setSortingEnabled(False)
#         self.table.setSizeAdjustPolicy(
#             QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents
#         )
#         self.table.setHorizontalScrollBarPolicy(
#             QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
#         )
#         self.table.setVerticalScrollBarPolicy(
#             QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
#         )
#         self.table.setStyleSheet("QTableWidget { border: 1px solid #e5e7eb; }")
#         self.table.setRowCount(4)
#         self.table.setVerticalHeaderLabels(["1", "2", "3", "4"])

#         # -------------------------
#         # Status + faults
#         # -------------------------
#         self.stateLab = QtWidgets.QLabel("State: --")
#         self.chgLab = QtWidgets.QLabel("Charger: --")
#         self.deepLab = QtWidgets.QLabel("Deep mode: --")
#         self.packLab = QtWidgets.QLabel("Pack I: --")
#         self.faultSummaryLab = QtWidgets.QLabel("Faults: --")

#         self.faultBox = QtWidgets.QGroupBox("Fault Details")
#         self.faultText = QtWidgets.QLabel("—")
#         self.faultText.setWordWrap(True)
#         faultLayout = QtWidgets.QVBoxLayout(self.faultBox)
#         faultLayout.addWidget(self.faultText)

#         # -------------------------
#         # Graphs
#         # -------------------------
#         self.graphBox = QtWidgets.QGroupBox("Live Graphs")
#         self.graphBox.setSizePolicy(
#             QtWidgets.QSizePolicy.Policy.Expanding,
#             QtWidgets.QSizePolicy.Policy.Fixed,
#         )
#         self.graphBox.setMaximumHeight(320)
#         graphLayout = QtWidgets.QVBoxLayout(self.graphBox)
#         self._graphsRow = QtWidgets.QHBoxLayout()
#         self._graphsRow.setSpacing(12)
#         graphLayout.addLayout(self._graphsRow)
#         self.graphStatusLab = QtWidgets.QLabel("Loading graphs…")
#         graphLayout.addWidget(self.graphStatusLab)
#         self.voltagePlot = None
#         self.tempPlot = None

#         # -------------------------
#         # Layout
#         # -------------------------
#         top = QtWidgets.QHBoxLayout()
#         top.addWidget(QtWidgets.QLabel("Port:"))
#         top.addWidget(self.portBox)
#         top.addWidget(self.refreshBtn)
#         top.addWidget(self.connectBtn)
#         top.addWidget(self.resetBtn)
#         top.addStretch(1)
#         top.addWidget(self.statusLab)

#         main = QtWidgets.QVBoxLayout(self)
#         main.addLayout(top)
#         main.addWidget(self.table, 3)
#         main.addWidget(self.stateLab)
#         main.addWidget(self.chgLab)
#         main.addWidget(self.deepLab)
#         main.addWidget(self.packLab)
#         main.addWidget(self.faultSummaryLab)
#         main.addWidget(self.faultBox)
#         main.addWidget(self.graphBox, 0)

#         # -------------------------
#         # Worker thread + demo timer
#         # -------------------------
#         self.workerThread: QtCore.QThread | None = None
#         self.worker: SerialWorker | None = None

#         self.demoTimer: QtCore.QTimer | None = None
#         self._demoStep = 0
#         # When STM toggles MEASURE ↔ CHARGE/DISCHARGE quickly, show only Charge/Discharge.
#         self._last_energy_display: str | None = None
#         self._pack_i_display_smooth: float | None = None

#         # -------------------------
#         # Signals
#         # -------------------------
#         self.refreshBtn.clicked.connect(self.refreshPorts)
#         self.connectBtn.clicked.connect(self.toggleConnection)
#         self.resetBtn.clicked.connect(self._on_reset_clicked)

#         self.refreshPorts()

#         if DEMO_MODE:
#             self.startDemoMode()

#         # Lazy-load pyqtgraph/numpy after window shows (faster startup).
#         QtCore.QTimer.singleShot(0, self._init_graphs)

#     # ------------------------------------------------------------------
#     # Helpers
#     # ------------------------------------------------------------------
#     def _init_graphs(self) -> None:
#         global pg
#         if pg is None:
#             try:
#                 pg = importlib.import_module("pyqtgraph")
#             except Exception as e:
#                 self.graphStatusLab.setText(
#                     f"Graphs unavailable: {e}\nInstall with: pip install pyqtgraph numpy"
#                 )
#                 return

#         try:
#             layout = self.graphBox.layout()
#             if layout is None:
#                 return

#             # Replace status label with plots
#             self.graphStatusLab.deleteLater()

#             self.voltagePlot = pg.PlotWidget(title="Series Voltages (V)")
#             self.tempPlot = pg.PlotWidget(title="Temperature Channels (°C)")
#             self._setup_plot(self.voltagePlot, y_label="Voltage (V)")
#             self._setup_plot(self.tempPlot, y_label="Temp (°C)")
#             self.voltagePlot.setSizePolicy(
#                 QtWidgets.QSizePolicy.Policy.Expanding,
#                 QtWidgets.QSizePolicy.Policy.Expanding,
#             )
#             self.tempPlot.setSizePolicy(
#                 QtWidgets.QSizePolicy.Policy.Expanding,
#                 QtWidgets.QSizePolicy.Policy.Fixed,
#             )
#             self.voltagePlot.setMinimumHeight(240)
#             self.voltagePlot.setMaximumHeight(240)
#             self.tempPlot.setMinimumHeight(240)
#             self.tempPlot.setMaximumHeight(240)
#             self._graphsRow.addWidget(self.voltagePlot, 1)
#             self._graphsRow.addWidget(self.tempPlot, 1)
#         except Exception as e:
#             self.graphStatusLab.setText(
#                 f"Graphs failed to initialize: {e}"
#             )

#     def _setup_plot(self, plot_widget: Any, y_label: str) -> None:
#         if pg is None:
#             return
#         plot_widget.setBackground("#ffffff")
#         plot_widget.showGrid(x=True, y=True, alpha=0.2)
#         plot_widget.setLabel("bottom", "Samples")
#         plot_widget.setLabel("left", y_label)
#         plot_widget.getAxis("left").setTextPen("#111827")
#         plot_widget.getAxis("bottom").setTextPen("#111827")
#         plot_widget.getPlotItem().getViewBox().setBorder(pg.mkPen("#d1d5db"))

#     def _ensure_graph_channels(self, channel_count: int, is_voltage: bool) -> None:
#         if pg is None or channel_count <= 0:
#             return

#         colors = [
#             "#2563eb", "#16a34a", "#dc2626", "#9333ea",
#             "#ea580c", "#0f766e", "#ca8a04", "#4f46e5",
#             "#be185d", "#0891b2", "#65a30d", "#b91c1c",
#         ]

#         if is_voltage:
#             if len(self._voltage_hist) >= channel_count:
#                 return
#             for i in range(len(self._voltage_hist), channel_count):
#                 self._voltage_hist.append(deque(maxlen=self.MAX_GRAPH_POINTS))
#                 curve = self.voltagePlot.plot(
#                     pen=pg.mkPen(colors[i % len(colors)], width=2),
#                     name=f"S{i + 1}",
#                 )
#                 self._voltage_curves.append(curve)
#         else:
#             if len(self._temp_hist) >= channel_count:
#                 return
#             for i in range(len(self._temp_hist), channel_count):
#                 self._temp_hist.append(deque(maxlen=self.MAX_GRAPH_POINTS))
#                 curve = self.tempPlot.plot(
#                     pen=pg.mkPen(colors[i % len(colors)], width=2),
#                     name=f"T{i + 1}",
#                 )
#                 self._temp_curves.append(curve)

#     def _update_graphs(self, series_voltages: List[float], temps: List[float]) -> None:
#         if pg is None:
#             return

#         self._sample_idx += 1
#         self._x_hist.append(self._sample_idx)
#         x_vals = list(self._x_hist)

#         self._ensure_graph_channels(len(series_voltages), is_voltage=True)
#         self._ensure_graph_channels(len(temps), is_voltage=False)

#         for i, value in enumerate(series_voltages):
#             self._voltage_hist[i].append(float(value))
#             self._voltage_curves[i].setData(x_vals, list(self._voltage_hist[i]))

#         for i, value in enumerate(temps):
#             self._temp_hist[i].append(float(value))
#             self._temp_curves[i].setData(x_vals, list(self._temp_hist[i]))

#     def decode_faults(self, fault: int) -> List[str]:
#         items: List[str] = []
#         if fault & (1 << 0): items.append("Over-voltage")
#         if fault & (1 << 1): items.append("Under-voltage")
#         if fault & (1 << 2): items.append("Over-temperature")
#         if fault & (1 << 3): items.append("Over-current")
#         if fault & (1 << 4): items.append("Sensor fault")
#         return items

#     def state_name(self, s: int) -> str:
#         # Match STM firmware (no BALANCING state): FAULT is 6.
#         state_map = {
#             0: "INIT",
#             1: "STANDBY",
#             2: "MEASURE",
#             3: "CHARGING",
#             4: "DISCHARGING",
#             5: "DEEP DISCHARGING",
#             6: "FAULT",
#         }
#         return state_map.get(s, "UNKNOWN")

#     def _set_state_label_from_code(
#         self,
#         s_int: int,
#         *,
#         chg_val: Any | None = None,
#         pack_i_val: Any | None = None,
#     ) -> None:
#         # Charge/Discharge are noisy around the transition (current crosses ~0),
#         # so if we have an explicit `chg` flag we trust it for display stability.
#         if s_int in (2, 3, 4):
#             if chg_val is not None:
#                 try:
#                     charging = int(chg_val) != 0
#                     self._last_energy_display = "Charge" if charging else "Discharge"
#                     self.stateLab.setText(f"State: {self._last_energy_display}")
#                     return
#                 except Exception:
#                     pass

#             # Fallback: use a deadband on current and keep the previous label.
#             if pack_i_val is not None:
#                 try:
#                     i_val = float(pack_i_val)
#                     if abs(i_val) < ENERGY_I_DEADBAND_A and self._last_energy_display is not None:
#                         self.stateLab.setText(f"State: {self._last_energy_display}")
#                         return
#                 except Exception:
#                     pass

#             # Last resort: basic mapping.
#             if s_int == 3:
#                 self._last_energy_display = "Charge"
#                 self.stateLab.setText("State: Charge")
#                 return
#             if s_int == 4:
#                 self._last_energy_display = "Discharge"
#                 self.stateLab.setText("State: Discharge")
#                 return
#             if s_int == 2:
#                 if self._last_energy_display is not None:
#                     self.stateLab.setText(f"State: {self._last_energy_display}")
#                 else:
#                     self.stateLab.setText("State: Measure")
#                 return

#         # Other states: show exact mapping.
#         self._last_energy_display = None
#         self.stateLab.setText(f"State: {self.state_name(s_int)} (S={s_int})")

#     def _sync_reset_button(self, *, fault_bits: int, s_int: int | None) -> None:
#         # Enable reset when we detect fault being active.
#         # If your STM uses a different fault code in `s`, update the `s_int == 6` check.
#         # Some firmwares use s==6, others use s==7 for FAULT.
#         in_fault = fault_bits != 0 or s_int in (6, 7)
#         connected = self.worker is not None and self.workerThread is not None
#         self.resetBtn.setEnabled(connected and in_fault)

#     @QtCore.Slot()
#     def _on_reset_clicked(self) -> None:
#         if self.worker is None:
#             self.statusLab.setText("Not connected (cannot reset STM)")
#             return
#         # Safe: signal is connected to SerialWorker in the worker thread.
#         self.resetBtn.setEnabled(False)
#         self.statusLab.setText(f"Sending reset: {STM_RESET_CMD}")
#         self.worker.send_cmd.emit(STM_RESET_CMD)

#     # ------------------------------------------------------------------
#     # Serial port handling
#     # ------------------------------------------------------------------
#     def refreshPorts(self) -> None:
#         self.portBox.clear()
#         ports = [p.device for p in list_ports.comports()]
#         self.portBox.addItems(ports)

#     def toggleConnection(self) -> None:
#         # Disconnect
#         if self.workerThread:
#             if self.worker:
#                 self.worker.stop()
#             self.workerThread.quit()
#             self.workerThread.wait()
#             self.workerThread = None
#             self.worker = None

#             self.connectBtn.setText("Connect")
#             self.statusLab.setText("Disconnected")
#             self.resetBtn.setEnabled(False)
#             self._pack_i_display_smooth = None

#             if DEMO_MODE:
#                 self.startDemoMode()
#             return

#         # Connect (real hardware)
#         if DEMO_MODE:
#             self.stopDemoMode()

#         port = self.portBox.currentText()
#         if not port:
#             self.statusLab.setText("No port selected")
#             return

#         self.worker = SerialWorker(port=port, baud=DEFAULT_BAUD)
#         self.workerThread = QtCore.QThread(self)
#         self.worker.moveToThread(self.workerThread)

#         self.workerThread.started.connect(self.worker.run)
#         self.worker.packet.connect(self.onPacket)
#         self.worker.status.connect(self.statusLab.setText)

#         self.workerThread.start()
#         self.connectBtn.setText("Disconnect")

#     # ------------------------------------------------------------------
#     # Incoming packets
#     # ------------------------------------------------------------------
#     @QtCore.Slot(dict)
#     def onPacket(self, pkt: Dict[str, Any]) -> None:
#         series_voltages: List[float] = pkt.get("v", []) or []
#         temps: List[float] = pkt.get("tc", []) or []
#         self._update_graphs(series_voltages, temps)

#         # Table
#         n = 4
#         self.table.setRowCount(n)

#         for i in range(n):
#             it0 = QtWidgets.QTableWidgetItem(f"S{i+1}")
#             it0.setTextAlignment(
#                 int(QtCore.Qt.AlignmentFlag.AlignVCenter)
#                 | int(QtCore.Qt.AlignmentFlag.AlignHCenter)
#             )
#             self.table.setItem(i, 0, it0)

#             v_val = series_voltages[i] if i < len(series_voltages) else None
#             it1 = QtWidgets.QTableWidgetItem("" if v_val is None else f"{float(v_val):.3f}")
#             it1.setTextAlignment(
#                 int(QtCore.Qt.AlignmentFlag.AlignVCenter)
#                 | int(QtCore.Qt.AlignmentFlag.AlignHCenter)
#             )
#             self.table.setItem(i, 1, it1)

#             tA = temps[2 * i] if (2 * i) < len(temps) else None
#             tB = temps[2 * i + 1] if (2 * i + 1) < len(temps) else None

#             it2 = QtWidgets.QTableWidgetItem("" if tA is None else f"{float(tA):.1f}")
#             it2.setTextAlignment(
#                 int(QtCore.Qt.AlignmentFlag.AlignVCenter)
#                 | int(QtCore.Qt.AlignmentFlag.AlignHCenter)
#             )
#             self.table.setItem(i, 2, it2)

#             it3 = QtWidgets.QTableWidgetItem("" if tB is None else f"{float(tB):.1f}")
#             it3.setTextAlignment(
#                 int(QtCore.Qt.AlignmentFlag.AlignVCenter)
#                 | int(QtCore.Qt.AlignmentFlag.AlignHCenter)
#             )
#             self.table.setItem(i, 3, it3)

#             self.table.setRowHeight(i, 28)

#         # State (supports either "s" or "st")
#         s_int_for_reset: int | None = None
#         chg_val_for_state = pkt.get("chg", None)
#         pack_i_val_for_state = pkt.get("i", None)
#         s_val = pkt.get("s", None)
#         if s_val is None:
#             s_val = pkt.get("st", None)
#         if s_val is not None:
#             try:
#                 s_int = int(s_val)
#                 s_int_for_reset = s_int
#                 self._set_state_label_from_code(
#                     s_int,
#                     chg_val=chg_val_for_state,
#                     pack_i_val=pack_i_val_for_state,
#                 )
#             except Exception:
#                 self.stateLab.setText("State: --")

#         # Charger / Deep mode
#         chg = pkt.get("chg", None)
#         deep = pkt.get("deep", None)

#         if chg is not None:
#             try:
#                 self.chgLab.setText(f"Charger: {'Connected' if int(chg) else 'Not connected'}")
#             except Exception:
#                 self.chgLab.setText("Charger: --")

#         if deep is not None:
#             try:
#                 self.deepLab.setText(f"Deep mode: {'ON' if int(deep) else 'OFF'}")
#             except Exception:
#                 self.deepLab.setText("Deep mode: --")

#         # Pack I (smoothed display)
#         pack_i = pkt.get("i", None)

#         pack_part: str | None = None
#         if pack_i is not None:
#             try:
#                 raw_i = float(pack_i)
#                 a = PACK_I_DISPLAY_SMOOTH_ALPHA
#                 if self._pack_i_display_smooth is None:
#                     self._pack_i_display_smooth = raw_i
#                 else:
#                     self._pack_i_display_smooth = a * raw_i + (1.0 - a) * self._pack_i_display_smooth
#                 show_i = self._pack_i_display_smooth
#                 mag = abs(show_i)
#                 if show_i > 1e-6:
#                     flow = "Out of pack"
#                 elif show_i < -1e-6:
#                     flow = "into pack"
#                 else:
#                     flow = ""
#                 pack_part = f"Pack I: {mag:.2f} A {flow}".strip() if flow else f"Pack I: {mag:.2f} A"
#             except Exception:
#                 pass

#         if pack_part is None and self._pack_i_display_smooth is not None:
#             show_i = self._pack_i_display_smooth
#             mag = abs(show_i)
#             if show_i > 1e-6:
#                 flow = "Out of pack"
#             elif show_i < -1e-6:
#                 flow = "into pack"
#             else:
#                 flow = ""
#             pack_part = f"Pack I: {mag:.2f} A {flow}".strip() if flow else f"Pack I: {mag:.2f} A"

#         if pack_part is None:
#             pack_part = "Pack I: --"

#         self.packLab.setText(pack_part)

#         # Faults
#         try:
#             fault = int(pkt.get("fault", 0))
#         except Exception:
#             fault = 0

#         self._sync_reset_button(fault_bits=fault, s_int=s_int_for_reset)

#         fault_list = self.decode_faults(fault)
#         if not fault_list:
#             self.faultSummaryLab.setText("Faults:  None")
#             self.faultText.setText(" No faults detected.")
#         else:
#             self.faultSummaryLab.setText(f"Faults: {len(fault_list)} active (0x{fault:02X})")
#             self.faultText.setText(" " + "\n ".join(fault_list))

#     # ------------------------------------------------------------------
#     # Demo mode
#     # ------------------------------------------------------------------
#     def startDemoMode(self) -> None:
#         if self.demoTimer is None:
#             self.demoTimer = QtCore.QTimer(self)
#             self.demoTimer.timeout.connect(self._demoTick)

#         self._demoStep = 0
#         self.demoTimer.start(500)
#         self.statusLab.setText("Demo mode: showing mock data")

#     def stopDemoMode(self) -> None:
#         if self.demoTimer is not None:
#             self.demoTimer.stop()
#         self.statusLab.setText("Disconnected")

#     def _demoTick(self) -> None:
#         self._demoStep += 1

#         num_series = 4
#         base_v = 3.60
#         series_voltages = [
#             base_v + 0.03 * math.sin(self._demoStep / 8.0 + i * 0.6)
#             for i in range(num_series)
#         ]

#         temps = [
#             28.0 + 0.8 * math.sin(self._demoStep / 10.0 + i * 0.35)
#             for i in range(8)
#         ]

#         s = 3 if (self._demoStep // 20) % 2 == 0 else 4
#         chg = 1 if s == 3 else 0

#         # Simulate deep toggle occasionally
#         deep = 1 if (self._demoStep // 60) % 2 == 1 else 0

#         pkt = {
#             "s": s,
#             "v": series_voltages,
#             "tc": temps,
#             "i": 0.8 * math.sin(self._demoStep / 12.0),
#             "soc": max(0.0, min(1.0, 0.5 + 0.4 * math.sin(self._demoStep / 50.0))),
#             "chg": chg,
#             "deep": deep,
#             "fault": 0,
#         }
#         self.onPacket(pkt)



# src/gui/main_window.py
from __future__ import annotations

import math
import time
from collections import deque
import importlib
from typing import List, Dict, Any

from PySide6 import QtWidgets, QtCore
import serial.tools.list_ports as list_ports
pg = None

from core.serial_worker import SerialWorker

DEFAULT_BAUD = 115200
DEMO_MODE = True
# EMA blend each packet: lower = slower Pack I display (0 < alpha <= 1).
PACK_I_DISPLAY_SMOOTH_ALPHA = 0.12

# UART command to ask STM to clear faults / restart.
STM_RESET_CMD = "RESET"

# Deadband for current direction decisions (only used if `chg` is missing).
ENERGY_I_DEADBAND_A = 0.15


class MainWindow(QtWidgets.QWidget):
    """BMS dashboard and threshold configuration tool."""
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
        self.resetBtn = QtWidgets.QPushButton("Reset STM")
        self.resetBtn.setEnabled(False)
        self.statusLab = QtWidgets.QLabel("Disconnected")

        # -------------------------
        # Threshold controls
        # -------------------------
        def _compact_spin(box: QtWidgets.QDoubleSpinBox) -> None:
            box.setFixedWidth(90)
            box.setFixedHeight(24)

        self.chgOnBox = QtWidgets.QDoubleSpinBox()
        _compact_spin(self.chgOnBox)
        self.chgOnBox.setRange(0.0, 3.3)
        self.chgOnBox.setDecimals(3)
        self.chgOnBox.setSingleStep(0.05)
        self.chgOnBox.setValue(1.000)

        self.chgOffBox = QtWidgets.QDoubleSpinBox()
        _compact_spin(self.chgOffBox)
        self.chgOffBox.setRange(0.0, 3.3)
        self.chgOffBox.setDecimals(3)
        self.chgOffBox.setSingleStep(0.05)
        self.chgOffBox.setValue(0.100)

        self.ovBox = QtWidgets.QDoubleSpinBox()
        _compact_spin(self.ovBox)
        self.ovBox.setRange(0.0, 10.0)
        self.ovBox.setDecimals(3)
        self.ovBox.setSingleStep(0.05)
        self.ovBox.setValue(4.150)

        self.uvBox = QtWidgets.QDoubleSpinBox()
        _compact_spin(self.uvBox)
        self.uvBox.setRange(0.0, 10.0)
        self.uvBox.setDecimals(3)
        self.uvBox.setSingleStep(0.05)
        self.uvBox.setValue(1.300)

        self.deepUvBox = QtWidgets.QDoubleSpinBox()
        _compact_spin(self.deepUvBox)
        self.deepUvBox.setRange(0.0, 10.0)
        self.deepUvBox.setDecimals(3)
        self.deepUvBox.setSingleStep(0.05)
        self.deepUvBox.setValue(0.000)

        self.otBox = QtWidgets.QDoubleSpinBox()
        _compact_spin(self.otBox)
        self.otBox.setRange(-40.0, 150.0)
        self.otBox.setDecimals(1)
        self.otBox.setSingleStep(1.0)
        self.otBox.setValue(60.0)

        self.ocBox = QtWidgets.QDoubleSpinBox()
        _compact_spin(self.ocBox)
        self.ocBox.setRange(0.0, 100.0)
        self.ocBox.setDecimals(2)
        self.ocBox.setSingleStep(0.10)
        self.ocBox.setValue(6.00)

        self.applyThreshBtn = QtWidgets.QPushButton("Apply Thresholds")
        self.applyThreshBtn.setEnabled(False)
        self.applyThreshBtn.setFixedHeight(26)

        self.thresholdBox = QtWidgets.QGroupBox("Threshold Settings")
        self.thresholdBox.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.thresholdBox.setMaximumHeight(170)
        thr = QtWidgets.QGridLayout(self.thresholdBox)
        thr.setContentsMargins(8, 6, 8, 6)
        thr.setHorizontalSpacing(8)
        thr.setVerticalSpacing(4)

        thr.addWidget(QtWidgets.QLabel("CHG ON (V)"),   0, 0)
        thr.addWidget(self.chgOnBox,                    0, 1)
        thr.addWidget(QtWidgets.QLabel("CHG OFF (V)"),  0, 2)
        thr.addWidget(self.chgOffBox,                   0, 3)

        thr.addWidget(QtWidgets.QLabel("OV (V)"),       1, 0)
        thr.addWidget(self.ovBox,                       1, 1)
        thr.addWidget(QtWidgets.QLabel("UV (V)"),       1, 2)
        thr.addWidget(self.uvBox,                       1, 3)

        thr.addWidget(QtWidgets.QLabel("Deep UV (V)"),  2, 0)
        thr.addWidget(self.deepUvBox,                   2, 1)
        thr.addWidget(QtWidgets.QLabel("OT (°C)"),      2, 2)
        thr.addWidget(self.otBox,                       2, 3)

        thr.addWidget(QtWidgets.QLabel("OC (A)"),       3, 0)
        thr.addWidget(self.ocBox,                       3, 1)
        thr.addWidget(self.applyThreshBtn,              3, 3)

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
        self._set_table_fixed_height()

        # -------------------------
        # Status + faults
        # -------------------------
        self.stateLab = QtWidgets.QLabel("State: --")
        self.chgLab = QtWidgets.QLabel("Charger: --")
        self.deepLab = QtWidgets.QLabel("Deep mode: --")
        self.packLab = QtWidgets.QLabel("Pack I: --")
        self.faultSummaryLab = QtWidgets.QLabel("Faults: --")

        self.faultBox = QtWidgets.QGroupBox("Fault Details")
        self.faultText = QtWidgets.QLabel("—")
        self.faultText.setWordWrap(True)
        faultLayout = QtWidgets.QVBoxLayout(self.faultBox)
        faultLayout.addWidget(self.faultText)

        # -------------------------
        # Thresholds (from STM telemetry)
        # -------------------------
        self.threshBox = QtWidgets.QGroupBox("Thresholds")
        self.threshBox.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.threshBox.setMaximumHeight(110)
        self.threshText = QtWidgets.QLabel("—")
        self.threshText.setWordWrap(True)
        threshLayout = QtWidgets.QVBoxLayout(self.threshBox)
        threshLayout.setContentsMargins(8, 6, 8, 6)
        threshLayout.setSpacing(4)
        threshLayout.addWidget(self.threshText)

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
        top.addWidget(self.resetBtn)
        top.addStretch(1)
        top.addWidget(self.statusLab)

        main = QtWidgets.QVBoxLayout(self)
        main.addLayout(top)
        main.addWidget(self.thresholdBox)
        main.addWidget(self.table, 3)
        main.addWidget(self.stateLab)
        main.addWidget(self.chgLab)
        main.addWidget(self.deepLab)
        main.addWidget(self.packLab)
        main.addWidget(self.faultSummaryLab)
        main.addWidget(self.faultBox)
        main.addWidget(self.threshBox)
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
        self._pack_i_display_smooth: float | None = None

        # -------------------------
        # Signals
        # -------------------------
        self.refreshBtn.clicked.connect(self.refreshPorts)
        self.connectBtn.clicked.connect(self.toggleConnection)
        self.resetBtn.clicked.connect(self._on_reset_clicked)
        self.applyThreshBtn.clicked.connect(self._on_apply_thresholds_clicked)

        self.refreshPorts()

        if DEMO_MODE:
            self.startDemoMode()

        # Lazy-load pyqtgraph/numpy after window shows (faster startup).
        QtCore.QTimer.singleShot(0, self._init_graphs)

    def _set_table_fixed_height(self) -> None:
        # Always show 4 rows and prevent vertical scrolling by sizing the widget.
        rows = 4
        default_row_h = 28
        for i in range(rows):
            self.table.setRowHeight(i, default_row_h)

        header_h = self.table.horizontalHeader().height()
        frame = self.table.frameWidth() * 2
        total_rows_h = sum(self.table.rowHeight(i) for i in range(rows))
        self.table.setFixedHeight(header_h + total_rows_h + frame)

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

    def _set_state_label_from_code(
        self,
        s_int: int,
        *,
        chg_val: Any | None = None,
        pack_i_val: Any | None = None,
    ) -> None:
        if s_int in (2, 3, 4):
            if chg_val is not None:
                try:
                    charging = int(chg_val) != 0
                    self._last_energy_display = "Charge" if charging else "Discharge"
                    self.stateLab.setText(f"State: {self._last_energy_display}")
                    return
                except Exception:
                    pass

            if pack_i_val is not None:
                try:
                    i_val = float(pack_i_val)
                    if abs(i_val) < ENERGY_I_DEADBAND_A and self._last_energy_display is not None:
                        self.stateLab.setText(f"State: {self._last_energy_display}")
                        return
                except Exception:
                    pass

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

        self._last_energy_display = None
        self.stateLab.setText(f"State: {self.state_name(s_int)} (S={s_int})")

    def _sync_reset_button(self, *, fault_bits: int, s_int: int | None) -> None:
        in_fault = fault_bits != 0 or s_int in (6, 7)
        connected = self.worker is not None and self.workerThread is not None
        self.resetBtn.setEnabled(connected and in_fault)

    @QtCore.Slot()
    def _on_reset_clicked(self) -> None:
        if self.worker is None:
            self.statusLab.setText("Not connected (cannot reset STM)")
            return
        self.resetBtn.setEnabled(False)
        self.statusLab.setText(f"Sending reset: {STM_RESET_CMD}")
        self.worker.send_cmd.emit(STM_RESET_CMD)

    @QtCore.Slot()
    def _on_apply_thresholds_clicked(self) -> None:
        if self.worker is None:
            self.statusLab.setText("Not connected (cannot send thresholds)")
            return

        chg_on = float(self.chgOnBox.value())
        chg_off = float(self.chgOffBox.value())
        ov = float(self.ovBox.value())
        uv = float(self.uvBox.value())
        deep_uv = float(self.deepUvBox.value())
        ot = float(self.otBox.value())
        oc = float(self.ocBox.value())

        if chg_on <= chg_off:
            self.statusLab.setText("Invalid charger thresholds: ON must be > OFF")
            return

        if ov <= uv:
            self.statusLab.setText("Invalid voltage thresholds: OV must be > UV")
            return

        if uv < deep_uv:
            self.statusLab.setText("Invalid voltage thresholds: UV must be >= Deep UV")
            return

        if ot <= 0.0:
            self.statusLab.setText("Invalid temperature threshold")
            return

        if oc <= 0.0:
            self.statusLab.setText("Invalid current threshold")
            return

        self.worker.send_cmd.emit(f"CHGTH {chg_on:.3f} {chg_off:.3f}")
        self.worker.send_cmd.emit(f"VTH {ov:.3f} {uv:.3f} {deep_uv:.3f}")
        self.worker.send_cmd.emit(f"TTH {ot:.1f}")
        self.worker.send_cmd.emit(f"ITH {oc:.2f}")

        self.statusLab.setText("Thresholds sent")

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
            self.resetBtn.setEnabled(False)
            self.applyThreshBtn.setEnabled(False)
            self._pack_i_display_smooth = None

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
        self.applyThreshBtn.setEnabled(True)

    # ------------------------------------------------------------------
    # Incoming packets
    # ------------------------------------------------------------------
    @QtCore.Slot(dict)
    def onPacket(self, pkt: Dict[str, Any]) -> None:
        series_voltages: List[float] = pkt.get("v", []) or []
        temps: List[float] = pkt.get("tc", []) or []
        self._update_graphs(series_voltages, temps)

        # Thresholds from STM telemetry
        try:
            if "chg_on" in pkt:
                self.chgOnBox.blockSignals(True)
                self.chgOnBox.setValue(float(pkt["chg_on"]))
                self.chgOnBox.blockSignals(False)

            if "chg_off" in pkt:
                self.chgOffBox.blockSignals(True)
                self.chgOffBox.setValue(float(pkt["chg_off"]))
                self.chgOffBox.blockSignals(False)

            if "ov" in pkt:
                self.ovBox.blockSignals(True)
                self.ovBox.setValue(float(pkt["ov"]))
                self.ovBox.blockSignals(False)

            if "uv" in pkt:
                self.uvBox.blockSignals(True)
                self.uvBox.setValue(float(pkt["uv"]))
                self.uvBox.blockSignals(False)

            if "deep_uv" in pkt:
                self.deepUvBox.blockSignals(True)
                self.deepUvBox.setValue(float(pkt["deep_uv"]))
                self.deepUvBox.blockSignals(False)

            if "ot" in pkt:
                self.otBox.blockSignals(True)
                self.otBox.setValue(float(pkt["ot"]))
                self.otBox.blockSignals(False)

            if "oc" in pkt:
                self.ocBox.blockSignals(True)
                self.ocBox.setValue(float(pkt["oc"]))
                self.ocBox.blockSignals(False)
        except Exception:
            pass

        # Table
        n = 4
        self.table.setRowCount(n)

        for i in range(n):
            it0 = QtWidgets.QTableWidgetItem(f"S{i+1}")
            it0.setTextAlignment(
                int(QtCore.Qt.AlignmentFlag.AlignVCenter)
                | int(QtCore.Qt.AlignmentFlag.AlignHCenter)
            )
            self.table.setItem(i, 0, it0)

            v_val = series_voltages[i] if i < len(series_voltages) else None
            it1 = QtWidgets.QTableWidgetItem("" if v_val is None else f"{float(v_val):.3f}")
            it1.setTextAlignment(
                int(QtCore.Qt.AlignmentFlag.AlignVCenter)
                | int(QtCore.Qt.AlignmentFlag.AlignHCenter)
            )
            self.table.setItem(i, 1, it1)

            tA = temps[2 * i] if (2 * i) < len(temps) else None
            tB = temps[2 * i + 1] if (2 * i + 1) < len(temps) else None

            it2 = QtWidgets.QTableWidgetItem("" if tA is None else f"{float(tA):.1f}")
            it2.setTextAlignment(
                int(QtCore.Qt.AlignmentFlag.AlignVCenter)
                | int(QtCore.Qt.AlignmentFlag.AlignHCenter)
            )
            self.table.setItem(i, 2, it2)

            it3 = QtWidgets.QTableWidgetItem("" if tB is None else f"{float(tB):.1f}")
            it3.setTextAlignment(
                int(QtCore.Qt.AlignmentFlag.AlignVCenter)
                | int(QtCore.Qt.AlignmentFlag.AlignHCenter)
            )
            self.table.setItem(i, 3, it3)

            self.table.setRowHeight(i, 28)

        self._set_table_fixed_height()

        # State (supports either "s" or "st")
        s_int_for_reset: int | None = None
        chg_val_for_state = pkt.get("chg", None)
        pack_i_val_for_state = pkt.get("i", None)
        s_val = pkt.get("s", None)
        if s_val is None:
            s_val = pkt.get("st", None)
        if s_val is not None:
            try:
                s_int = int(s_val)
                s_int_for_reset = s_int
                self._set_state_label_from_code(
                    s_int,
                    chg_val=chg_val_for_state,
                    pack_i_val=pack_i_val_for_state,
                )
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

        # Pack I (smoothed display)
        pack_i = pkt.get("i", None)

        pack_part: str | None = None
        if pack_i is not None:
            try:
                raw_i = float(pack_i)
                a = PACK_I_DISPLAY_SMOOTH_ALPHA
                if self._pack_i_display_smooth is None:
                    self._pack_i_display_smooth = raw_i
                else:
                    self._pack_i_display_smooth = a * raw_i + (1.0 - a) * self._pack_i_display_smooth
                show_i = self._pack_i_display_smooth
                mag = abs(show_i)
                if show_i > 1e-6:
                    flow = "Out of pack"
                elif show_i < -1e-6:
                    flow = "into pack"
                else:
                    flow = ""
                pack_part = f"Pack I: {mag:.2f} A {flow}".strip() if flow else f"Pack I: {mag:.2f} A"
            except Exception:
                pass

        if pack_part is None and self._pack_i_display_smooth is not None:
            show_i = self._pack_i_display_smooth
            mag = abs(show_i)
            if show_i > 1e-6:
                flow = "Out of pack"
            elif show_i < -1e-6:
                flow = "into pack"
            else:
                flow = ""
            pack_part = f"Pack I: {mag:.2f} A {flow}".strip() if flow else f"Pack I: {mag:.2f} A"

        if pack_part is None:
            pack_part = "Pack I: --"

        self.packLab.setText(pack_part)

        # Thresholds (from STM telemetry)
        # Keys sent by firmware: chg_on, chg_off, ov, uv, deep_uv, ot, oc
        def _fmt(key: str, fmt: str) -> str:
            val = pkt.get(key, None)
            if val is None:
                return "--"
            try:
                return fmt.format(float(val))
            except Exception:
                return "--"

        self.threshText.setText(
            "Charger detect: ON {on} V | OFF {off} V\n"
            "Voltage: OV {ov} V | UV {uv} V | Deep UV {duv} V\n"
            "Temp: OT {ot} °C\n"
            "Current: OC {oc} A".format(
                on=_fmt("chg_on", "{:.3f}"),
                off=_fmt("chg_off", "{:.3f}"),
                ov=_fmt("ov", "{:.3f}"),
                uv=_fmt("uv", "{:.3f}"),
                duv=_fmt("deep_uv", "{:.3f}"),
                ot=_fmt("ot", "{:.1f}"),
                oc=_fmt("oc", "{:.2f}"),
            )
        )

        # Optional: keep the settings widgets in sync with live thresholds,
        # but only if the user is not currently editing them.
        if not (
            self.chgOnBox.hasFocus()
            or self.chgOffBox.hasFocus()
            or self.ovBox.hasFocus()
            or self.uvBox.hasFocus()
            or self.deepUvBox.hasFocus()
            or self.otBox.hasFocus()
            or self.ocBox.hasFocus()
        ):
            try:
                if pkt.get("chg_on", None) is not None:
                    self.chgOnBox.setValue(float(pkt["chg_on"]))
                if pkt.get("chg_off", None) is not None:
                    self.chgOffBox.setValue(float(pkt["chg_off"]))
                if pkt.get("ov", None) is not None:
                    self.ovBox.setValue(float(pkt["ov"]))
                if pkt.get("uv", None) is not None:
                    self.uvBox.setValue(float(pkt["uv"]))
                if pkt.get("deep_uv", None) is not None:
                    self.deepUvBox.setValue(float(pkt["deep_uv"]))
                if pkt.get("ot", None) is not None:
                    self.otBox.setValue(float(pkt["ot"]))
                if pkt.get("oc", None) is not None:
                    self.ocBox.setValue(float(pkt["oc"]))
            except Exception:
                pass

        # Faults
        try:
            fault = int(pkt.get("fault", 0))
        except Exception:
            fault = 0

        self._sync_reset_button(fault_bits=fault, s_int=s_int_for_reset)

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
        deep = 1 if (self._demoStep // 60) % 2 == 1 else 0

        pkt = {
            "s": s,
            "v": series_voltages,
            "tc": temps,
            "i": 0.8 * math.sin(self._demoStep / 12.0),
            "chg": chg,
            "deep": deep,
            "fault": 0,
            "chg_on": 1.000,
            "chg_off": 0.100,
            "ov": 4.150,
            "uv": 1.300,
            "deep_uv": 0.000,
            "ot": 60.0,
            "oc": 6.00,
        }
        self.onPacket(pkt)
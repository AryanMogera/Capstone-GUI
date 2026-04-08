# BMS GUI (PySide6)

Desktop dashboard for a modular sodium-ion BMS.  
The app reads newline-delimited JSON telemetry from an STM32 over UART, 
shows live status, and can send configuration/reset commands back to the controller.

## Features

- Live table for 4 series groups (voltage + temperature channels)
- State, charger/deep mode, pack current, and fault summary display
- Threshold controls (send `CHGTH`, `VTH`, `TTH`, `ITH` commands)
- Optional live graphs (via `pyqtgraph`)
- Demo mode for UI testing without hardware

## Project Structure

- `src/main.py` - app entry point and light theme setup
- `src/gui/main_window.py` - main GUI, serial connect/disconnect flow, packet rendering, demo mode
- `src/core/serial_worker.py` - serial read/write worker running in a Qt thread
- `src/core/protocol.py` - packet parser (`parse_packet`)
- `src/core/config.py` - shared config (`DEFAULT_BAUD`, `DEMO_MODE`)

## Telemetry Format (from STM32)

Each UART line should be one JSON object, for example:

```json
{"s":3,"v":[3.61,3.60,3.59,3.62],"tc":[28.4,28.7,29.0,29.2,28.6,28.5,28.9,29.1],"i":-1.25,"fault":0}
```

Common keys used by the GUI:

- `s`: state code (int)
- `v`: list of 4 series voltages
- `tc`: list of 8 temperatures (2 per series group)
- `i`: pack current
- `fault`: fault bitfield
- Optional threshold echo keys: `chg_on`, `chg_off`, `ov`, `uv`, `deep_uv`, `ot`, `oc`

## Prerequisites

- Python 3.10+ recommended
- USB/UART connection to STM32 (for hardware mode)

Dependencies are listed in `requirements.txt`:

- `pyside6`
- `pyserial`
- `pyqtgraph`
- `numpy`

## Setup and Run (macOS)

1. Open Terminal and go to the project:
   ```bash
   cd "Project Directory"
   ```
2. Create and activate virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the app:
   ```bash
   python3 src/main.py
   ```

## Setup and Run (Windows)

1. Open PowerShell (or Command Prompt) and go to the project folder:
   ```powershell
   cd "C:\path\to\bms-gui"
   ```
2. Create and activate virtual environment:
   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   If using Command Prompt:
   ```bat
   .\.venv\Scripts\activate.bat
   ```
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Run the app:
   ```powershell
   python src/main.py
   ```

## Demo Mode vs Hardware Mode

Demo/hardware behavior is controlled in `src/core/config.py`:

- `DEMO_MODE = True` -> starts with synthetic data (no STM32 required)
- `DEMO_MODE = False` -> normal hardware flow; choose serial port and connect

Default serial baud is also in `src/core/config.py`:

- `DEFAULT_BAUD = 115200`

## Typical Hardware Workflow

1. Set `DEMO_MODE = False`.
2. Connect STM32 over USB/UART.
3. Launch app.
4. Click `Refresh`, select detected port, then `Connect`.
5. Observe live telemetry and faults.
6. Use `Apply Thresholds` to send threshold commands.
7. Use `Reset STM` when in fault state (button enables based on state/faults).

## Status: Threshold Applying (WIP)

The **Apply Thresholds** feature (sending thresholds from Python to the STM32) is **still under debugging** and **not fully implemented/validated yet**. Expect possible mismatches with firmware parsing/ACK behavior while this is being finalized.

## Troubleshooting

- **No serial ports listed**
  - Check cable/device power.
  - Reconnect USB and click `Refresh`.
  - On macOS, typical names: `/dev/tty.*` or `/dev/cu.*`.
  - On Windows, typical names: `COM3`, `COM4`, etc.

- **Connection failed**
  - Confirm the selected port is correct and not in use by another tool.
  - Confirm baud rate matches firmware (`115200` by default).

- **No graph display**
  - Ensure `pyqtgraph` and `numpy` are installed.
  - The app still works without graphs but will show a graph status message.

- **No telemetry shown**
  - Ensure firmware sends one complete JSON object per line (`\n` terminated).
  - Check that keys match expected names (`s`, `v`, `tc`, `i`, `fault`, etc.).

## Notes

- `app.yml` is present but the current desktop app flow reads runtime settings from Python modules (`src/core/config.py`) and GUI controls.
- `__pycache__/` and `*.pyc` are ignored in git via `.gitignore`.

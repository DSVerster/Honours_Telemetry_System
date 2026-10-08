# Honours_Telemetry_System

A stratospheric balloon telemetry system developed for my Honours project. It combines GPS tracking, UHF radio communication (Radiometrix NTX2 / NRX2), onboard data logging, and a ground station that receives, decodes, and logs flight telemetry at high altitude.

---

## Technology Stack

### Hardware

| Subsystem | Technology |
|---|---|
| Payload computer | **Raspberry Pi Zero W (v1.1)** running Raspberry Pi OS / Debian |
| GPS | **Uputronics u-blox GPS** expansion board (v3.2b, 2016), connected to the Pi's UART (`/dev/serial0`) |
| Transmitter | Radiometrix **NTX2** - UHF narrow-band FM transmitter |
| Receiver | Radiometrix **NRX2** - UHF narrow-band FM receiver (baseband output plus RSSI) |
| Ground decoder | **Arduino Uno (Rev3)** |
| Ground computer | PC / laptop running **Windows 10**, connected to the Arduino over USB |
| Antennas | Whip-style (monopole) antennas on the transmitter and receiver |
| Power (payload) | 5 V USB: either a USB power bank or a normal USB port |

### Software

| Layer | Technology |
|---|---|
| Payload programs | **Python 3** (3.7 or newer) |
| GPS interface | **gpsd** daemon, read through the `gps` Python client (`python3-gps`) |
| Radio output | **RPi.GPIO** - the Pi toggles GPIO17 directly to drive the NTX2 modulation input (software "bit-banging", timed with `time.perf_counter`) |
| Receiver firmware | **Arduino C++** (Arduino core only, no external libraries), using an external interrupt on D2 for edge timing |
| Ground logger | **Python 3** (3.7 or newer) with **pyserial** |
| Analysis | **Python 3** standard library only (`csv`, `statistics`, `math`) |
| Version control | **Git** / GitHub |

### Communication and data

| Item | Technology |
|---|---|
| Radio link | UHF, one-way (payload to ground), narrow-band FM |
| Line coding | **Manchester** encoding (IEEE 802.3 convention), 4000 µs bit period (250 bit/s) by default |
| Framing | Custom frame: 6-byte `0xAA` preamble, 2-byte sync word (`0x2DD4`), length byte, ASCII payload, **CRC-8** (polynomial `0x07`) |
| Telemetry payload | Compact comma-separated ASCII text |
| Arduino to PC | USB serial, 115200 baud, line-based `LOG,...` records |
| Data storage | **CSV** (GPS and received-telemetry logs), **JSON** (`latest_gps.json`), plain-text logs (`gps_transmit.log`) |

---

## Repository Structure

```text
Honours_Telemetry_System/
├── programs/
│   ├── payload/
│   │   ├── air/
│   │   │   ├── gps_execute.py
│   │   │   └── gps_transmit.py
│   │   │
│   │   ├── stationary/
│   │   │   ├── gps_execute.py
│   │   │   ├── gps_transmit.py
│   │   │   └── analysis.py
│   │   │
│   │   └── gps_test/
│   │       └── verify.py
│   │
│   └── ground/
│       └── receiver_logger/
│           ├── receiver_logger.ino
│           └── gps_receive_logger.py
│
├── documents/
│   └── Honours_Research_Project (incomplete).pdf
│
├── README.md
├── requirements.txt
└── .gitignore
```

Runtime-generated `logs/` folders and `latest_gps.json` files will appear inside the program folders when the programs are run. They are **never committed** (see [Generated Data and Version Control](#generated-data-and-version-control)).

### `programs/payload/air/`

Software intended for operation while the balloon is airborne.

- `gps_execute.py` - reads GPS data from `gpsd`, validates fixes, logs them to CSV, and maintains `latest_gps.json`.
- `gps_transmit.py` - reads `latest_gps.json` and transmits it through the NTX2 as a Manchester-encoded frame.

The airborne versions may differ from the stationary versions in logging intervals, transmission intervals, and other flight-specific configuration. The underlying GPS and telemetry functionality is the same.

### `programs/payload/stationary/`

Software for stationary and controlled testing of the payload.

- `gps_execute.py` - as above.
- `gps_transmit.py` - as above.
- `analysis.py` - analyses the GPS CSV logs collected during stationary experiments.

### `programs/payload/gps_test/`

- `verify.py` - reads from `gpsd` and prints the current fix every 2 seconds, to verify the GPS hardware and communication path independently of the main payload programs.

### `programs/ground/receiver_logger/`

Software for the ground station.

- `receiver_logger.ino` - Arduino Uno sketch. Decodes the Manchester telemetry from the NRX2 receiver and prints each frame over USB serial, including a machine-readable `LOG,...` line.
- `gps_receive_logger.py` - runs on the ground PC, reads the Arduino's serial output, and writes one row per unique transmission to `logs/gps_received.csv`.

### `documents/`

Supporting project material (the research report, wiring diagrams, datasheets, test results, etc.).

---

## System Overview

```text
                         AIRBORNE PAYLOAD
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                       GPS Module                            │
│                           │                                 │
│                           │ UART                            │
│                           ▼                                 │
│                  Raspberry Pi (gpsd)                        │
│                           │                                 │
│              ┌────────────┴────────────┐                    │
│              │                         │                    │
│              ▼                         ▼                    │
│       gps_execute.py           latest_gps.json              │
│              │                         │                    │
│              ▼                         ▼                    │
│          logs/*.csv             gps_transmit.py             │
│                                        │                    │
│                                        ▼                    │
│                                  NTX2 Transmitter           │
│                                        │                    │
└────────────────────────────────────────┼────────────────────┘
                                         │
                                  UHF telemetry
                                         │
                                         ▼
                              ┌─────────────────────┐
                              │   NRX2 Receiver     │
                              └──────────┬──────────┘
                                         │ baseband (D2) + RSSI (A0)
                                         ▼
                              ┌─────────────────────┐
                              │  Arduino Uno        │
                              │  receiver_logger.ino│
                              └──────────┬──────────┘
                                         │ USB serial, 115200 baud
                                         │ "LOG,OK,<ms>,<RSSI>,<payload>"
                                         ▼
                              ┌─────────────────────┐
                              │ gps_receive_logger  │
                              │        .py          │
                              └──────────┬──────────┘
                                         │
                                         ▼
                              logs/gps_received.csv
```

---

## Installation

### Payload (Raspberry Pi)

1. Install the system packages. These are **not** pip packages:

   ```bash
   sudo apt update
   sudo apt install gpsd gpsd-clients python3-gps python3-pip python3-venv
   ```

2. Create a virtual environment and install the Python dependencies. The `--system-site-packages` flag is important: it lets the virtual environment see the apt-installed `gps` module.

   ```bash
   cd Honours_Telemetry_System
   python3 -m venv --system-site-packages .venv
   source .venv/bin/activate
   python3 -m pip install -r requirements.txt
   ```

   Newer Raspberry Pi OS releases (Bookworm and later) block `pip install` into the system Python, which is why the virtual environment is used.

   If `RPi.GPIO` fails to build, run `sudo apt install python3-dev` and retry, or install the apt package `python3-rpi.gpio` instead.

### Ground station (PC / laptop)

1. Install Python 3 and the dependencies:

   ```bash
   python3 -m pip install -r requirements.txt
   ```

   On the ground PC this installs only `pyserial`; `RPi.GPIO` is skipped automatically because it is restricted to Raspberry Pi architectures in `requirements.txt`.

2. Install the Arduino IDE (or `arduino-cli`) to upload `receiver_logger.ino` to the Arduino Uno. No additional Arduino libraries are required.

### What goes where

| Dependency | Installed with | Used by |
|---|---|---|
| `gpsd`, `gpsd-clients`, `python3-gps` | `apt` | `gps_execute.py`, `verify.py` |
| `RPi.GPIO` | `requirements.txt` | `gps_transmit.py` |
| `pyserial` | `requirements.txt` | `gps_receive_logger.py` |
| *(standard library only)* | - | `analysis.py` |

---

## GPS Subsystem

The payload GPS software communicates with the GPS receiver through `gpsd`.

`gps_execute.py`:

1. connects to `gpsd`;
2. receives TPV (time-position-velocity) reports;
3. accepts a report as valid only if it has a 3D fix (`mode >= 3`) with latitude and longitude present;
4. updates `latest_gps.json` on **every** valid fix;
5. appends a row to the session CSV log every `LOG_INTERVAL` seconds (5 s in the current code).

Altitude, speed, and track are optional and are recorded as `None`/empty if the receiver has not provided them.

Updating `latest_gps.json` on every fix, independently of the 5-second logging interval, means the transmitter always has access to the newest valid position.

### GPS startup procedure

`gpsd` must be prepared manually before running the GPS programs:

```bash
sudo pkill -f "cat /dev/serial0"
sudo systemctl stop gpsd.socket gpsd.service
sudo gpsd /dev/serial0 -F /var/run/gpsd.sock -n
```

These commands are **not** intended to run automatically at boot. Run them by hand before starting a GPS program.

### GPS verification

To check the GPS hardware on its own:

```bash
cd programs/payload/gps_test
python3 verify.py
```

`verify.py` prints a line every 2 seconds, either `GPS FIX` (with mode, latitude, longitude, altitude, speed, track, and satellites) or `NO POSITION FIX`. It accepts a 2D fix or better, whereas `gps_execute.py` requires a 3D fix.

---

## GPS Data Logging

Each run of `gps_execute.py` creates a new CSV in a `logs/` directory next to the script:

```text
logs/gps_log_YYYY-MM-DD_HH-MM-SS.csv        (timestamp is UTC)
```

The first line of each file is a metadata line (`Logging session started: <ISO timestamp>`), followed by a header and one row per logged fix:

```text
system_time, satellite_time, latitude, longitude,
altitude_m, speed_mps, track_deg, satellites_used
```

### Latest GPS position

`gps_execute.py` also maintains `latest_gps.json` (next to the script), which holds the most recent valid fix:

```json
{
    "system_time": "...",
    "satellite_time": "2026-09-19T02:23:06.000Z",
    "latitude": -26.6886298,
    "longitude": 27.0952813,
    "altitude_m": 1344.117,
    "speed_mps": 0.07,
    "track_deg": 354.5929,
    "satellites_used": 9
}
```

This is the interface between GPS acquisition and the transmitter. The file is written to a temporary file and then atomically swapped in with `os.replace`, so `gps_transmit.py` can never read a half-written JSON file.

---

## Telemetry

### Payload format

`gps_transmit.py` converts `latest_gps.json` into a compact ASCII payload:

```text
<transmission_counter>,<latitude>,<longitude>,<altitude>,<HHMMSS>
```

For example:

```text
1,-26.68863,27.09528,1344,022306
```

- `transmission_counter` - starts at 0 each time the transmitter is started and increases by one per transmitted burst. It acts as a **group ID**: all repeated copies of one reading share the same counter value.
- `latitude`, `longitude` - 5 decimal places (reduced to 4 if the payload would exceed 40 bytes).
- `altitude` - whole metres.
- `HHMMSS` - UTC time of the GPS fix, taken from the satellite time (falls back to the Pi's UTC clock if the satellite time is unavailable).

### Frame structure

```text
Preamble (6 x 0xAA) + Sync (0x2D 0xD4) + Length (1 byte) + Payload (1-40 bytes) + CRC-8
```

- CRC-8 uses polynomial `0x07` and covers the length byte and payload.
- The whole frame is Manchester-encoded (IEEE 802.3 convention): bit `1` = LOW then HIGH, bit `0` = HIGH then LOW.
- The default bit period is 4000 µs (250 bit/s). A typical 32-byte payload gives a 42-byte frame, roughly 1.3 s per copy.
- The Arduino decoder also accepts an inverted signal.

`MAX_PAYLOAD_BYTES` in `gps_transmit.py` must match `MAX_PAYLOAD` in `receiver_logger.ino`, and `--bit-us` must match `BIT_US` in the sketch.

### Repeated transmission

Each GPS reading is sent as a burst of identical copies, so that the receiver has several chances to decode it. Defaults:

| Option | Default | Meaning |
|---|---|---|
| `--gpio` | `17` | BCM GPIO pin driving the NTX2 TXD input |
| `--bit-us` | `4000` | Manchester bit period in microseconds |
| `--repeats` | `6` | Copies of the frame per reading |
| `--gap-ms` | `0` | Idle gap between copies in a burst |
| `--interval` | `60` | Seconds between readings/bursts |
| `--json-path` | `latest_gps.json` | GPS JSON file to read (relative to the current directory) |
| `--log-dir` | `logs` | Directory for `gps_transmit.log` |
| `--seconds` | `0` | Stop after N seconds (`0` = run until Ctrl+C) |

Examples:

```bash
python3 gps_transmit.py
python3 gps_transmit.py --interval 120 --repeats 6
python3 gps_transmit.py --json-path /home/strato/latest_gps.json
python3 gps_transmit.py --help
```

### Transmit log

Every transmission, warning, and error is also written to `logs/gps_transmit.log` (in the current working directory, or `--log-dir`). Raw GPS reads between transmissions are not logged. If `latest_gps.json` is missing or contains bad data, the cycle is skipped with a warning.

### Running with GPIO access

`gps_transmit.py` tries to raise its scheduling priority (`SCHED_FIFO`) for accurate bit timing. This needs root; without it the script silently continues at normal priority. If you use the virtual environment, `sudo python3` will **not** see its packages, so call the venv interpreter explicitly:

```bash
sudo .venv/bin/python3 gps_transmit.py
```

---

## Ground Station

### Hardware connections (NRX2 to Arduino Uno)

```text
NRX2 pin 7  (RXD)   -> Arduino D2   (direct, no resistor)
NRX2 pin 3  (RSSI)  -> Arduino A0
NRX2 pin 5  (Vcc)   -> Arduino 5V
NRX2 pins 4 and 2   -> GND
NRX2 pin 1          -> antenna
```

### Arduino sketch

Upload `programs/ground/receiver_logger/receiver_logger.ino` to the Uno. It:

- timestamps every signal edge with an interrupt on D2 and decodes the Manchester stream (6 consecutive long intervals in the preamble establish bit timing);
- checks the CRC;
- prints a human-readable line for the Serial Monitor (115200 baud) for every frame, good or bad;
- prints a machine-readable line for every frame:

  ```text
  LOG,<OK|BAD>,<millis>,<RSSI_mV>,<payload text>
  ```

  for example `LOG,OK,45231,1862,5,-26.68863,27.09528,1344,022306`;
- prints a `[status]` line every 2 seconds with RSSI, edge count, preamble locks, and OK/bad frame counts.

### Receive logger

`gps_receive_logger.py` reads the Arduino's serial output and logs **one row per unique transmission**, not one row per received copy.

1. For each `LOG,OK,...` line with a valid GPS payload, it counts the copy against that transmission's group ID.
2. Once `--finalize-seconds` (default 10) pass without a new copy of that group, it writes a single row with the fix data and the number of copies received.
3. Any groups still pending when you press Ctrl+C are written before exit.

`BAD` (failed CRC) frames and payloads that are not in the GPS format are ignored.

Usage:

```bash
cd programs/ground/receiver_logger
python3 gps_receive_logger.py --port /dev/ttyACM0
python3 gps_receive_logger.py --port COM3 --baud 115200
python3 gps_receive_logger.py --port COM3 --log-dir logs --finalize-seconds 10
```

Finding the serial port:

- Linux / macOS: `ls /dev/ttyACM* /dev/ttyUSB* /dev/tty.*`
- Windows: Device Manager -> Ports (COM & LPT)

Output is appended to `logs/gps_received.csv` with the columns:

```text
logged_at_utc, group_id, latitude, longitude, altitude_m,
fix_time_hhmmss, rssi_mv, copies_received
```

Notes when interpreting this file:

- `copies_received` is the number of copies decoded out of the `--repeats` sent, so it is a simple per-transmission reliability measure.
- `rssi_mv` is the RSSI measured when the **first** copy of that group was decoded.
- `group_id` restarts at 0 whenever the transmitter is restarted, so it is only unique within one transmitter run. Use `logged_at_utc` to tell runs apart.
- The file is opened in append mode, so data from multiple sessions accumulates in the same CSV.

---

## Running the System

### Payload

1. **Verify the GPS** (optional but recommended):

   ```bash
   cd programs/payload/gps_test
   python3 verify.py
   ```

2. **Prepare gpsd** with the three commands in [GPS startup procedure](#gps-startup-procedure).

3. **Start the GPS logger** (use `stationary` or `air`):

   ```bash
   cd programs/payload/stationary
   python3 gps_execute.py
   ```

4. **Start telemetry**, in a second terminal, once valid GPS data is available:

   ```bash
   cd programs/payload/stationary
   python3 gps_transmit.py
   ```

### Ground station

1. Upload `receiver_logger.ino` to the Arduino.
2. Run `gps_receive_logger.py` with the Arduino's serial port (see above).

### Stationary vs airborne

The `air` and `stationary` folders are kept separate because their operating requirements differ.

- **Stationary**: controlled testing, GPS testing, telemetry and transmitter/receiver experiments, and data collection for analysis.
- **Airborne**: actual balloon operation, tracking and recovery, appropriate telemetry intervals, and operation within the payload's power constraints.

Do not assume the two are identical. When a change is made to one, check whether the same change is needed in the other.

---

## Analysing GPS Logs

`programs/payload/stationary/analysis.py` analyses the payload GPS CSVs from stationary experiments:

```bash
cd programs/payload/stationary
python3 analysis.py
```

It reads every `.csv` in the `logs/` directory next to the script and reports, per file and overall, the positional deviation from the file's own mean position, altitude, speed, satellite counts, consecutive position changes, and "jumps" (a change above 5 m between consecutive fixes). The report is printed and saved to `log_analysis.txt` (git-ignored).

Because the reference position is each file's own mean, the results describe GPS **repeatability**, not absolute accuracy against a surveyed point.

> **Note:** `analysis.py` expects the payload log format produced by `gps_execute.py`. Files that do not match (for example `gps_received.csv` from the ground station) are counted as "empty", and the script will offer to delete them. Keep ground-station logs out of the payload `logs/` folder, and answer `N` to the delete prompt if unsure.

---

## Generated Data and Version Control

**No logs or generated data are ever committed to Git.** The `.gitignore` excludes:

| Pattern | What it covers |
|---|---|
| `logs/`, `log/` | every logs directory in the repo (payload GPS CSVs, `gps_transmit.log`, `gps_received.csv`) |
| `*.csv`, `*.csv.*` | any CSV |
| `*.log`, `*.log.*` | any log file, including rotated ones |
| `latest_gps.json`, `latest_gps.json.*`, `*.json.tmp` | the latest-position file and its temporary file |
| `log_analysis.txt` | the report written by `analysis.py` |

### Checking that nothing is tracked

`.gitignore` only affects files Git is **not already tracking**. To confirm no data files are in the repository:

```bash
git ls-files | grep -Ei '\.(csv|log)$|(^|/)logs?/|latest_gps|log_analysis'
```

This should print nothing. To see which rule is ignoring a particular file:

```bash
git check-ignore -v programs/ground/receiver_logger/logs/gps_received.csv
```

### If a data file was already committed

Stop tracking it (this keeps the file on disk):

```bash
git rm -r --cached programs/ground/receiver_logger/logs
git rm -r --cached programs/payload/stationary/logs
git rm --cached programs/payload/stationary/latest_gps.json
git commit -m "Stop tracking generated GPS data"
```

Only run the lines for paths that actually appear in `git ls-files`. Note that this removes the files from future commits only. If the data was already **pushed**, it remains in the repository history; removing it completely requires rewriting history (for example with `git filter-repo`) and force-pushing, and any existing clones or forks would still contain it. If the data is sensitive (such as launch-site or home coordinates), treat it as exposed.

### Keeping experimental data

Because data is not in the repository, back up important experimental logs separately (an external drive or institutional storage), and record which commit produced them (see [Reproducibility](#reproducibility)).

---

## Development and Testing Workflow

```text
1. Verify GPS hardware (programs/payload/gps_test/verify.py)
        │
        ▼
2. Prepare gpsd
        │
        ▼
3. Run gps_execute.py ──► latest_gps.json
        │                 logs/gps_log_*.csv
        ▼
4. Confirm valid GPS data
        │
        ▼
5. Run gps_transmit.py ──► logs/gps_transmit.log
        │
        ▼
6. NRX2 + receiver_logger.ino decode the UHF transmission
        │
        ▼
7. gps_receive_logger.py ──► logs/gps_received.csv
        │
        ▼
8. Compare transmitted and received logs; run analysis.py on stationary GPS logs
```

Each stage can be tested separately, which makes it easier to isolate problems in GPS acquisition, transmission, reception, or decoding.

---

## Reproducibility

For each significant experiment, record:

- the repository Git commit (`git rev-parse HEAD`);
- payload, GPS, transmitter, receiver, and antenna configuration;
- GPS logging interval;
- telemetry interval, number of repeated copies, and Manchester bit period;
- experiment start and end time; and
- relevant environmental conditions.

Associate generated data with the commit that produced it so results can be reproduced against the correct version of the software.

---

## Project Status

This is an evolving research and engineering project. Current components:

- airborne and stationary payload software;
- GPS verification tool;
- UHF telemetry transmission (NTX2, Manchester framing, repeated bursts);
- UHF telemetry reception and decoding (NRX2 + Arduino);
- received-telemetry logging;
- GPS log analysis; and
- hardware and wiring documentation (in progress).

---

## Licence

No licence has been specified for this repository yet. A suitable open-source or research-specific licence can be added when the project is ready for public distribution.

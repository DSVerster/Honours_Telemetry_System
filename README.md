# Honours_Telemetry_System
A stratospheric balloon telemetry system developed for my Honours project, combining GPS tracking, UHF radio communication, onboard data logging, and a ground station to transmit, receive, decode, and monitor flight telemetry at high altitudes.

## Repository Structure

```text
Repo/
├── programs/
│   ├── payload/
│   │   ├── stationary/
│   │   │   ├── gps_transmit.py
│   │   │   ├── gps_execute.py
│   │   │   └── analysis.py
│   │   │
│   │   └── air/
│   │       ├── gps_transmit.py
│   │       └── gps_execute.py
│   │
│   ├── gps_test/
│   │   └── verify.py
│   │
│   └── ground/
│       ├── gps_receive.ino
│       ├── ground_station.py
│       └── [future Python logging program]
│
├── documents/
│   └── [wiring diagrams, datasheets, supporting documentation, etc.]
│
├── README.md
├── requirements.txt
└── .gitignore
```

### `programs/payload/stationary/`

Contains the software used for stationary and controlled testing of the payload system.

- `gps_execute.py` — obtains GPS data, validates GPS fixes, records GPS measurements, and maintains the latest valid GPS position.
- `gps_transmit.py` — reads the latest GPS position and transmits a compact telemetry frame.
- `analysis.py` — analyses GPS data collected during stationary experiments.

The stationary implementation is intended primarily for controlled testing, system verification, data collection, and analysis.

### `programs/payload/air/`

Contains the software intended for operation while the balloon is airborne.

The airborne versions of `gps_execute.py` and `gps_transmit.py` may differ from the stationary versions in terms of:

- information logged;
- logging intervals;
- telemetry transmission intervals; and
- other configuration required specifically for airborne operation.

The underlying GPS and telemetry functionality remains the same.

### `programs/gps_test/`

Contains software used to verify the operation of the GPS module independently of the main payload programs.

- `verify.py` — reads and displays readings received from the connected GPS module.

This program is intended for GPS hardware and communication verification rather than normal payload operation.

### `programs/ground/`

Contains software associated with the ground station.

- `gps_receive.ino` — Arduino program responsible for receiving and decoding the telemetry data.
- `ground_station.py` — Python ground-station program.
- A further Python logging program may be added later for recording received telemetry.

### `documents/`

Contains supporting project material such as:

- wiring diagrams;
- system diagrams;
- hardware documentation;
- datasheets;
- experimental documentation;
- test results; and
- other relevant project documents.

---

# System Overview

The overall system consists of an airborne GPS and telemetry subsystem and a ground station.

```text
                         AIRBORNE PAYLOAD
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                       GPS Module                            │
│                           │                                 │
│                           │ UART                            │
│                           ▼                                 │
│                    Raspberry Pi                             │
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
                                         │
                                    Baseband data
                                         │
                                         ▼
                              ┌─────────────────────┐
                              │      Arduino        │
                              │   gps_receive.ino   │
                              └──────────┬──────────┘
                                         │
                                  Decoded telemetry
                                         │
                                         ▼
                              ┌─────────────────────┐
                              │  ground_station.py  │
                              └──────────┬──────────┘
                                         │
                                         ▼
                                  Display / Logging
```

---

# GPS Subsystem

The payload GPS software communicates with the GPS receiver through `gpsd`.

The GPS execution program:

1. connects to the GPS service;
2. receives GPS reports;
3. checks whether a usable GPS fix is available;
4. records valid GPS measurements;
5. updates `latest_gps.json`; and
6. makes the latest position available to other payload software.

The current GPS implementation considers a 3D fix (`mode >= 3`) necessary and requires latitude and longitude to be available before a position is considered valid.

---

# GPS Data Logging

Each execution of `gps_execute.py` creates a separate CSV log in a local `logs` directory.

The recorded GPS information includes:

```text
system_time
satellite_time
latitude
longitude
altitude_m
speed_mps
track_deg
satellites_used
```

A typical log filename follows the form:

```text
gps_log_YYYY-MM-DD_HH-MM-SS.csv
```

For example:

```text
gps_log_2026-09-19_02-23-06.csv
```

The logging interval is configurable through the individual payload implementation. The stationary and airborne versions may therefore use different intervals.

---

# Latest GPS Position

In addition to the historical CSV log, the GPS program maintains:

```text
latest_gps.json
```

This file contains the most recent valid GPS position.

An example is:

```json
{
    "system_time": "...",
    "satellite_time": "...",
    "latitude": -26.6886298,
    "longitude": 27.0952813,
    "altitude_m": 1344.117,
    "speed_mps": 0.07,
    "track_deg": 354.5929,
    "satellites_used": 9
}
```

The JSON file is intended to provide a simple interface between the GPS acquisition program and other payload programs.

In particular, `gps_transmit.py` reads this file to obtain the latest position that should be transmitted.

The GPS program writes the JSON file through a temporary file before replacing the previous version. This prevents another program from attempting to read a partially written JSON file.

---

# GPS Startup Procedure

The GPS module requires the Raspberry Pi GPS service to be prepared before running the GPS programs.

The following commands are currently required:

```bash
sudo pkill -f "cat /dev/serial0"
sudo systemctl stop gpsd.socket gpsd.service
sudo gpsd /dev/serial0 -F /var/run/gpsd.sock -n
```

These commands are **not intended to run automatically at system startup**.

They should instead be run manually before starting one of the GPS programs.

A shell script may be provided in the future to perform these commands automatically when requested by the user, for example:

```bash
./start_gps.sh
```

The script would only prepare GPSD when manually executed. It would not install itself as a service and would not execute automatically when the Raspberry Pi boots.

After the GPS service has been prepared, the relevant GPS program can be run normally.

For example:

```bash
cd programs/payload/stationary
python3 gps_execute.py
```

or:

```bash
cd programs/payload/air
python3 gps_execute.py
```

---

# GPS Verification

Before running the main payload software, the GPS module can be tested independently using:

```text
programs/gps_test/verify.py
```

The purpose of this program is simply to read available information from the connected GPS module and provide a straightforward way to verify that the GPS hardware and communication path are functioning.

A typical testing sequence is therefore:

```text
GPS hardware
     │
     ▼
verify.py
     │
     ▼
Confirm GPS readings
     │
     ▼
Prepare GPSD
     │
     ▼
gps_execute.py
```

---

# Telemetry System

The payload uses a Radiometrix NTX2 transmitter to transmit GPS information from the balloon to the ground station.

The telemetry transmitter reads:

```text
latest_gps.json
```

and converts the GPS information into a compact ASCII payload.

The current payload format is:

```text
<transmission_counter>,<latitude>,<longitude>,<altitude>,<HHMMSS>
```

For example:

```text
1,-26.68863,27.09528,1344,022306
```

The payload contains:

- a transmission counter;
- latitude;
- longitude;
- altitude; and
- the GPS fix time in UTC.

The compact format reduces the amount of data that must be transmitted while retaining the primary information required for balloon tracking and recovery.

---

# Telemetry Frame

The current transmitter constructs a frame consisting of:

```text
Preamble
    +
Synchronisation sequence
    +
Payload length
    +
Payload
    +
CRC
```

The transmitter currently uses:

- a six-byte `0xAA` preamble;
- a two-byte synchronisation sequence;
- a payload-length byte;
- the ASCII telemetry payload;
- an 8-bit CRC; and
- Manchester encoding.

Manchester encoding is implemented as:

```text
Bit 1 → LOW → HIGH
Bit 0 → HIGH → LOW
```

The receiver-side decoder is designed to interpret this same encoding.

---

# Repeated Telemetry Transmission

A single GPS reading may be transmitted multiple times as a burst.

The current transmitter implementation supports configurable:

- GPIO pin;
- Manchester bit timing;
- number of repeated copies;
- gap between copies;
- transmission interval;
- GPS JSON path; and
- total execution duration.

For example:

```bash
python3 gps_transmit.py
```

or:

```bash
python3 gps_transmit.py --interval 120 --repeats 6
```

The transmitter can also be directed to a specific GPS JSON file:

```bash
python3 gps_transmit.py --json-path /home/strato/latest_gps.json
```

Run:

```bash
python3 gps_transmit.py --help
```

to view the available options.

The `air` and `stationary` versions may use different transmission intervals according to their experimental requirements.

---

# Ground Station

The ground station receives the transmitted UHF telemetry and converts it back into usable GPS information.

The intended signal path is:

```text
Radiometrix NTX2
       │
       │ UHF RF
       ▼
Radiometrix NRX2
       │
       │ Baseband
       ▼
Arduino
       │
       │ gps_receive.ino
       ▼
Decoded telemetry
       │
       ▼
ground_station.py
       │
       ▼
Display / Logging
```

The Arduino receiver program will be named:

```text
gps_receive.ino
```

The associated Python ground-station program will be named:

```text
ground_station.py
```

A separate Python program for logging received telemetry may be added later.

The ground-station software is deliberately separated from the airborne payload software so that the receiver and decoding system can be tested independently.

---

# Airborne and Stationary Configurations

The repository contains separate `air` and `stationary` implementations because the two operating environments have different requirements.

### Stationary

The stationary configuration is intended for:

- controlled testing;
- GPS testing;
- telemetry testing;
- data collection;
- transmitter/receiver experiments; and
- analysis of experimental GPS data.

### Airborne

The airborne configuration is intended for:

- actual balloon operation;
- tracking;
- recovery;
- reduced unnecessary data transmission;
- appropriate telemetry intervals; and
- operation within the power constraints of the payload.

The two configurations should therefore **not automatically be assumed to be identical**.

Changes made to one configuration should be evaluated to determine whether the corresponding change is also required in the other.

---

# Installation

## Raspberry Pi System Requirements

The GPS subsystem requires the relevant GPSD software and Python GPS bindings.

On Raspberry Pi OS/Debian, install:

```bash
sudo apt update
sudo apt install gpsd gpsd-clients python3-gps python3-pip
```

The repository also provides a Python requirements file:

```bash
python3 -m pip install -r requirements.txt
```

### Important

`requirements.txt` contains Python package dependencies.

The following are **system packages** and therefore should be installed using `apt`:

```text
gpsd
gpsd-clients
python3-gps
python3-pip
```

They should not simply be listed as ordinary entries in a pip requirements file.

A future `setup.sh` script can automate both the system-package installation and Python dependency installation if desired.

---

# Running the GPS System

## 1. Verify the GPS

From the repository:

```bash
cd programs/gps_test
python3 verify.py
```

Confirm that readings are being received from the GPS module.

## 2. Prepare GPSD

Run:

```bash
sudo pkill -f "cat /dev/serial0"
sudo systemctl stop gpsd.socket gpsd.service
sudo gpsd /dev/serial0 -F /var/run/gpsd.sock -n
```

## 3. Start the GPS logger

For stationary testing:

```bash
cd programs/payload/stationary
python3 gps_execute.py
```

For airborne operation:

```bash
cd programs/payload/air
python3 gps_execute.py
```

The program will create the relevant log directory, create a session log, monitor GPS data, and update `latest_gps.json`.

## 4. Start telemetry

After valid GPS data is available:

```bash
cd programs/payload/stationary
python3 gps_transmit.py
```

or:

```bash
cd programs/payload/air
python3 gps_transmit.py
```

The transmitter reads the latest valid GPS position and sends the configured telemetry frame.

---

# Requirements

The Python requirements are intentionally kept in:

```text
requirements.txt
```

At present, the payload transmitter requires Raspberry Pi GPIO support.

The GPS Python interface is supplied by the Raspberry Pi/Debian `python3-gps` package because the GPS programs communicate with `gpsd`.

The complete dependency setup is therefore:

```text
Raspberry Pi OS
      │
      ├── gpsd
      ├── gpsd-clients
      ├── python3-gps
      └── python3-pip
             │
             ▼
      requirements.txt
             │
             └── Python packages
```

---

# Experimental Data

Generated GPS data is intentionally excluded from version control.

The payload programs generate:

```text
logs/
```

and:

```text
latest_gps.json
```

These files are runtime/experimental data rather than source code.

The `.gitignore` file therefore excludes these generated files and directories.

Historical experimental data can be retained separately and analysed using:

```text
programs/payload/stationary/analysis.py
```

---

# Development and Testing Workflow

The recommended development sequence is:

```text
1. Verify GPS hardware
        │
        ▼
2. Run programs/gps_test/verify.py
        │
        ▼
3. Prepare GPSD
        │
        ▼
4. Run gps_execute.py
        │
        ├──────────────► latest_gps.json
        │
        └──────────────► logs/*.csv
        │
        ▼
5. Verify GPS data
        │
        ▼
6. Run gps_transmit.py
        │
        ▼
7. Receive UHF transmission
        │
        ▼
8. Decode using gps_receive.ino
        │
        ▼
9. Process using ground_station.py
        │
        ▼
10. Log and analyse received telemetry
```

This workflow allows the GPS acquisition, payload processing, radio transmission, radio reception, decoding, and ground-station software to be tested as separate stages.

---

# Reproducibility

For each significant experiment, it is recommended to record:

- repository Git commit;
- payload configuration;
- GPS configuration;
- transmitter configuration;
- receiver configuration;
- antenna configuration;
- GPS logging interval;
- telemetry transmission interval;
- number of repeated transmissions;
- Manchester timing parameters;
- experiment start time;
- experiment end time; and
- relevant environmental conditions.

Generated experimental data should be associated with the corresponding repository commit so that results can be reproduced against the correct version of the software.

---

# Project Status

This repository is an evolving research and engineering project.

The software and documentation may be updated as the GPS, telemetry, receiver, and ground-station subsystems are developed and tested.

Planned and developing components include:

- airborne payload software;
- stationary testing software;
- GPS verification tools;
- UHF telemetry transmission;
- UHF telemetry reception;
- Arduino telemetry decoding;
- ground-station software;
- received-data logging;
- experimental analysis; and
- complete hardware and wiring documentation.

---

# Documentation

Additional project documentation is stored in:

```text
documents/
```

This directory is intended to contain the complete wiring diagrams, system diagrams, hardware documentation, datasheets, experimental documentation, and other supporting material.

---

# Licence

No licence has been specified for this repository yet.

A suitable open-source or research-specific licence can be added when the project is ready for public distribution.

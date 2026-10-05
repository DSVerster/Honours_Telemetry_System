#!/usr/bin/env python3
import gps
import csv
import json
import os
import time
from datetime import datetime, timezone

# Only latitude and longitude are required for a valid GPS position
REQUIRED_FIELDS = ["lat", "lon"]
MIN_MODE = 3  # 2 = 2D fix, 3 = 3D fix
LOG_INTERVAL = 5  # seconds

# Directory containing this Python script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Log directory
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")

# Create logs directory if it does not exist
os.makedirs(LOG_DIR, exist_ok=True)

# Time the program was started
START_TIME = datetime.now(timezone.utc)

# Unique log filename for this execution
LOG_FILENAME = (
    f"gps_log_{START_TIME.strftime('%Y-%m-%d_%H-%M-%S')}.csv"
)

LOG_FILE = os.path.join(LOG_DIR, LOG_FILENAME)
# File containing the latest valid GPS information
LATEST_FILE = os.path.join(SCRIPT_DIR, "latest_gps.json")

def is_complete(report):
    mode = getattr(report, "mode", 0)

    if (mode < MIN_MODE):
        return False, f"mode={mode} (need >= {MIN_MODE})"

    missing = [
        field for field in REQUIRED_FIELDS
        if getattr(report, field, None) is None
    ]

    if (missing):
        return False, f"missing: {', '.join(missing)}"
    return True, None

def create_log_file():
    # Create a new CSV file for this program execution.
    with open(LOG_FILE, "w", newline="") as file:
        writer = csv.writer(file)

        # Record when this logging session started
        writer.writerow([
            f"Logging session started: "
            f"{START_TIME.isoformat()}"
        ])

        writer.writerow([
            "system_time",
            "satellite_time",
            "latitude",
            "longitude",
            "altitude_m",
            "speed_mps",
            "track_deg",
            "satellites_used"
        ])

def log_gps_data(data):
    # Append a successful GPS fix to the current session log.
    with open(LOG_FILE, "a", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            data["system_time"],
            data["satellite_time"],
            data["latitude"],
            data["longitude"],
            data["altitude_m"],
            data["speed_mps"],
            data["track_deg"],
            data["satellites_used"]
        ])

def update_latest_gps(data):
    # Write the latest valid GPS fix to a JSON file. The temporary file prevents another program from reading a partially-written JSON file.
    temporary_file = LATEST_FILE + ".tmp"
    with open(temporary_file, "w") as file:
        json.dump(data, file, indent=4)
    os.replace(temporary_file, LATEST_FILE)

def main():
    create_log_file()
    session = gps.gps(mode=gps.WATCH_ENABLE)
    print("GPS monitoring started.")
    print(f"Logging to: {LOG_FILE}")
    print(f"Latest GPS data: {LATEST_FILE}")
    print(f"Valid GPS fixes are logged every {LOG_INTERVAL} seconds.")
    print("Press Ctrl+C to stop.\n")
    last_log_time = 0

    while (True):
        try:
            report = session.next()
        except StopIteration:
            continue
        except KeyError:
            continue
        
        if (report.get("class") != "TPV"):
            continue

        ok, reason = is_complete(report)

        if (not ok):
            continue

        sats = getattr(session, "satellites_used", 0)

        # Optional GPS values are allowed to be unavailable
        altitude = getattr(report, "alt", None)
        speed = getattr(report, "speed", None)
        track = getattr(report, "track", None)

        # System time from the Raspberry Pi
        system_time = datetime.now(timezone.utc).isoformat()

        # GPS time received from the satellites through the GPS receiver
        satellite_time = getattr(report, "time", None)

        latest_valid_fix = {
            "system_time": system_time,
            "satellite_time": satellite_time,
            "latitude": report.lat,
            "longitude": report.lon,
            "altitude_m": altitude,
            "speed_mps": speed,
            "track_deg": track,
            "satellites_used": sats
        }

        # ALWAYS update the latest GPS information.
        # This means geofencing/transmission can access
        # the newest valid position independently of
        # the 5-second research logging interval.
        update_latest_gps(latest_valid_fix)

        current_time = time.monotonic()

        # Log one valid GPS measurement every 5 seconds
        if (current_time - last_log_time >= LOG_INTERVAL):
            log_gps_data(latest_valid_fix)
            print(
                f"SYSTEM TIME: {system_time}  |  "
                f"SATELLITE TIME: "
                f"{satellite_time if satellite_time is not None else 'N/A'}"
            )
            print(
                f"VALID FIX LOGGED  "
                f"lat={report.lat:.6f}  "
                f"lon={report.lon:.6f}  "
                f"alt={altitude if altitude is not None else 'N/A'}m  "
                f"speed={speed if speed is not None else 'N/A'}m/s  "
                f"track={track if track is not None else 'N/A'}deg  "
                f"sats_used={sats}"
            )
            last_log_time = current_time

if (__name__ == "__main__"):
    try:
        main()
    except KeyboardInterrupt:
        print("\nGPS monitoring stopped.")

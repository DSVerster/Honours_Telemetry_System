#!/usr/bin/env python3
"""
GPS receive logger (PC/laptop side, connected to the Arduino over USB serial).

Reads the Arduino's serial output, looks for lines of the form:

    LOG,<OK|BAD>,<millis>,<RSSI_mV>,<payload text>

and, for OK frames with payload "<group_id>,<lat>,<lon>,<alt>,<hhmmss>",
tracks how many copies of each group_id have arrived. It does NOT write a
duplicate row to the log for every copy - instead, once FINALIZE_SECONDS
has passed with no new copy of a given group, it writes exactly ONE row
to logs/gps_received.csv recording the fix data and how many copies were
received for that transmission.

Requires pyserial:
    pip install pyserial

Usage:
    python3 gps_receive_logger.py --port /dev/ttyACM0
    python3 gps_receive_logger.py --port COM3 --baud 115200

Find your port:
    Linux/Mac: ls /dev/tty.*  or  ls /dev/ttyACM* /dev/ttyUSB*
    Windows:   Device Manager -> Ports (COM & LPT)
"""

import argparse, csv, os, time, serial
from datetime import datetime, timezone

FINALIZE_SECONDS = 10.0   # how long to wait after the last copy before
                          # treating a transmission group as "done" and
                          # writing its final row with the copy count

def parse_log_line(line):
    # Parse a 'LOG,...' line. Returns (status, millis, rssi_mv, payload_text) or None if the line isn't a valid LOG line.
    if not line.startswith("LOG,"):
        return None
    parts = line.split(",", 4)
    if len(parts) != 5:
        return None
    _, status, millis_str, rssi_str, payload_text = parts
    try:
        millis = int(millis_str)
        rssi_mv = int(rssi_str)
    except ValueError:
        return None
    return status, millis, rssi_mv, payload_text

def parse_gps_payload(payload_text):
    # Parse '<group_id>,<lat>,<lon>,<alt>,<hhmmss>'. Returns a dict or None if the payload doesn't match the expected GPS format (e.g. a non-GPS test beacon got decoded) - caller should just skip those.
    fields = payload_text.split(",")
    if len(fields) != 5:
        return None
    try:
        return {
            "group_id": int(fields[0]),
            "latitude": float(fields[1]),
            "longitude": float(fields[2]),
            "altitude_m": float(fields[3]),
            "fix_time_hhmmss": fields[4],
        }
    except ValueError:
        return None

def ensure_csv_header(csv_path):
    is_new = not os.path.exists(csv_path)
    if is_new:
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    f = open(csv_path, "a", newline="")
    writer = csv.writer(f)
    if is_new:
        writer.writerow([
            "logged_at_utc", "group_id", "latitude", "longitude",
            "altitude_m", "fix_time_hhmmss", "rssi_mv", "copies_received"
        ])
        f.flush()
    return f, writer

def main():
    p = argparse.ArgumentParser(description="GPS receive logger (Arduino serial -> CSV)")
    p.add_argument("--port", required=True, help="serial port, e.g. /dev/ttyACM0 or COM3")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--log-dir", default="logs", help="directory for gps_received.csv (default: ./logs)")
    p.add_argument("--finalize-seconds", type=float, default=FINALIZE_SECONDS,
                   help=f"seconds of silence before finalizing a group (default {FINALIZE_SECONDS})")
    args = p.parse_args()

    csv_path = os.path.join(args.log_dir, "gps_received.csv")
    csv_file, csv_writer = ensure_csv_header(csv_path)

    print(f"Listening on {args.port} @ {args.baud} baud. Logging unique fixes to {csv_path}")
    print("Ctrl+C to stop.\n")

    # group_id -> {"data": {...}, "rssi_mv": int, "copies": int, "last_seen": float}
    groups = {}

    def finalize_group(group_id):
        g = groups.pop(group_id)
        data = g["data"]
        csv_writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            data["group_id"],
            f'{data["latitude"]:.5f}',
            f'{data["longitude"]:.5f}',
            f'{data["altitude_m"]:.0f}',
            data["fix_time_hhmmss"],
            g["rssi_mv"],
            g["copies"],
        ])
        csv_file.flush()
        print(f"[logged] group {group_id}: "
              f"lat={data['latitude']:.5f} lon={data['longitude']:.5f} "
              f"alt={data['altitude_m']:.0f}m fix_time={data['fix_time_hhmmss']} "
              f"copies_received={g['copies']}")

    try:
        with serial.Serial(args.port, args.baud, timeout=1) as ser:
            while True:
                raw = ser.readline()
                if raw:
                    try:
                        line = raw.decode("ascii", errors="replace").strip()
                    except Exception:
                        line = None

                    if line:
                        parsed = parse_log_line(line)
                        if parsed:
                            status, millis, rssi_mv, payload_text = parsed
                            if status == "OK":
                                gps = parse_gps_payload(payload_text)
                                if gps:
                                    gid = gps["group_id"]
                                    now = time.monotonic()
                                    if gid not in groups:
                                        groups[gid] = {
                                            "data": gps,
                                            "rssi_mv": rssi_mv,
                                            "copies": 0,
                                            "last_seen": now,
                                        }
                                        print(f"[new]  group {gid}: first copy received")
                                    groups[gid]["copies"] += 1
                                    groups[gid]["last_seen"] = now
                                    print(f"       group {gid}: copy #{groups[gid]['copies']} "
                                          f"(RSSI={rssi_mv} mV)")

                # Finalize any groups that have gone quiet for long enough
                now = time.monotonic()
                done = [gid for gid, g in groups.items()
                        if now - g["last_seen"] >= args.finalize_seconds]
                for gid in done:
                    finalize_group(gid)

    except KeyboardInterrupt:
        pass
    finally:
        # Flush out whatever groups were still pending at shutdown
        for gid in list(groups.keys()):
            finalize_group(gid)
        csv_file.close()
        print("\nStopped.")

if __name__ == "__main__":
    main()

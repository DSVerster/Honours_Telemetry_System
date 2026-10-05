#!/usr/bin/env python3
"""
NTX2 GPS beacon transmitter (Raspberry Pi, RPi.GPIO, GPIO17).

Reads latest_gps.json from the current directory every --interval seconds
and transmits a compact Manchester-encoded frame with the current fix,
using the burst scheme already validated on the bench:

    6 copies per reading, back-to-back with no gap, repeated every
    --interval seconds (default 120s) -> ~90% per-reading success rate
    in testing with a 1kOhm R3 and --bit-us 4000.

Expected JSON shape (extra fields are ignored):
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

Payload format sent over the air (comma-separated, no labels, to save
bytes against the 40-byte frame limit):

    <transmission_counter><lat 5dp>,<lon 5dp>,<alt m, whole>,<HHMMSS of fix time>

Example: "1,-26.68863,27.09528,1344,022306"  (about 32 bytes)

The receiver (rx_manchester.ino / the diagnostic build) needs NO changes:
it already prints whatever ASCII text is in the payload field.

Usage:
    python3 gps_transmit.py
    python3 gps_transmit.py --json-path /home/strato/latest_gps.json
    python3 gps_transmit.py --interval 120 --repeats 6

Run with sudo for GPIO access / better timing.
"""

import argparse
import gc
import json
import os
import time
from datetime import datetime, timezone

import RPi.GPIO as GPIO

# ---------- timing ----------

def wait_until(deadline):
    # Sleep most of the way, then spin for the last 2 ms for accuracy.
    while True:
        remaining = deadline - time.perf_counter()
        if (remaining <= 0):
            return
        if (remaining > 0.0025):
            time.sleep(remaining - 0.002)

def play(pin, levels, tick_seconds, idle_level):
    # Output one level per tick, then return the line to its idle level.
    gc.disable()
    try:
        deadline = time.perf_counter()
        for level in levels:
            GPIO.output(pin, level)
            deadline += tick_seconds
            wait_until(deadline)
    finally:
        GPIO.output(pin, idle_level)
        gc.enable()

# ---------- Manchester framing (matches the Arduino decoder exactly) ----------

PREAMBLE = b"\xAA" * 6
SYNC = b"\x2D\xD4"
MAX_PAYLOAD_BYTES = 40  # must match MAX_PAYLOAD in the Arduino sketch

def crc8(data):
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc

def build_frame(payload):
    if len(payload) == 0 or len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"payload must be 1-{MAX_PAYLOAD_BYTES} bytes, got {len(payload)}")
    body = bytes([len(payload)]) + payload
    return PREAMBLE + SYNC + body + bytes([crc8(body)])

def to_half_bits(frame):
    # Manchester (IEEE 802.3): bit 1 = LOW then HIGH, bit 0 = HIGH then LOW.
    halves = []
    for byte in frame:
        for i in range(7, -1, -1):
            halves.extend([0, 1] if ((byte >> i) & 1) else [1, 0])
    return halves

def send_burst(pin, payload, repeats, gap_seconds, bit_us):
    # Send `repeats` copies of the same frame, each separated by gap_seconds of idle. Returns (total_on_air_seconds, per_copy_seconds).
    half_seconds = bit_us / 2 / 1_000_000
    one_frame_halves = to_half_bits(build_frame(payload))
    per_copy_seconds = len(one_frame_halves) * half_seconds

    for i in range(repeats):
        play(pin, one_frame_halves, half_seconds, GPIO.LOW)
        if i < repeats - 1 and gap_seconds > 0:
            time.sleep(gap_seconds)

    total_seconds = repeats * per_copy_seconds + max(0, repeats - 1) * gap_seconds
    return total_seconds, per_copy_seconds

# ---------- GPS JSON -> compact payload ----------

def fix_time_hhmmss(satellite_time_str):
    # Extract HHMMSS from an ISO-ish timestamp like '2026-09-19T02:23:06.000Z'. Falls back to current UTC time if parsing fails.
    try:
        # Handle both '...Z' and '...+00:00' style suffixes
        s = satellite_time_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
    except (ValueError, AttributeError, TypeError):
        dt = datetime.now(timezone.utc)
    return dt.strftime("%H%M%S")

def build_gps_payload(fix, transmission_counter):
    # Build the compact comma-separated payload string from a parsed latest_gps.json dict. Raises KeyError/TypeError if required fields are missing or malformed - caller should catch and skip that cycle.
    lat = float(fix["latitude"])
    lon = float(fix["longitude"])
    alt = float(fix["altitude_m"])
    hhmmss = fix_time_hhmmss(fix.get("satellite_time"))

    text = f"{transmission_counter},{lat:.5f},{lon:.5f},{alt:.0f},{hhmmss}"
    payload = text.encode("ascii")

    if len(payload) > MAX_PAYLOAD_BYTES:
        # Fall back to fewer decimal places if somehow too long (e.g. huge altitude)
        text = f"{transmission_counter},{lat:.4f},{lon:.4f},{alt:.0f},{hhmmss}"
        payload = text.encode("ascii")

    return text, payload

def read_latest_fix(json_path):
    with open(json_path, "r") as f:
        return json.load(f)

# ---------- main ----------

def parse_args():
    p = argparse.ArgumentParser(description="NTX2 GPS beacon transmitter")
    p.add_argument("--gpio", type=int, default=17)
    p.add_argument("--bit-us", type=int, default=4000,
                   help="Manchester bit period in microseconds (default 4000, matches tested setup)")
    p.add_argument("--repeats", type=int, default=6,
                   help="copies of the frame per reading, back-to-back (default 6, matches the "
                        "~90%% success-rate test)")
    p.add_argument("--gap-ms", type=float, default=0.0,
                   help="idle gap in milliseconds between copies within one burst (default 0)")
    p.add_argument("--interval", type=float, default=120.0,
                   help="seconds between readings/bursts (default 120)")
    p.add_argument("--json-path", default="latest_gps.json",
                   help="path to the GPS JSON file (default: latest_gps.json in the current directory)")
    p.add_argument("--seconds", type=float, default=0,
                   help="stop after N seconds total (0 = run until Ctrl+C)")
    return p.parse_args()

def main():
    args = parse_args()

    try:
        os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(50))
    except (AttributeError, PermissionError, OSError):
        pass

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(args.gpio, GPIO.OUT, initial=GPIO.LOW)

    end_time = None if (args.seconds <= 0) else time.monotonic() + args.seconds
    print(f"NTX2 GPS beacon on GPIO{args.gpio}. Ctrl+C to stop.")
    print(f"Reading: {args.json_path}")
    print(f"Sending {args.repeats} copies per reading, {args.gap_ms:g} ms gap between copies, "
          f"every {args.interval:g}s.\n")
    transmission_counter = 0 #Counter used to define identifier for transmissions
    try:
        while (end_time is None or time.monotonic() < end_time):
            cycle_start = time.monotonic()
            try:
                fix = read_latest_fix(args.json_path)
                text, payload = build_gps_payload(fix, transmission_counter)

                total_s, per_copy_s = send_burst(
                    args.gpio, payload, args.repeats, args.gap_ms / 1000.0, args.bit_us
                )
                print(f"sent: {text}  ({len(payload)} bytes)  x{args.repeats} copies  "
                      f"({total_s:.2f} s total, {per_copy_s:.2f} s/copy)")
                transmission_counter += 1 
            except FileNotFoundError:
                print(f"[warn] {args.json_path} not found - skipping this cycle")
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                print(f"[warn] bad/incomplete GPS data ({e}) - skipping this cycle")

            elapsed = time.monotonic() - cycle_start
            sleep_for = max(0.0, args.interval - elapsed)
            time.sleep(sleep_for)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.output(args.gpio, GPIO.LOW)
        GPIO.cleanup()
        print("\nStopped.")

if (__name__ == "__main__"):
    main()

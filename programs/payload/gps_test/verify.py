#!/usr/bin/env python3
"""
GPS Fix Monitor
Reads GPS data from gpsd and displays the most recent GPS information
every 2 seconds.
Latitude and longitude are required for a valid position.
Altitude, speed and track are optional and will display as N/A when
the GPS has not provided them yet.
Press Ctrl+C to stop.
"""

import gps
import time
from datetime import datetime, timezone

DISPLAY_INTERVAL = 2.0

def main():
    session = gps.gps(mode=gps.WATCH_ENABLE)
    print("GPS monitor started (Ctrl+C to stop)...\n")
    # Remember the most recent values received from the GPS
    lat = None
    lon = None
    alt = None
    speed = None
    track = None
    mode = 0
    sats = "?"

    last_display = 0

    while True:
        try:
            report = session.next()
        except StopIteration:
            continue
        except KeyError:
            continue
        except KeyboardInterrupt:
            print("\nGPS monitor stopped.")
            break
        # Only process TPV (Time-Position-Velocity) reports
        if report.get("class") != "TPV":
            continue
        # Update values whenever they are available
        if getattr(report, "lat", None) is not None:
            lat = report.lat
        if getattr(report, "lon", None) is not None:
            lon = report.lon
        if getattr(report, "alt", None) is not None:
            alt = report.alt
        if getattr(report, "speed", None) is not None:
            speed = report.speed
        if getattr(report, "track", None) is not None:
            track = report.track
        if getattr(report, "mode", None) is not None:
            mode = report.mode
        # Get satellites currently being used
        try:
            sats = session.satellites_used
        except AttributeError:
            sats = "?"
        # Only display every 2 seconds
        now = time.monotonic()
        if now - last_display < DISPLAY_INTERVAL:
            continue
        last_display = now
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        # Determine whether we have a usable position
        if lat is not None and lon is not None and mode >= 2:
            lat_text = f"{lat:.6f}"
            lon_text = f"{lon:.6f}"
            alt_text = f"{alt:.1f} m" if alt is not None else "N/A"
            speed_text = f"{speed:.2f} m/s" if speed is not None else "N/A"
            track_text = f"{track:.1f}°" if track is not None else "N/A"
            print(
                f"[{ts}] GPS FIX | "
                f"mode={mode} | "
                f"lat={lat_text} | "
                f"lon={lon_text} | "
                f"alt={alt_text} | "
                f"speed={speed_text} | "
                f"track={track_text} | "
                f"sats={sats}"
            )
        else:
            print(
                f"[{ts}] NO POSITION FIX | "
                f"mode={mode} | "
                f"sats={sats}"
            )

if __name__ == "__main__":
    main()

#!/usr/bin/env python3

import csv, math, os, statistics
from datetime import datetime

# CONFIGURATION
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
OUTPUT_FILE = os.path.join(BASE_DIR, "log_analysis.txt")
JUMP_THRESHOLD = 5.0  # metres

# HELPER FUNCTIONS
def distance(lat1, lon1, lat2, lon2):
    #Calculate distance between two GPS coordinates in metres.
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = min(1.0, max(0.0, math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def fmt(value, unit=""):
    #Format numerical values for the report.
    return "N/A" if value is None else f"{value:.3f}{unit}" if isinstance(value, float) else f"{value}{unit}"

def make_table(headers, rows):
    #Create a simple text table.
    if (not rows): return []
    widths = [max(len(str(headers[i])), max(len(str(row[i])) for row in rows)) for i in range(len(headers))]
    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    header = "| " + " | ".join(str(headers[i]).ljust(widths[i]) for i in range(len(headers))) + " |"
    return [sep, header, sep] + ["| " + " | ".join(str(row[i]).ljust(widths[i]) for i in range(len(headers))) + " |" for row in rows] + [sep]

# GPS LOG ANALYSIS
def analyse_file(path):
    #Analyse one GPS CSV file.
    with open(path, newline="", encoding="utf-8") as f:
        f.readline()  # Skip metadata header line
        reader = csv.DictReader(f)
        if (not {"latitude", "longitude", "altitude_m", "speed_mps", "satellites_used"}.issubset(reader.fieldnames or [])):
            return None
        rows = list(reader)

    valid_rows = []
    for row in rows:
        try:
            valid_rows.append((row, float(row["latitude"]), float(row["longitude"])))
        except (KeyError, TypeError, ValueError):
            continue

    if (len(valid_rows) < 2): return None

    latitudes, longitudes = [r[1] for r in valid_rows], [r[2] for r in valid_rows]
    altitudes, speeds, satellites = [], [], []

    for r, _, _ in valid_rows:
        for target, key in [(altitudes, "altitude_m"), (speeds, "speed_mps"), (satellites, "satellites_used")]:
            try: target.append(float(r[key]))
            except (KeyError, TypeError, ValueError): pass

    ref_lat, ref_lon = statistics.mean(latitudes), statistics.mean(longitudes)
    deviations = [distance(ref_lat, ref_lon, lat, lon) for lat, lon in zip(latitudes, longitudes)]
    changes = [distance(latitudes[i - 1], longitudes[i - 1], latitudes[i], longitudes[i]) for i in range(1, len(latitudes))]

    return {
        "file": os.path.basename(path), "readings": len(valid_rows),
        "mean_deviation": statistics.mean(deviations), "std_deviation": statistics.stdev(deviations), "max_deviation": max(deviations),
        "lat_std": statistics.stdev(latitudes), "lon_std": statistics.stdev(longitudes),
        "alt_mean": statistics.mean(altitudes) if altitudes else None,
        "alt_std": statistics.stdev(altitudes) if len(altitudes) > 1 else None,
        "alt_range": max(altitudes) - min(altitudes) if altitudes else None,
        "speed_mean": statistics.mean(speeds) if speeds else None, "speed_max": max(speeds) if speeds else None,
        "sat_mean": statistics.mean(satellites) if satellites else None,
        "sat_min": min(satellites) if satellites else None, "sat_max": max(satellites) if satellites else None,
        "change_mean": statistics.mean(changes), "change_max": max(changes),
        "jumps": sum(c > JUMP_THRESHOLD for c in changes)
    }

# MAIN
def main():
    print(f"\n{'=' * 78}\n                         GPS LOG ANALYSIS\n{'=' * 78}")
    if (not os.path.exists(LOG_DIR)):
        os.makedirs(LOG_DIR)
        print(f"\nLog directory created at: {LOG_DIR}\nPlease place .csv log files in this directory and re-run.")
        return

    files = sorted(fn for fn in os.listdir(LOG_DIR) if fn.lower().endswith(".csv"))
    total_files, results, empty_files = len(files), [], []

    for filename in files:
        path = os.path.join(LOG_DIR, filename)
        try:
            res = analyse_file(path)
            if (res is None or res["readings"] < 2):
                empty_files.append(filename)
                print(f"  [EMPTY]    {filename}")
            else:
                results.append(res)
                print(f"  [ANALYSED] {filename:<42}{res['readings']:>4} readings")
        except Exception as error:
            empty_files.append(filename)
            print(f"  [ERROR]    {filename} ({error})")

    total_readings = sum(r["readings"] for r in results)

    # BUILD REPORT
    report = [
        f"{'=' * 78}\n                         GPS LOG ANALYSIS\n{'=' * 78}\n"
        f"Generated: {datetime.now().astimezone().isoformat()}\n\n"
        f"DETAILED MEASUREMENTS\n{'-' * 78}"
    ]

    if (results):
        for r in results:
            report.append(
                f"\nFILE: {r['file']}\nReadings: {r['readings']}\n\n"
                f"  Positional deviation: mean={fmt(r['mean_deviation'], ' m')}, std={fmt(r['std_deviation'], ' m')}, max={fmt(r['max_deviation'], ' m')}\n"
                f"  Position variation: latitude std={fmt(r['lat_std'])}, longitude std={fmt(r['lon_std'])}\n"
                f"  Altitude: mean={fmt(r['alt_mean'], ' m')}, std={fmt(r['alt_std'], ' m')}, range={fmt(r['alt_range'], ' m')}\n"
                f"  Speed: mean={fmt(r['speed_mean'], ' m/s')}, max={fmt(r['speed_max'], ' m/s')}\n"
                f"  Satellites: mean={fmt(r['sat_mean'])}, min={fmt(r['sat_min'])}, max={fmt(r['sat_max'])}\n"
                f"  Consecutive position changes: mean={fmt(r['change_mean'], ' m')}, max={fmt(r['change_max'], ' m')}, jumps > {JUMP_THRESHOLD:.0f} m={r['jumps']}"
            )
    else:
        report.append("\nNo usable GPS logs were found.")

    # INDIVIDUAL LOG RESULTS
    report.append(f"\n\nINDIVIDUAL LOG RESULTS\n{'-' * 78}\n")
    if (results):
        headers = ["Log file", "Readings", "Mean Dev.", "Max Dev.", "Mean Change", "Max Change", "Jumps"]
        rows = [[r["file"], r["readings"], fmt(r["mean_deviation"], " m"), fmt(r["max_deviation"], " m"), fmt(r["change_mean"], " m"), fmt(r["change_max"], " m"), r["jumps"]] for r in results]
        report.extend(make_table(headers, rows))
    else:
        report.append("No usable GPS logs were found.")

    # OVERALL SUMMARY
    report.append(f"\n\n{'=' * 78}\n                           OVERALL SUMMARY\n{'=' * 78}\n")
    report.extend(make_table(["Measurement", "Value"], [
        ["Total CSV files read", total_files],
        ["Files containing GPS values", len(results)],
        ["Empty CSV files", len(empty_files)],
        ["Total GPS readings", total_readings]
    ]))

    if (results):
        m_devs = [r["mean_deviation"] for r in results]
        chgs = [r["change_mean"] for r in results if r["change_mean"] is not None]
        metrics = [
            ["Average positional deviation", f"{statistics.mean(m_devs):.3f} m"],
            ["Largest positional deviation", f"{max(r['max_deviation'] for r in results):.3f} m"],
            ["Average consecutive position change", f"{statistics.mean(chgs):.3f} m" if chgs else "N/A"],
            [f"Total jumps > {JUMP_THRESHOLD:.0f} m", sum(r["jumps"] for r in results)]
        ]
        report.append("\n")
        report.extend(make_table(["GPS Metric", "Result"], metrics))

    # INTERPRETATION
    report.append(
        f"\n\nINTERPRETATION\n{'-' * 78}\n\n"
        "Each CSV is analysed independently using its own mean latitude/longitude as the reference position.\n\n"
        "Therefore, positional deviation represents GPS consistency/repeatability rather than absolute accuracy against a surveyed reference coordinate.\n\n"
        "For a stationary receiver, speed should ideally remain close to 0 m/s. Consecutive position changes therefore indicate apparent GPS movement or measurement variation.\n\n"
        f"A position change greater than {JUMP_THRESHOLD:.0f} m is classified as a jump.\n\n"
        "Track is not included because it is not particularly meaningful when the GPS receiver is stationary."
    )

    # SAVE REPORT
    report_text = "\n".join(report)
    print(f"\n{report_text}")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f: f.write(report_text)
    print(f"\n{'=' * 78}\nReport saved to: {OUTPUT_FILE}\n{'=' * 78}")

    # EMPTY FILE CLEANUP
    if (empty_files):
        print(f"\n{'-' * 78}\nEMPTY CSV CLEANUP\n{'-' * 78}\n\nTotal files read:       {total_files}\nFiles with GPS values:  {len(results)}\nEmpty files:            {len(empty_files)}\n\nA CSV with fewer than 2 valid GPS readings is considered empty.\n")
        if (input("Delete the empty CSV files? [y/N]: ").strip().lower() in ("y", "yes")):
            deleted = 0
            for fn in empty_files:
                try:
                    os.remove(os.path.join(LOG_DIR, fn))
                    deleted += 1
                    print(f"  Deleted: {fn}")
                except OSError as err:
                    print(f"  Could not delete {fn}: {err}")
            print(f"\nDeleted {deleted} of {len(empty_files)} empty CSV file(s).")
        else:
            print("\nNo files were deleted.")

if (__name__ == "__main__"):
    main()

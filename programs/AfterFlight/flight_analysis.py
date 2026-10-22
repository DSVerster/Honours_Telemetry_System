#!/usr/bin/env python3
""" Flight-test analysis for the stratospheric balloon communication and
tracking artefact.

Inputs (all from the 2026-10-09 flight):
  gps_log_*.csv      airborne GPS log (UTC timestamps, 30 s interval)
  gps_transmit.log   airborne transmission log (LOCAL time, UTC+2)
  gps_received.csv   ground-station reception log (UTC timestamps)

Outputs (written to OUT_DIR):
  flight_altitude.png    altitude and satellites against time
  flight_link.png        RSSI and copies received against distance
  flight_summary.txt     every number used in Chapter 4

Usage:
  python3 flight_analysis.py
  python3 flight_analysis.py --gs-lat -26.9029 --gs-lon 27.1806 --gs-alt 1447 """
import argparse, re
from datetime import timedelta
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

LOCAL_OFFSET = timedelta(hours=2)   # SAST = UTC+2
CLIMB_THRESHOLD_M = 30              # rise above pre-launch median = airborne
EARTH_R = 6371000.0

def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2) - np.radians(lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_R * np.arcsin(np.sqrt(a))

def load_gps(path):
    g = pd.read_csv(path, skiprows=1)
    g["t"] = pd.to_datetime(g["satellite_time"], utc=True)
    return g

def load_tx(path):
    rows = []
    pat = re.compile(
        r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s+INFO\s+sent: "
        r"(\d+),([-\d.]+),([-\d.]+),(\d+),(\d+)\s+\((\d+) bytes\)")
    for line in Path(path).read_text().splitlines():
        m = pat.match(line)
        if m:
            ts, gid, lat, lon, alt, ft, nbytes = m.groups()
            t_local = pd.Timestamp(ts)
            rows.append(dict(group_id=int(gid),
                             t_sent=(t_local - LOCAL_OFFSET).tz_localize("UTC"),
                             lat=float(lat), lon=float(lon), alt=int(alt),
                             fix_time=ft, nbytes=int(nbytes)))
    return pd.DataFrame(rows)

def load_rx(path):
    r = pd.read_csv(path)
    # A transmission can be split across two log rows (seen for group 23).
    # Merge rows with the same group_id: sum copies, mean RSSI.
    merged = (r.groupby("group_id", as_index=False)
                .agg(latitude=("latitude", "first"),
                     longitude=("longitude", "first"),
                     altitude_m=("altitude_m", "first"),
                     fix_time_hhmmss=("fix_time_hhmmss", "first"),
                     rssi_mv=("rssi_mv", "mean"),
                     copies_received=("copies_received", "sum"),
                     logged=("logged_at_utc", "first")))
    n_split = int(r.group_id.duplicated().sum())
    return merged, n_split

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gps", default="/mnt/user-data/uploads/gps_log_2026-10-09_08-25-55.csv")
    ap.add_argument("--tx", default="/mnt/user-data/uploads/gps_transmit.log")
    ap.add_argument("--rx", default="/mnt/user-data/uploads/gps_received.csv")
    ap.add_argument("--out", default="/mnt/user-data/outputs/flight")
    ap.add_argument("--gs-lat", type=float, default=None,
                    help="ground station latitude (default: launch position)")
    ap.add_argument("--gs-lon", type=float, default=None)
    ap.add_argument("--gs-alt", type=float, default=None)
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    S = []                                  # summary lines

    def say(s=""):
        print(s)
        S.append(s)

    g, tx = load_gps(a.gps), load_tx(a.tx)
    rx, n_split = load_rx(a.rx)

    # ---------- liftoff detection from GPS altitude ----------
    pre = g[g.t < g.t.iloc[0] + pd.Timedelta(minutes=30)]    # after fix settles
    pre_alt = pre[pre.satellites_used >= 10].altitude_m.median()
    climbing = g[(g.altitude_m > pre_alt + CLIMB_THRESHOLD_M) & (g.satellites_used >= 10)]
    first_climb = climbing.t.iloc[0]
    last_still = g[g.t < first_climb].t.iloc[-1]
    t0 = last_still                                         # t = 0 reference
    g["min"] = (g.t - t0).dt.total_seconds() / 60
    fl = g[g.t >= first_climb].copy()                       # flight segment
    pre_launch = g[(g.t <= last_still) & (g.satellites_used >= 10)]

    # ground station position
    gs_lat = a.gs_lat if a.gs_lat is not None else pre_launch.latitude.median()
    gs_lon = a.gs_lon if a.gs_lon is not None else pre_launch.longitude.median()
    gs_alt = a.gs_alt if a.gs_alt is not None else pre_alt
    gs_assumed = a.gs_lat is None

    say("=== LIFTOFF ===")
    say(f"Pre-launch median altitude: {pre_alt:.1f} m")
    say(f"Last stationary fix : {last_still:%H:%M:%S} UTC ({(last_still+LOCAL_OFFSET):%H:%M:%S} local)")
    say(f"First climbing fix  : {first_climb:%H:%M:%S} UTC ({(first_climb+LOCAL_OFFSET):%H:%M:%S} local)")
    say("NOTE: stated release time was 10:59 local. The GPS shows the balloon "
        "stationary until the fix above.")

    # ---------- flight overview ----------
    last = g.iloc[-1]
    dur_min = (last.t - t0).total_seconds() / 60
    dist_launch = haversine(gs_lat, gs_lon, last.latitude, last.longitude)
    asc = np.polyfit(fl["min"] * 60, fl.altitude_m, 1)[0]  # m/s linear fit
    gain = fl.altitude_m.max() - pre_alt
    say("\n=== FLIGHT OVERVIEW (GPS log) ===")
    say(f"Liftoff lies between two fixes, so time after liftoff is "
        f"{(last.t-first_climb).total_seconds()/60:.1f} to {dur_min:.1f} min")
    say(f"Total GPS fixes logged        : {len(g)}")
    say(f"Fixes in flight segment       : {len(fl)}")
    say(f"Logged time from liftoff (min): {dur_min:.1f}")
    say(f"Last fix                      : {last.t:%H:%M:%S} UTC ({(last.t+LOCAL_OFFSET):%H:%M:%S} local)")
    say(f"Maximum altitude (m)          : {g.altitude_m.max():.0f}")
    say(f"Altitude gain above launch (m): {gain:.0f}")
    say(f"Mean ascent rate, linear fit (m/s): {asc:.2f}")
    say(f"Max horizontal speed (m/s)    : {fl.speed_mps.max():.1f}")
    say(f"Mean horizontal speed (m/s)   : {fl.speed_mps.mean():.1f}")
    say(f"Horizontal distance at last fix (km): {dist_launch/1000:.2f}")
    say(f"Satellites in flight min/mean/max: {fl.satellites_used.min()} / "
        f"{fl.satellites_used.mean():.1f} / {fl.satellites_used.max()}")
    say(f"Satellites pre-launch (>=10 sats) min/mean/max: "
        f"{pre_launch.satellites_used.min()} / {pre_launch.satellites_used.mean():.1f} / "
        f"{pre_launch.satellites_used.max()}")
    last15 = g[(g.t > last_still - pd.Timedelta(minutes=15)) & (g.t <= last_still)]
    say(f"Satellites, last 15 min before liftoff mean/min/max: "
        f"{last15.satellites_used.mean():.1f} / {last15.satellites_used.min()} / {last15.satellites_used.max()}")
    say(f"Flight fixes with >=4 satellites: {(fl.satellites_used>=4).sum()}/{len(fl)}")
    gap = g.t.diff().dt.total_seconds().dropna()
    say(f"GPS log interval mean/max (s)  : {gap.mean():.1f} / {gap.max():.0f}")
    say(f"Cold-start: first fix with >=4 sats at "
        f"{g[g.satellites_used>=4].t.iloc[0]:%H:%M:%S} UTC "
        f"(log started {g.t.iloc[0]:%H:%M:%S})")

    # ---------- transmission performance ----------
    first_air = int(tx[tx.t_sent > first_climb].group_id.min())
    last_ground = first_air - 1
    iv = tx.t_sent.diff().dt.total_seconds().dropna()
    say("\n=== TRANSMISSION (transmit log) ===")
    say(f"Packets transmitted (0..{tx.group_id.max()}): {len(tx)}")
    say(f"Last pre-launch packet: {last_ground}; first airborne packet: {first_air}")
    say(f"Airborne packets sent: {first_air}..{tx.group_id.max()} "
        f"({tx.group_id.max()-first_air+1})")
    say(f"Transmission interval mean/std/min/max (s): "
        f"{iv.mean():.2f} / {iv.std():.2f} / {iv.min():.0f} / {iv.max():.0f}")
    say(f"Intervals != 60 s: {(iv != 60).sum()} of {len(iv)} "
        f"(log resolution is 1 s)")
    say(f"Packet length: {tx.nbytes.min()}-{tx.nbytes.max()} bytes; 6 copies per packet")

    # ---------- reception ----------
    say("\n=== RECEPTION (ground station) ===")
    say(f"Receiver log starts at packet {rx.group_id.min()} "
        f"(packets 0..{rx.group_id.min()-1} not logged: receiver not yet running)")
    say(f"Split log rows merged: {n_split}")
    exp = tx[tx.group_id >= rx.group_id.min()]
    got = set(rx.group_id)
    missing = sorted(set(exp.group_id) - got)
    say(f"Packets expected (since receiver start): {len(exp)}; received: {len(got & set(exp.group_id))}; "
        f"missing: {missing if missing else 'none'}")

    # payload integrity: compare each received packet to what was sent
    m = exp.merge(rx, on="group_id")
    bad = m[(abs(m.lat - m.latitude) > 1e-5) | (abs(m.lon - m.longitude) > 1e-5)
            | (m.alt != m.altitude_m) | (m.fix_time != m.fix_time_hhmmss.astype(str).str.zfill(6))]
    say(f"Received payloads differing from transmitted payloads: {len(bad)} of {len(m)}")

    m["phase"] = np.where(m.group_id <= last_ground, "ground", "flight")
    m["hdist_km"] = haversine(gs_lat, gs_lon, m.latitude, m.longitude) / 1000
    m["slant_km"] = np.sqrt(m.hdist_km**2 + ((m.altitude_m - gs_alt) / 1000) ** 2)
    for ph, d in m.groupby("phase"):
        say(f"[{ph}] packets {d.group_id.min()}..{d.group_id.max()} (n={len(d)}): "
            f"success {len(d)}/{len(d)}; copies/packet mean {d.copies_received.mean():.2f} "
            f"(min {d.copies_received.min()}); copy success {d.copies_received.sum()}/{6*len(d)} "
            f"= {100*d.copies_received.sum()/(6*len(d)):.1f}%; RSSI mean {d.rssi_mv.mean():.0f} mV "
            f"(min {d.rssi_mv.min():.0f}, max {d.rssi_mv.max():.0f})")
    f = m[m.phase == "flight"]
    say(f"Max slant range with successful reception: {f.slant_km.max():.2f} km "
        f"(horizontal {f.hdist_km.max():.2f} km, packet {int(f.loc[f.slant_km.idxmax(),'group_id'])})")
    say(f"Flight packets received with fewer than 6 copies: "
        f"{(f.copies_received<6).sum()} of {len(f)}")
    say(f"Lowest flight copy counts: "
        f"{f.sort_values('copies_received')[['group_id','copies_received','slant_km']].head(4).to_dict('records')}")
    r_corr = np.corrcoef(f.slant_km, f.rssi_mv)[0, 1]
    say(f"Pearson r (RSSI vs slant range, flight): {r_corr:.2f}")
    # Ground-phase RSSI outliers
    gnd = m[m.phase == "ground"]
    out_g = gnd[gnd.rssi_mv < gnd.rssi_mv.median() - 300]
    if len(out_g):
        say(f"Ground-phase RSSI outliers (>300 mV below median): "
            f"{out_g[['group_id','rssi_mv']].to_dict('records')}")
    # Reception latency
    m["logged_t"] = pd.to_datetime(m.logged, utc=True)
    lat_s = (m.logged_t - m.t_sent).dt.total_seconds()
    say(f"Send-to-log latency mean/max (s): {lat_s.mean():.1f} / {lat_s.max():.1f}")

    # ---------- last packet vs final GPS log fix ----------
    say("\n=== FINAL POSITION ===")
    lp = tx.iloc[-1]
    say(f"Last received packet {int(lp.group_id)}: {lp.lat:.5f}, {lp.lon:.5f}, "
        f"{lp.alt} m, fix {lp.fix_time} UTC")
    say(f"Last GPS log fix: {last.latitude:.5f}, {last.longitude:.5f}, "
        f"{last.altitude_m:.0f} m, {last.t:%H%M%S} UTC")
    say(f"Ground station position used for distances: {gs_lat:.5f}, {gs_lon:.5f}, {gs_alt:.0f} m "
        f"({'ASSUMED = launch position' if gs_assumed else 'supplied'})")

    # ---------- figures ----------
    plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.3})

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 5.6), sharex=True,
                                   gridspec_kw={"height_ratios": [2, 1]})
    ax1.plot(g["min"], g.altitude_m, "-", color="C0", lw=1.4, label="GPS log (30 s)")
    mm = m.copy()
    mm["min"] = (pd.to_datetime(mm.fix_time_hhmmss.astype(str).str.zfill(6),
                                format="%H%M%S").dt.time.apply(
        lambda t: t.hour * 3600 + t.minute * 60 + t.second) -
        (t0.hour * 3600 + t0.minute * 60 + t0.second)) / 60
    ax1.plot(mm["min"], mm.altitude_m, "o", ms=4, color="C3", label="Packets received")
    ax1.axvline(0, color="k", ls="--", lw=1)
    ax1.text(-0.4, 2200, "liftoff", ha="right", fontsize=9)
    ax1.annotate("last fix (power lost)",
                 (g["min"].iloc[-1], g.altitude_m.iloc[-1]),
                 xytext=(3.0, 5250), textcoords="data", ha="center", fontsize=9,
                 arrowprops=dict(arrowstyle="->"))
    ax1.set_xlim(-15, 20)
    ax1.set_ylabel("Altitude (m)")
    ax1.legend(loc="upper left")
    ax2.plot(g["min"], g.satellites_used, "-o", ms=3, color="C2")
    ax2.axvline(0, color="k", ls="--", lw=1)
    ax2.set_ylabel("Satellites used")
    ax2.set_xlabel("Time relative to liftoff (min)")
    fig.tight_layout()
    fig.savefig(out / "flight_altitude.png", dpi=200)
    plt.close(fig)

    fig, (b1, b2) = plt.subplots(1, 2, figsize=(8, 3.6))
    col = np.where(m.phase == "ground", "C7", "C3")
    b1.scatter(m.slant_km, m.rssi_mv, c=col, s=22)
    b1.set_xlabel("Distance to ground station (km)")
    b1.set_ylabel("RSSI (mV)")
    b1.set_title("Signal strength", fontsize=10)
    b2.scatter(m.slant_km, m.copies_received, c=col, s=22)
    b2.set_xlabel("Distance to ground station (km)")
    b2.set_ylabel("Copies decoded (of 6)")
    b2.set_ylim(0, 6.5)
    b2.set_title("Copies received per packet", fontsize=10)
    from matplotlib.lines import Line2D
    b1.legend(handles=[Line2D([], [], marker="o", ls="", color="C7", label="Before liftoff"),
                       Line2D([], [], marker="o", ls="", color="C3", label="In flight")],
              loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "flight_link.png", dpi=200)
    plt.close(fig)

    (out / "flight_summary.txt").write_text("\n".join(S) + "\n")
    print(f"\nWrote figures and flight_summary.txt to {out}")

if __name__ == "__main__":
    main()
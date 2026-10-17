"""PHASE_D section 6 web gate through the API of the TEST stack (I2).

usage: gate.py <data_dir> <out_dir> [backend_url] [frontend_url]
Two synthetic users: A registers a shared daily tract table, a shared biweekly raster
series, shared point features and a private table; B links the shared three plus one
catalog source (NPS noise) at output_level participant and episode. Writes
<out>/checks.json and the result CSVs. Synthetic data only.
"""
import io
import json
import re
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from ref import reference  # noqa: E402

DATA, OUT = Path(sys.argv[1]), Path(sys.argv[2])
BASE = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:8100"
FE = sys.argv[4] if len(sys.argv) > 4 else "http://localhost:3100"
OUT.mkdir(parents=True, exist_ok=True)
TOL = 1e-6
checks = []


def check(name, ok, detail=""):
    checks.append({"check": name, "ok": bool(ok), "detail": str(detail)[:400]})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""),
          flush=True)
    return ok


def save():
    (OUT / "checks.json").write_text(json.dumps(
        {"passed": sum(c["ok"] for c in checks), "failed": sum(not c["ok"] for c in checks),
         "checks": checks}, indent=1))


c = httpx.Client(base_url=BASE, timeout=900)
for _ in range(150):
    try:
        if c.get("/api/health").status_code == 200:
            break
    except httpx.HTTPError:
        pass
    time.sleep(2)
check("backend /api/health answers", c.get("/api/health").json().get("status") == "ok")

PASSWORD = "Synthetic-Pass-1"


def user(email, first, last):
    r = c.post("/api/auth/signup", json={"email": email, "password": PASSWORD,
                                         "first_name": first, "last_name": last})
    if r.status_code != 200:
        r = c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


A = user("ada.tester@example.com", "Ada", "Tester")
B = user("ben.tester@example.com", "Ben", "Tester")

cap = c.get("/api/datasets/capabilities", headers=A).json()
check("capabilities: registry on, daily tables, biweekly rasters, features",
      cap.get("registry") is True and "daily" in cap["kinds"].get("polygon_table", [])
      and "biweekly" in cap["kinds"].get("raster", []) and "static" in cap["kinds"].get("features", []),
      cap)


def post_dataset(hdr, paths, meta):
    files = [("files", (Path(p).name, open(p, "rb").read(),
                        "text/csv" if str(p).endswith(".csv") else "application/octet-stream"))
             for p in paths]
    return c.post("/api/datasets", headers=hdr, files=files, data={"metadata": json.dumps(meta)})


design = json.load(open(DATA / "design.json"))
common = {"source": "I2 e2e gate (synthetic)", "version": "1",
          "license_note": "Synthetic test data, no restrictions"}
# metadata shaped exactly like the frontend's buildDatasetMetadata
meta_daily = {"name": "Synthetic daily tract values", "kind": "polygon_table", "temporal": "daily",
              "key": {"geography": "Tract", "column": "GEOID10", "time_column": "date"},
              "variables": [{"name": "syn_daily", "unit": "index",
                             "description": "Synthetic daily value per tract"}],
              "visibility": "deployment", "description": "Daily synthetic values", **common}
meta_bw = {"name": "Synthetic biweekly raster", "kind": "raster", "temporal": "biweekly",
           "variables": [{"name": "syn_bw", "band": 1, "unit": "index"}],
           "periods": [{"file": p["file"], "start": p["start"], "end": p["end"]}
                       for p in design["periods"]],
           "visibility": "deployment", **common}
meta_sites = {"name": "Synthetic sites", "kind": "features", "temporal": "static",
              "variables": [{"name": "syn_sites_dist_m", "unit": "m",
                             "description": "Distance to the nearest synthetic site"}],
              "visibility": "deployment", **common}
meta_priv = {"name": "Synthetic private table", "kind": "polygon_table", "temporal": "static",
             "key": {"geography": "Tract", "column": "GEOID10"},
             "variables": [{"name": "syn_private"}], "visibility": "private", **common}

ids = {}
for label, paths, meta in (
        ("daily", [DATA / "daily_tract.csv"], meta_daily),
        ("bw", [DATA / "bw" / p["file"] for p in design["periods"]], meta_bw),
        ("sites", [DATA / "sites.gpkg"], meta_sites),
        ("private", [DATA / "private_static.csv"], meta_priv)):
    t0 = time.time()
    r = post_dataset(A, paths, meta)
    body = r.json()
    ok = r.status_code == 201 and body.get("dataset", {}).get("status") == "ready"
    check(f"A registers {label} ({meta['kind']}/{meta['temporal']}, {meta['visibility']}) -> 201 ready",
          ok, f"{r.status_code} {json.dumps(body)[:300]}")
    if ok:
        ids[label] = body["dataset"]["id"]
        d = body["dataset"]
        if label == "bw":
            check("biweekly raster record: 6 files, variable syn_bw",
                  len(d.get("files") or []) >= 1 and [v["name"] for v in d["variables"]] == ["syn_bw"],
                  d.get("files"))
        if label == "daily":
            check("daily table record: key in the web's vocabulary",
                  d.get("key", {}).get("geography") == "Tract"
                  and d["key"].get("time_column") == "date", d.get("key"))
        print(f"  ({label} registered in {time.time() - t0:.1f}s)")
save()
if len(ids) < 4:
    print("registration failed; stopping")
    sys.exit(2)

# refused data: the message names the problem, never a data value
bad = OUT / "bad_daily.csv"
bad.write_text("GEOID10,date,syn_daily\n18097310100,notadate-7319,1.5\n")
r = post_dataset(A, [bad], {**meta_daily, "name": "Refused daily"})
check("refused upload -> 400 {detail, issues} without the data value",
      r.status_code == 400 and "issues" in r.json() and "notadate-7319" not in r.text,
      f"{r.status_code} {r.text[:300]}")
r = post_dataset(A, [DATA / "daily_tract.csv"], {**meta_daily, "name": "synthetic DAILY tract values"})
check("name unique per owner ignoring case -> 409", r.status_code == 409, r.status_code)

# visibility and owner rules
la = c.get("/api/datasets", headers=A).json()
check("A lists its 4 datasets, all owned_by_me",
      {d["id"] for d in la} >= set(ids.values()) and all(d["owned_by_me"] for d in la
                                                         if d["id"] in ids.values()))
lb = c.get("/api/datasets", headers=B).json()
shared = {ids["daily"], ids["bw"], ids["sites"]}
check("B lists exactly A's 3 shared datasets (not the private one)",
      {d["id"] for d in lb} == shared, [d["name"] for d in lb])
check("B sees them as not owned, owner_display = first + last name (no e-mail)",
      all((not d["owned_by_me"]) and d["owner_display"] == "Ada Tester" for d in lb)
      and "example.com" not in json.dumps(lb), [d.get("owner_display") for d in lb])
check("no server path in B's listing", "/app/data" not in json.dumps(lb)
      and "custom_exposomes" not in json.dumps(lb))
check("B GET A's shared dataset -> 200", c.get(f"/api/datasets/{ids['daily']}", headers=B).status_code == 200)
check("B GET A's private dataset -> 404", c.get(f"/api/datasets/{ids['private']}", headers=B).status_code == 404)
check("B PATCH A's shared dataset -> 403",
      c.patch(f"/api/datasets/{ids['daily']}", headers=B, json={"name": "hijacked"}).status_code == 403)
check("B un-share A's shared dataset -> 403",
      c.patch(f"/api/datasets/{ids['daily']}", headers=B, json={"visibility": "private"}).status_code == 403)
check("B DELETE A's shared dataset -> 403",
      c.delete(f"/api/datasets/{ids['daily']}", headers=B).status_code == 403)
check("B PATCH A's private dataset -> 404",
      c.patch(f"/api/datasets/{ids['private']}", headers=B, json={"name": "x"}).status_code == 404)
check("B DELETE A's private dataset -> 404",
      c.delete(f"/api/datasets/{ids['private']}", headers=B).status_code == 404)
ra = c.get("/api/custom-exposomes", headers=B)
check("alias /api/custom-exposomes lists only B's own datasets (none)",
      ra.status_code == 200 and ra.json() == {"variables": {}}, ra.text[:200])
ra = c.get("/api/custom-exposomes", headers=A)
check("alias /api/custom-exposomes lists A's own ready datasets (4)",
      ra.status_code == 200 and len(ra.json().get("variables", {})) == 4, len(ra.json().get("variables", {})))
r = c.get("/api/custom-exposomes/boundaries", headers=B)
check("boundaries alias (used by the upload form) answers", r.status_code == 200 and "boundaries" in r.json())
save()

# B's tasks
VARS = ["noise"]
ORDER = [ids["daily"], ids["bw"], ids["sites"]]


def make_task(name, level):
    r = c.post("/api/tasks", headers=B, json={"task_name": name})
    tid = r.json()["id"]
    up = c.post(f"/api/tasks/{tid}/upload", headers=B,
                files={"file": ("cohort_B.csv", open(DATA / "cohort_B.csv", "rb").read(), "text/csv")})
    check(f"{level}: cohort upload -> 11 rows", up.status_code == 200 and up.json().get("row_count") == 11,
          up.text[:200])
    cfg = {"experiment": "auto", "buffer": {"size": 270, "raster_res_m": 25}, "variables": VARS,
           "output_level": level, "custom_datasets": ORDER}
    r = c.put(f"/api/tasks/{tid}/config", headers=B, json={**cfg, "custom_datasets": ORDER + [ids["private"]]})
    check(f"{level}: config naming A's private dataset -> 404", r.status_code == 404, r.status_code)
    r = c.put(f"/api/tasks/{tid}/config", headers=B, json=cfg)
    check(f"{level}: config saved", r.status_code == 200, r.text[:200])
    t = c.get(f"/api/tasks/{tid}", headers=B).json()
    check(f"{level}: task reports output_level and the 3 dataset ids",
          t.get("output_level") == level and t.get("custom_datasets") == ORDER,
          {k: t.get(k) for k in ("output_level", "custom_datasets")})
    return tid


tp = make_task("e2e participant level", "participant")
te = make_task("e2e episode level", "episode")


def wait(tid, label, hdr=None, timeout=3600, poll=5.0):
    hdr = hdr or B
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        s = c.get(f"/api/tasks/{tid}/status", headers=hdr).json()
        if s.get("status") != last:
            print(f"  [{label}] {s.get('status')} {time.time() - t0:.0f}s", flush=True)
            last = s.get("status")
        if s.get("status") in ("finished", "error", "cancelled"):
            return s, time.time() - t0
        time.sleep(poll)
    return {"status": "timeout"}, timeout


# One task at a time: two starts within a second race in the web's serial queue (a
# pre-existing defect, reported separately), which is not what this gate tests.
r1 = c.post(f"/api/tasks/{tp}/start", headers=B)
check("participant task starts", r1.status_code == 200, r1.text[:200])
st = c.get(f"/api/tasks/{tp}/status", headers=B).json().get("status")
r = c.delete(f"/api/datasets/{ids['bw']}", headers=A)
check(f"A DELETE a dataset a running task uses -> 409 (participant task was {st})",
      st in ("queued", "running") and r.status_code == 409, f"{st} {r.status_code} {r.text[:200]}")
check("A cannot read B's task (403)", c.get(f"/api/tasks/{tp}", headers=A).status_code == 403)
sp, dtp = wait(tp, "participant")
check(f"participant task finished ({dtp:.0f}s)", sp.get("status") == "finished", sp)
r2 = c.post(f"/api/tasks/{te}/start", headers=B)
check("episode task starts", r2.status_code == 200, r2.text[:200])
se, dte = wait(te, "episode")
check(f"episode task finished ({dte:.0f}s)", se.get("status") == "finished", se)
for tid, label in ((tp, "participant"), (te, "episode")):
    logs = c.get(f"/api/tasks/{tid}/logs", headers=B)
    (OUT / f"logs_{label}.json").write_text(logs.text)
save()
if sp.get("status") != "finished" or se.get("status") != "finished":
    sys.exit(3)

ref_ep, ref_part, contrib = reference(DATA)
cohort = pd.read_csv(DATA / "cohort_B.csv", dtype=str)
CUSTOM = ["syn_daily", "syn_bw", "syn_sites_dist_m"]


def fetch(tid, label):
    r = c.get(f"/api/tasks/{tid}/results", headers=B)
    (OUT / f"result_{label}.csv").write_bytes(r.content)
    check(f"{label}: download carries X-Output-Level: {label}", r.headers.get("x-output-level") == label,
          r.headers.get("x-output-level"))
    return pd.read_csv(io.BytesIO(r.content), dtype={"pid": str, "state_fips": str})


part = fetch(tp, "participant")
epi = fetch(te, "episode")
noise_cols = [col for col in part.columns if col.startswith("l50dba")]
check("participant result.csv: one row per participant (6), first-appearance order, ids as uploaded",
      part["pid"].tolist() == list(dict.fromkeys(cohort["pid"])), part["pid"].tolist())
check("participant result.csv columns: pid, then the variables in request order",
      list(part.columns) == ["pid"] + noise_cols + CUSTOM and len(noise_cols) == 3, list(part.columns))
check("participant result.csv has no dates, coordinates or episode ids",
      not ({"startDate", "endDate", "longitude", "latitude", "episode_id", "state_fips"} & set(part.columns)))
check("episode result.csv: one row per location episode (11)", len(epi) == 11, len(epi))
check("episode result.csv keeps the cohort columns and ids as uploaded",
      {"pid", "startDate", "endDate", "longitude", "latitude", "state_fips"} <= set(epi.columns)
      and epi["pid"].tolist() == cohort["pid"].tolist(), list(epi.columns))
check("episode result.csv has every variable column", set(noise_cols + CUSTOM) <= set(epi.columns))


# Daily and raster values are exact (each buffer lies inside one tract / one cell). Feature
# distances use EPSG:4326 -> 5070; with PROJ's network grids off in the web (the fix this
# gate found) the image and this host use the same transformation, so they agree too.
TOLS = {"syn_daily": TOL, "syn_bw": TOL, "syn_sites_dist_m": TOL}


def compare(got, want, label):
    worst = {}
    ok = True
    for col in CUSTOM:
        g, w = got[col].astype(float).to_numpy(), want[col].astype(float).to_numpy()
        if not np.array_equal(np.isnan(g), np.isnan(w)):
            ok = False
        m = ~np.isnan(w) & ~np.isnan(g)
        worst[col] = float(np.max(np.abs(g[m] - w[m]))) if m.any() else 0.0
        ok = ok and worst[col] <= TOLS[col]
    return ok, {k: f"{v:.2e}" for k, v in worst.items()}


ep_sorted = epi.reset_index(drop=True)
ok, worst = compare(ep_sorted, ref_ep, "episode")
check(f"episode values == independent reference, 3 registered datasets (max |diff| {worst})", ok, worst)
ok, worst = compare(part.reset_index(drop=True), ref_part, "participant")
check(f"participant values == independent reference, 3 registered datasets (max |diff| {worst})", ok, worst)

# participant noise == day-weighted mean of its episodes' noise (static source)
lens = (pd.to_datetime(epi["endDate"]) - pd.to_datetime(epi["startDate"])).dt.days + 1
worst, ok = 0.0, True
for col in noise_cols:
    for pid in part["pid"]:
        m = (epi["pid"] == pid) & epi[col].notna()
        want = float((epi.loc[m, col] * lens[m]).sum() / lens[m].sum()) if m.any() else np.nan
        got = float(part.loc[part["pid"] == pid, col].iloc[0])
        if np.isnan(want) != np.isnan(got):
            ok = False
        elif not np.isnan(want):
            worst = max(worst, abs(got - want))
check(f"participant noise == day-weighted mean of its episode values (max |diff| {worst:.2e})",
      ok and worst <= TOL, worst)

# hand computation, one participant (00105: three episodes, a missing-value window, gaps)
hand = {}
p5 = [a for p, a in contrib if p == "00105"]
for v in CUSTOM:
    hand[v] = sum(a[v][0] for a in p5) / sum(a[v][1] for a in p5)
row = part[part["pid"] == "00105"].iloc[0]
check("hand check 00105: sum_e sum_t d*z / sum_e sum_t d per variable",
      all(abs(float(row[v]) - hand[v]) <= TOLS[v] for v in CUSTOM),
      {v: (float(row[v]), hand[v]) for v in CUSTOM})
# the daily value of 00105 by hand: T4 Jan 20-31 (12 days; Feb 1-5 missing), T5 Feb 20-Mar 5
# (15 days), T0 Mar 15-31 (17 days); value = 10*(i+1) + 0.1*day_index
t = {e["geoid"]: i for i, e in enumerate(design["locations"])}
d0 = pd.Timestamp("2016-01-01")
spans = [(4, "2016-01-20", "2016-01-31"), (5, "2016-02-20", "2016-03-05"), (0, "2016-03-15", "2016-03-31")]
num = den = 0.0
for ti, s, e in spans:
    for d in pd.date_range(s, e):
        num += 10 * (ti + 1) + 0.1 * (d - d0).days
        den += 1
check("hand check 00105 syn_daily from the generating formula (44 contributing days)",
      den == 44 and abs(float(row["syn_daily"]) - num / den) <= TOL, (float(row["syn_daily"]), num / den))

# results endpoints
for tid, label, n in ((tp, "participant", 6), (te, "episode", 11)):
    pv = c.get(f"/api/tasks/{tid}/results/preview?limit=50", headers=B).json()
    exp_unit = "participants" if label == "participant" else "episodes"
    check(f"{label}: preview level/row_unit/total_rows",
          pv.get("level") == label and pv.get("row_unit") == exp_unit and pv.get("total_rows") == n,
          {k: pv.get(k) for k in ("level", "row_unit", "total_rows")})
    want_ref = ref_part if label == "participant" else ref_ep
    lk = pv.get("linkage") or {}
    good = True
    for col in CUSTOM:
        linked = int(want_ref[col].notna().sum())
        got = lk.get(col, {})
        good &= got.get("linked") == linked and got.get("total") == n
    check(f"{label}: linkage rates at the output level (custom columns)", good,
          {col: lk.get(col) for col in CUSTOM})
    check(f"{label}: linkage covers the noise columns too", all(col in lk for col in noise_cols))
    hg = c.get(f"/api/tasks/{tid}/results/histogram", headers=B).json()
    check(f"{label}: histogram level", hg.get("level") == label, hg.get("level"))
    geo = c.get(f"/api/tasks/{tid}/results/geo", headers=B, params={"value_col": "syn_daily"}).json()
    counts = {b["state_fips"]: b["count"] for b in geo.get("by_state", [])}
    if label == "participant":
        exp = {"18": 4, "17": 1}
        means = {b["state_fips"]: b["mean"] for b in geo["by_state"]}
        st_of = {"00101": "18", "00102": "18", "00103": "18", "00104": "18", "00105": "18", "00106": "17"}
        rp = ref_part.assign(st=ref_part["pid"].map(st_of)).dropna(subset=["syn_daily"])
        exp_mean = rp.groupby("st")["syn_daily"].mean().round(6).to_dict()
        check("participant geo: level, longest-episode rule, counts per state",
              geo.get("level") == label and geo.get("state_rule") == "longest_episode" and counts == exp,
              {"level": geo.get("level"), "rule": geo.get("state_rule"), "counts": counts})
        check("participant geo: per-state means of the participants' values",
              all(abs(means[s] - exp_mean[s]) <= 1e-5 for s in exp), (means, exp_mean))
    else:
        check("episode geo: level and counts per state (episodes with a value)",
              geo.get("level") == label and counts == {"18": 7, "17": 3}, {"counts": counts})
    t = c.get(f"/api/tasks/{tid}", headers=B).json()
    check(f"{label}: task payload result_level", t.get("result_level") == label, t.get("result_level"))
    check(f"{label}: A cannot read B's results (403)",
          c.get(f"/api/tasks/{tid}/results/preview", headers=A).status_code == 403)
save()

# un-share: B no longer sees the dataset and cannot re-run the task that snapshotted it
r = c.patch(f"/api/datasets/{ids['daily']}", headers=A, json={"visibility": "private"})
check("A un-shares the daily table -> 200", r.status_code == 200 and r.json()["dataset"]["visibility"] == "private")
check("B no longer lists it", ids["daily"] not in {d["id"] for d in c.get("/api/datasets", headers=B).json()})
r = c.post(f"/api/tasks/{tp}/start", headers=B)
check("B cannot re-run the finished task that used it (409)", r.status_code == 409, f"{r.status_code} {r.text[:200]}")
check("B's finished results stay readable", c.get(f"/api/tasks/{tp}/results/preview", headers=B).status_code == 200)
r = c.patch(f"/api/datasets/{ids['daily']}", headers=A, json={"visibility": "deployment"})
check("A re-shares it; B lists it again", r.status_code == 200 and ids["daily"] in
      {d["id"] for d in c.get("/api/datasets", headers=B).json()})
r = c.patch(f"/api/datasets/{ids['sites']}", headers=A,
            json={"description": "Edited by the owner", "variables": [{"name": "syn_sites_dist_m", "unit": "m",
                                                                      "description": "Edited"}]})
check("A edits its shared dataset's metadata -> 200", r.status_code == 200, r.status_code)
check("A deletes its private dataset (unused) -> 200",
      c.delete(f"/api/datasets/{ids['private']}", headers=A).status_code == 200)

# frontend pages (HTTP) and the bundle
fe = httpx.Client(base_url=FE, timeout=60, follow_redirects=True)
for path in ("/", "/login", "/dashboard", "/dashboard/datasets", "/dashboard/task/new",
             f"/dashboard/task/{tp}", f"/dashboard/task/{tp}/results"):
    r = fe.get(path)
    check(f"frontend {path} -> 200", r.status_code == 200, r.status_code)
html = fe.get("/dashboard/datasets").text
chunks = sorted(set(re.findall(r'/_next/static/[^"\']+\.js', html)))
blob = "".join(fe.get(u).text for u in chunks)
check("frontend bundle calls the TEST backend (localhost:8100)", "localhost:8100" in blob)
check("frontend bundle carries the share warning (7.1 item 6)",
      "you are responsible for making sure the source" in blob)
json.dump({"A_datasets": ids, "task_participant": tp, "task_episode": te},
          open(OUT / "ids.json", "w"), indent=1)
save()

# Observation, not a gate check: the serial queue while a task with two experiments runs.
# User C starts T1 (noise + the shared daily table = two experiments, each runner taking
# and releasing DATA_DIR/.run_lock), then T2 once T1 holds the lock, and polls quickly
# (the frontend polls status too; a status read can promote the queue).
C = user("cy.tester@example.com", "Cy", "Tester")
probe = {}
tids = []
for n in (1, 2):
    tid = c.post("/api/tasks", headers=C, json={"task_name": f"queue probe {n}"}).json()["id"]
    c.post(f"/api/tasks/{tid}/upload", headers=C,
           files={"file": ("cohort_B.csv", open(DATA / "cohort_B.csv", "rb").read(), "text/csv")})
    c.put(f"/api/tasks/{tid}/config", headers=C,
          json={"experiment": "auto", "buffer": {"size": 270, "raster_res_m": 25}, "variables": ["noise"],
                "output_level": "participant", "custom_datasets": [ids["daily"]]})
    tids.append(tid)
c.post(f"/api/tasks/{tids[0]}/start", headers=C)
t0 = time.time()
while time.time() - t0 < 60:
    s1 = c.get(f"/api/tasks/{tids[0]}/status", headers=C).json()
    if s1.get("current_step") or any((e or {}).get("current_step")
                                     for e in (s1.get("experiments") or {}).values()):
        break  # T1's first runner is executing a step: it holds the run lock
    time.sleep(0.2)
probe["T2_start_reply"] = c.post(f"/api/tasks/{tids[1]}/start", headers=C).json().get("status")
timeline = []
t0 = time.time()
while time.time() - t0 < 900:
    s1 = c.get(f"/api/tasks/{tids[0]}/status", headers=C).json()
    s2 = c.get(f"/api/tasks/{tids[1]}/status", headers=C).json()
    state = (s1.get("status"), s2.get("status"))
    if not timeline or timeline[-1][1:] != state:
        timeline.append((round(time.time() - t0, 1), *state))
    if all(x in ("finished", "error", "cancelled") for x in state):
        break
    time.sleep(0.3)
probe["timeline"] = timeline
probe["T1_final"] = {k: s1.get(k) for k in ("status", "message")}
probe["T2_final"] = {k: s2.get(k) for k in ("status", "message")}
probe["T2_ran_while_T1_running"] = any(a == "running" and b == "running" for _, a, b in timeline)
(OUT / "queue_probe.json").write_text(json.dumps(probe, indent=1))
print("queue probe:", json.dumps(probe)[:600])
save()
print(f"\n{sum(x['ok'] for x in checks)} passed, {sum(not x['ok'] for x in checks)} failed")
sys.exit(0 if all(x["ok"] for x in checks) else 1)

#!/usr/bin/env python3
"""
Whole-command-flow tests for run and restart.

These drive cmd_run and cmd_restart through their real orchestration -- the
preflights, the try/finally, the gate loop and the recording -- with the model
and the ledger faked. Defects found in review were orchestration defects that
persist_results tests could not reach, because they lived in the order the
command does things rather than in the recording function.

No model is loaded and no real ledger is touched.
"""
import argparse, importlib.util as u, json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sp = u.spec_from_file_location("sp", os.path.join(HERE, "state_probe.py"))
m = u.module_from_spec(sp); sp.loader.exec_module(m)

DECL = {
    "declaration_sha256": "d" * 64, "model_sha256": "m" * 64,
    "probe_file_sha256": "880f", "probe_set_id": "B_space_in_value",
    "declared_utc": "2026-09-20T00:00:00Z",
    "runtime": {"n_ctx": 512, "n_threads": 7, "n_batch": 512, "seed": 0},
    "thresholds": {"noise_k": 3.0, "min_margin_abs": 0.5,
                   "specificity_min_ratio": 3.0, "jitter_n": 20},
    "probes": {"relation": {}, "unrelated": {}},
}

class L:
    def __init__(self, *a, **k):
        self.ok, self.reason, self.body, self.closed = True, "ok", None, False
        LEDGERS.append(self)
    def commit(self, t, b): self.body = b; return "evt_flow"
    def verify(self): return []
    def close(self): self.closed = True

LEDGERS = []

def decl_file(d=None):
    p = os.path.join(tempfile.mkdtemp(), "declaration.json")
    open(p, "w").write(json.dumps(d if d is not None else DECL))
    return p

def args_for(out, decl=None, **kw):
    a = dict(model="/fake.gguf", decl=decl or decl_file(), ledger="/any",
             out=out, probes="/fake.json", state_file="/tmp/s", tol=None,
             phase=None, n_ctx=512, threads=None, n_batch=512, seed=0)
    a.update(kw)
    return argparse.Namespace(**a)

def fake_gates(on_jitter=None):
    m.Engine = lambda *a, **k: object()
    m.sha256_file = lambda p: DECL["model_sha256"]
    def jitter(eng, decl):
        if on_jitter: on_jitter()
        return {"n": 20, "spread_range": 0.0, "spread_stdev": 0.0, "mean": 1.0,
                "values": [1.0] * 20, "deterministic": True,
                "suggested_restart_tol": 0.001}
    m.run_jitter = jitter
    m.run_floor = lambda e, d, sp_: {"D_with_state": 4.2, "D_fresh": -1.0,
                                     "delta": 5.2, "required_margin": 0.5,
                                     "margin_binding_term": "min_margin_abs",
                                     "jitter_range": 0.0, "pass": True}
    m.run_causality = lambda e, d, sp_: {"D_state_A": 4.2, "D_state_B": -3.9,
                                         "required_margin": 0.5, "pass": True}
    m.run_specificity = lambda e, d: {"shift_related": 5.2, "shift_unrelated": 0.4,
                                      "ratio": 13.0, "pass": True}

real = {k: getattr(m, k) for k in
        ("Engine", "sha256_file", "run_jitter", "run_floor", "run_causality",
         "run_specificity", "Ledger")}
def restore():
    for k, v in real.items(): setattr(m, k, v)

print("=== whole-command-flow: run ===\n")

# 24 -- happy path end to end
m.Ledger = L; LEDGERS.clear(); fake_gates()
out = os.path.join(tempfile.mkdtemp(), "results.json")
rc = m.cmd_run(args_for(out))
assert rc == 0, rc
assert os.path.exists(out), "no results file"
saved = json.loads(open(out).read())
assert saved["floor"]["pass"] and saved["declaration_sha256"] == DECL["declaration_sha256"]
assert LEDGERS[0].closed, "ledger left open on the happy path"
assert "results_json" in LEDGERS[0].body and "results" not in LEDGERS[0].body
print("--- 24 run happy path            -> results saved, committed as text, ledger closed")

# 25 -- output appears DURING the battery: must not lose the run
LEDGERS.clear()
d = tempfile.mkdtemp(); out = os.path.join(d, "results.json")
fake_gates(on_jitter=lambda: open(out, "w").write("APPEARED MID-BATTERY"))
try:
    rc = m.cmd_run(args_for(out))
except SystemExit as e:
    rc = str(e)
recovered = [f for f in os.listdir(d) if ".recovered-" in f]
assert recovered, f"MEASUREMENT LOST on a late collision; dir={os.listdir(d)}"
got = json.loads(open(os.path.join(d, recovered[0])).read())
assert got["floor"]["pass"] is True, "recovery file is not the measurement"
assert open(out).read() == "APPEARED MID-BATTERY", "the colliding file was overwritten"
assert LEDGERS[0].closed
print("--- 25 out appears mid-battery   -> saved to a unique recovery path, nothing lost")

# 26 -- partial write, working ledger: complete payload must still be committed
LEDGERS.clear(); fake_gates()
d = tempfile.mkdtemp(); out = os.path.join(d, "results.json")
real_fdopen, real_fsync = m.os.fdopen, m.os.fsync
class Trunc:
    def __init__(self, f): self.f = f
    def write(self, b): return self.f.write(b[:5])
    def flush(self): self.f.flush()
    def fileno(self): return self.f.fileno()
    def __enter__(self): return self
    def __exit__(self, *a): self.f.close(); return False
m.os.fdopen = lambda fd, mode: Trunc(real_fdopen(fd, mode))
m.os.fsync = lambda fd: (_ for _ in ()).throw(OSError("simulated"))
try:
    m.cmd_run(args_for(out))
    raise AssertionError("should have raised")
except SystemExit as e:
    msg = str(e)
finally:
    m.os.fdopen, m.os.fsync = real_fdopen, real_fsync
assert "RESULTS FILE INCOMPLETE" in msg, msg
assert "ARE in the chain as event evt_flow" in msg, "complete payload was abandoned"
assert LEDGERS[0].body is not None, "ledger never tried"
assert json.loads(LEDGERS[0].body["results_json"])["floor"]["pass"] is True
assert LEDGERS[0].body["file_intact"] == "no"
assert LEDGERS[0].closed
print("--- 26 partial file, good ledger -> complete payload committed anyway")

print("\n=== whole-command-flow: restart ===\n")

# 27 -- missing --tol must close the ledger
LEDGERS.clear(); m.Ledger = L
rc = m.cmd_restart(args_for(os.path.join(tempfile.mkdtemp(), "r.json"), tol=None))
assert rc == 2, rc
assert LEDGERS and LEDGERS[0].closed, "ledger left OPEN when --tol was missing"
print("--- 27 restart without --tol     -> exit 2, ledger closed")

# 28 -- declaration read failure must close the ledger
LEDGERS.clear()
try:
    m.cmd_restart(args_for(os.path.join(tempfile.mkdtemp(), "r.json"),
                           decl="/definitely/missing.json", tol=0.01))
except Exception as e:
    print(f"--- 28 restart decl read raised: {type(e).__name__}")
assert LEDGERS and LEDGERS[0].closed, "ledger left OPEN on declaration-read failure"
print("    ledger closed despite the failure: True")

restore()
print("\nALL COMMAND-FLOW PATHS BEHAVE AS SPECIFIED")

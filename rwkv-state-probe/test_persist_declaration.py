#!/usr/bin/env python3
"""Failure-path tests for persist_declaration and cmd_declare's refusals.
No model is loaded; the ledger is faked. Run before any declaration attempt."""
import importlib.util as u, json, os, tempfile, sys, argparse
sp = u.spec_from_file_location('sp', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state_probe.py')); m = u.module_from_spec(sp); sp.loader.exec_module(m)

# Thresholds are FLOATS on purpose: canon/1 rejects them, which is what forced
# the declaration to be committed as serialized text rather than as a dict.
DECL = {"declaration_sha256":"d"*64, "model_sha256":"m"*64,
        "probe_file_sha256":"880f", "probe_set_id":"B_space_in_value",
        "declared_utc":"2026-09-20T00:00:00Z", "probes":{"x":1},
        "thresholds":{"noise_k":3.0,"min_margin_abs":0.5,
                      "specificity_min_ratio":3.0,"jitter_n":20}}

class FakeLedger:
    def __init__(self, mode="ok"): self.mode, self.ok, self.reason, self.body = mode, True, "ok", None
    def commit(self, t, body):
        if self.mode == "raise": raise RuntimeError("chain write failed")
        if self.mode == "none":  return None
        self.body = body; return "evt_abc123"
    def close(self): pass

def run(name, fn):
    d = tempfile.mkdtemp(); path = os.path.join(d, "declaration.json")
    try:
        res = fn(path); err = None
    except SystemExit as e:
        res, err = None, str(e)
    final = os.path.exists(path); pending = os.path.exists(path + ".pending")
    print(f"--- {name}")
    print(f"    final file : {final}")
    print(f"    .pending   : {pending}")
    if err: print(f"    refused    : {err.splitlines()[0][:95]}")
    else:   print(f"    returned   : {res}")
    return final, pending, err

print("=== persist_declaration failure paths ===\n")
led_ok = FakeLedger("ok")
f, p, e = run("1 happy path", lambda path: m.persist_declaration(DECL, path, led_ok))
assert f and not p and e is None, "happy path broken"
import hashlib as _h
body = led_ok.body
assert "declaration" not in body, "dict body would be rejected by canon/1"
assert isinstance(body["declaration_json"], str), "declaration must be committed as TEXT"
assert json.loads(body["declaration_json"]) == DECL, "text must round-trip to the declaration"
assert body["declaration_json_sha256"] == _h.sha256(body["declaration_json"].encode()).hexdigest()

def has_float(o):
    if isinstance(o, float): return True
    if isinstance(o, dict):  return any(has_float(v) for v in o.values())
    if isinstance(o, list):  return any(has_float(v) for v in o)
    return False
assert not has_float(body), "event body contains a float; canon/1 will reject it"
assert has_float(DECL), "fixture must contain floats for this test to mean anything"
print("    committed as TEXT, round-trips, no float anywhere in event body: True")
print("    thresholds inside the declaration unchanged:", DECL["thresholds"], "\n")

f, p, e = run("2 commit raises", lambda path: m.persist_declaration(DECL, path, FakeLedger("raise")))
assert not f and not p and e, "commit-raise must leave NO file and refuse"
print()

f, p, e = run("3 commit returns None", lambda path: m.persist_declaration(DECL, path, FakeLedger("none")))
assert not f and not p and e, "commit-None must leave NO file and refuse"
print()

def boom(a, b): raise OSError("read-only filesystem")
led2 = FakeLedger("ok")
f, p, e = run("4 publish fails AFTER commit", lambda path: m.persist_declaration(DECL, path, led2, _link=boom))
assert not f and p and e, "publish failure must PRESERVE .pending for recovery"
assert "COMMITTED BUT NOT PUBLISHED" in e and "mv" in e and "Do NOT re-run" in e, "recovery instructions missing"
assert led2.body is not None, "commit should have happened"
print("    chain committed, .pending preserved, recovery instructions printed\n")

print("=== clobber refusals ===\n")

def preexisting_decl(path):
    open(path, "w").write("EXISTING COMMITMENT - MUST NOT BE DESTROYED")
    return m.persist_declaration(DECL, path, FakeLedger("ok"))
d = tempfile.mkdtemp(); path = os.path.join(d, "declaration.json")
open(path, "w").write("EXISTING COMMITMENT - MUST NOT BE DESTROYED")
try:
    m.persist_declaration(DECL, path, FakeLedger("ok")); raise AssertionError("overwrote a declaration")
except SystemExit as e:
    assert "already exists" in str(e)
assert open(path).read() == "EXISTING COMMITMENT - MUST NOT BE DESTROYED", "existing declaration was modified"
print("--- 7 existing declaration.json  -> refused, file untouched")

d = tempfile.mkdtemp(); path = os.path.join(d, "declaration.json")
open(path + ".pending", "w").write("UNRECOVERED PENDING - MUST NOT BE DESTROYED")
try:
    m.persist_declaration(DECL, path, FakeLedger("ok")); raise AssertionError("overwrote a pending file")
except SystemExit as e:
    assert "already exists" in str(e)
assert open(path + ".pending").read() == "UNRECOVERED PENDING - MUST NOT BE DESTROYED", "pending was modified"
print("--- 8 existing .pending          -> refused, file untouched")

d = tempfile.mkdtemp(); path = os.path.join(d, "declaration.json")
def racing_link(src, dst):
    open(dst, "w").write("APPEARED DURING THE RUN")
    return os.link(src, dst)
try:
    m.persist_declaration(DECL, path, FakeLedger("ok"), _link=racing_link)
    raise AssertionError("link overwrote a destination that appeared mid-run")
except SystemExit as e:
    assert "COMMITTED BUT NOT PUBLISHED" in str(e)
assert open(path).read() == "APPEARED DURING THE RUN", "destination was overwritten"
assert os.path.exists(path + ".pending"), "pending must survive for recovery"
print("--- 9 destination appears mid-run -> link refuses, pending preserved\n")

print("=== recovery defects ===\n")

# 11 -- a pre-commit fsync failure must leave NO .pending, because a leftover
# one is indistinguishable from a committed one and would be read as proof.
d = tempfile.mkdtemp(); path = os.path.join(d, "declaration.json")
led_unused = FakeLedger("ok")
real_fsync = m.os.fsync
m.os.fsync = lambda fd: (_ for _ in ()).throw(OSError("simulated fsync failure"))
try:
    m.persist_declaration(DECL, path, led_unused); raise AssertionError("should have refused")
except SystemExit as e:
    assert "Nothing was committed." in str(e) and "No file remains." in str(e), str(e)
finally:
    m.os.fsync = real_fsync
assert not os.path.exists(path + ".pending"), "pre-commit .pending must NOT survive"
assert not os.path.exists(path)
assert led_unused.body is None, "nothing should have been committed"
print("--- 11 fsync fails before commit  -> no .pending, nothing committed")

# 12 -- an existing .pending must NOT be described as committed
d = tempfile.mkdtemp(); path = os.path.join(d, "declaration.json")
open(path + ".pending", "wb").write(b"UNVERIFIED")
expect_sha = _h.sha256(b"UNVERIFIED").hexdigest()
try:
    m.persist_declaration(DECL, path, FakeLedger("ok")); raise AssertionError("should have refused")
except SystemExit as e:
    msg = str(e)
assert "COMMITMENT STATUS IS UNKNOWN" in msg, "must not assume commitment"
assert "already in the chain" not in msg, "must not assert commitment"
assert expect_sha in msg, "must print the pending file's hash so it can be matched"
assert "ln " in msg and "Verify first" in msg, "must require verification before publishing"
print("--- 12 existing .pending          -> commitment reported UNKNOWN, hash given")

# 13 -- recovery instruction must not be a plain mv
d = tempfile.mkdtemp(); path = os.path.join(d, "declaration.json")
try:
    m.persist_declaration(DECL, path, FakeLedger("ok"), _link=boom); raise AssertionError("should have refused")
except SystemExit as e:
    msg = str(e)
assert "ln " in msg and "Do not use `mv`" in msg, "recovery must use a non-overwriting command"
assert os.path.exists(path + ".pending")
print("--- 13 publish fails, dest free   -> recovery uses ln, warns against mv")

# 14 -- publish fails because the destination exists: never instruct moving over it
d = tempfile.mkdtemp(); path = os.path.join(d, "declaration.json")
def link_dest_exists(src, dst):
    open(dst, "w").write("A DIFFERENT COMMITTED DECLARATION")
    return os.link(src, dst)
try:
    m.persist_declaration(DECL, path, FakeLedger("ok"), _link=link_dest_exists)
    raise AssertionError("should have refused")
except SystemExit as e:
    msg = str(e)
assert "THE DESTINATION ALREADY EXISTS" in msg and "Do NOT move over it" in msg
assert "ln " not in msg.split("THE DESTINATION")[1], "must not hand out a publish command here"
assert open(path).read() == "A DIFFERENT COMMITTED DECLARATION", "destination was modified"
print("--- 14 publish fails, dest exists -> refuses to instruct any overwrite\n")

# 15 -- when cleanup itself fails, say so; never claim "no file remains"
d = tempfile.mkdtemp(); path = os.path.join(d, "declaration.json")
real_fsync, real_remove = m.os.fsync, m.os.remove
m.os.fsync = lambda fd: (_ for _ in ()).throw(OSError("simulated fsync failure"))
m.os.remove = lambda p_: (_ for _ in ()).throw(OSError("simulated cleanup failure"))
try:
    m.persist_declaration(DECL, path, FakeLedger("ok")); raise AssertionError("should have refused")
except SystemExit as e:
    msg = str(e)
finally:
    m.os.fsync, m.os.remove = real_fsync, real_remove
assert "no file remains" not in msg.lower(), "must not claim the file is gone when it is not"
assert "REMAINS on disk" in msg and "cleanup also failed" in msg, msg
assert "NOT a commitment" in msg
assert os.path.exists(path + ".pending"), "fixture check: the file really did survive"
print("--- 15 cleanup fails too          -> reports the file REMAINS, not 'no file remains'")
os.remove(path + ".pending")

# 15b -- when cleanup succeeds, the honest claim is still made
d = tempfile.mkdtemp(); path = os.path.join(d, "declaration.json")
m.os.fsync = lambda fd: (_ for _ in ()).throw(OSError("simulated fsync failure"))
try:
    m.persist_declaration(DECL, path, FakeLedger("ok")); raise AssertionError("should have refused")
except SystemExit as e:
    msg = str(e)
finally:
    m.os.fsync = real_fsync
assert "No file remains." in msg and "REMAINS on disk" not in msg
assert not os.path.exists(path + ".pending")
print("--- 15b cleanup succeeds          -> 'No file remains.' and it genuinely does not\n")

print("=== cmd_declare refusal paths (no model loaded) ===\n")
def cd(ledger):
    a = argparse.Namespace(model="/nonexistent.gguf", decl="/tmp/should_not_exist.json",
                           ledger=ledger, probes="/tmp/pb.json",
                           n_ctx=512, threads=None, n_batch=512, seed=0)
    return m.cmd_declare(a)
rc = cd(None);            print(f"--- 5 --ledger omitted      -> exit {rc}"); assert rc == 3
rc = cd("/nonexistent");  print(f"--- 6 ledger path invalid   -> exit {rc}"); assert rc == 3
assert not os.path.exists("/tmp/should_not_exist.json"), "refusal must write nothing"
print("    neither refusal wrote a declaration, and neither loaded the model\n")

print("=== ledger is closed even when the model fails ===\n")
class TrackingLedger(FakeLedger):
    def __init__(self): super().__init__("ok"); self.closed = False
    def close(self): self.closed = True
tracked = []
def fake_ledger_ctor(path):
    l = TrackingLedger(); tracked.append(l); return l
real_ledger = m.Ledger
m.Ledger = fake_ledger_ctor
try:
    a = argparse.Namespace(model="/nonexistent.gguf", decl="/tmp/nope.json",
                           ledger="/any", probes="/tmp/pb.json",
                           n_ctx=512, threads=None, n_batch=512, seed=0)
    try:
        m.cmd_declare(a)
    except Exception as e:
        print(f"--- 10 Engine construction raised: {type(e).__name__}")
    assert tracked and tracked[0].closed, "ledger left OPEN when model loading failed"
    print("    ledger closed despite the failure: True")
finally:
    m.Ledger = real_ledger
print()
print("=== persist_results: measurements must never be lost ===\n")

# Realistic battery output: every D, spread and margin is a float.
RES = {"jitter": {"spread_range": 0.0, "spread_stdev": 0.0, "n": 20},
       "floor": {"D_with_state": 4.21, "D_fresh": -1.03, "delta": 5.24,
                 "required_margin": 0.5, "pass": True},
       "gate_failed": None}

# 16 -- floats commit as TEXT and the file is published
d = tempfile.mkdtemp(); out = os.path.join(d, "results.json")
led = FakeLedger("ok")
ev, sha, published = m.persist_results(RES, out, led, "observation", "state_probe_battery")
body = led.body
assert "results" not in body and isinstance(body["results_json"], str)
assert json.loads(body["results_json"]) == RES
assert not has_float(body), "event body contains a float; canon/1 would reject it"
assert has_float(RES), "fixture must contain floats for this to mean anything"
assert published == out and os.path.exists(out) and not os.path.exists(out + ".pending")
print("--- 16 float results              -> committed as TEXT, published, no float in event")

# 17 -- commit rejected: results MUST survive, loudly uncommitted
d = tempfile.mkdtemp(); out = os.path.join(d, "results.json")
try:
    m.persist_results(RES, out, FakeLedger("raise"), "observation", "k")
    raise AssertionError("should have refused")
except SystemExit as e:
    msg = str(e)
assert "RESULTS NOT COMMITTED" in msg and "are NOT lost" in msg, msg
assert "Do not re-run the battery" in msg
assert os.path.exists(out), "MEASUREMENTS WERE LOST - this is the bug being fixed"
assert json.loads(open(out).read()) == RES, "published results must be the real ones"
print("--- 17 ledger rejects results     -> results PUBLISHED anyway, loudly uncommitted")

# 18 -- an existing output must be neither overwritten NOR a cause of data loss.
# This previously asserted a refusal. That was wrong: by the time persist_results
# runs the measurement exists, and refusing destroys it. Refusing early is
# cmd_run's job (test 22); here the correct behaviour is to divert.
d = tempfile.mkdtemp(); out = os.path.join(d, "results.json")
open(out, "w").write("AN EARLIER MEASUREMENT")
ev, sha, published = m.persist_results(RES, out, FakeLedger("ok"), "observation", "k")
assert open(out).read() == "AN EARLIER MEASUREMENT", "an earlier measurement was destroyed"
assert published != out and os.path.exists(published), "new measurement was lost"
assert json.loads(open(published).read()) == RES
print("--- 18 existing results.json      -> diverted, both measurements intact")

# 19 -- run/restart refuse before spending a measurement
m.Ledger = fake_ledger_ctor
try:
    a = argparse.Namespace(decl="/tmp/nope.json", ledger=None, out="/tmp/nope_out.json",
                           model="/nonexistent.gguf", probes="/tmp/pb.json",
                           state_file="/tmp/s", tol=None, phase=None)
    assert m.cmd_run(a) == 3
    assert m.cmd_restart(a) == 3
finally:
    m.Ledger = real_ledger
assert not os.path.exists("/tmp/nope_out.json")
print("--- 19 run/restart without ledger -> exit 3 before any model load\n")

print("=== results: write failure must not destroy the measurement ===\n")

# 20 -- fsync fails but bytes are intact: KEEP the data and carry on
d = tempfile.mkdtemp(); out = os.path.join(d, "results.json")
led = FakeLedger("ok")
m.os.fsync = lambda fd: (_ for _ in ()).throw(OSError("simulated fsync failure"))
try:
    ev, sha, published = m.persist_results(RES, out, led, "observation", "k")
finally:
    m.os.fsync = real_fsync
assert os.path.exists(published), "MEASUREMENT DESTROYED by an fsync failure"
assert json.loads(open(published).read()) == RES
assert led.body is not None, "should still have committed"
print("--- 20 fsync fails, bytes intact  -> results KEPT, committed, published")

# 21 -- write produces wrong bytes: keep for inspection, refuse to call it the run
d = tempfile.mkdtemp(); out = os.path.join(d, "results.json")
real_fdopen = m.os.fdopen
class TruncatingFile:
    def __init__(self, f): self.f = f
    def write(self, b): return self.f.write(b[:5])
    def flush(self): self.f.flush()
    def fileno(self): return self.f.fileno()
    def __enter__(self): return self
    def __exit__(self, *a): self.f.close(); return False
m.os.fdopen = lambda fd, mode: TruncatingFile(real_fdopen(fd, mode))
m.os.fsync = lambda fd: (_ for _ in ()).throw(OSError("simulated fsync failure"))
try:
    m.persist_results(RES, out, FakeLedger("ok"), "observation", "k")
    raise AssertionError("should have refused")
except SystemExit as e:
    msg = str(e)
finally:
    m.os.fdopen, m.os.fsync = real_fdopen, real_fsync
assert "RESULTS FILE INCOMPLETE" in msg and "KEPT for inspection" in msg, msg
# The corrected contract: the partial file is kept AND the complete in-memory
# payload is still committed, so the message must point at the chain.
assert "ARE in the chain as event" in msg, "complete payload was abandoned: " + msg
assert os.path.exists(out + ".pending"), "corrupt file must be kept for forensics"
print("--- 21 write corrupts the bytes   -> kept for inspection, complete payload committed")

# 22 -- an existing output file is refused BEFORE any measurement
d = tempfile.mkdtemp(); out = os.path.join(d, "results.json")
open(out, "w").write("AN EARLIER MEASUREMENT")
m.Ledger = fake_ledger_ctor
try:
    a = argparse.Namespace(decl="/tmp/nope.json", ledger="/any", out=out,
                           model="/nonexistent.gguf", probes="/tmp/pb.json",
                           state_file="/tmp/s", tol=None, phase=None)
    rc = m.cmd_run(a)
finally:
    m.Ledger = real_ledger
assert rc == 3, f"expected refusal before measuring, got {rc}"
assert open(out).read() == "AN EARLIER MEASUREMENT"
print("--- 22 existing --out             -> refused BEFORE the model loads")

# 23 -- ledger closed when the battery raises early
m.Ledger = fake_ledger_ctor
tracked.clear()
try:
    a = argparse.Namespace(decl="/tmp/definitely_missing.json", ledger="/any",
                           out=os.path.join(tempfile.mkdtemp(), "r.json"),
                           model="/nonexistent.gguf", probes="/tmp/pb.json",
                           state_file="/tmp/s", tol=None, phase=None)
    try:
        m.cmd_run(a)
    except Exception as e:
        print(f"--- 23 declaration read raised: {type(e).__name__}")
finally:
    m.Ledger = real_ledger
assert tracked and tracked[0].closed, "ledger left OPEN when run failed early"
print("    ledger closed despite the early failure: True\n")

print("ALL FAILURE PATHS BEHAVE AS SPECIFIED")

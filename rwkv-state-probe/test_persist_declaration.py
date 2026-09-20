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
print("ALL FAILURE PATHS BEHAVE AS SPECIFIED")

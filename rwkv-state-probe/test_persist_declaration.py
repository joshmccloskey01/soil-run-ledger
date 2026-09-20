#!/usr/bin/env python3
"""Failure-path tests for persist_declaration and cmd_declare's refusals.
No model is loaded; the ledger is faked. Run before any declaration attempt."""
import importlib.util as u, json, os, tempfile, sys, argparse
sp = u.spec_from_file_location('sp', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state_probe.py')); m = u.module_from_spec(sp); sp.loader.exec_module(m)

DECL = {"declaration_sha256":"d"*64, "model_sha256":"m"*64,
        "probe_file_sha256":"880f", "probe_set_id":"B_space_in_value",
        "declared_utc":"2026-09-20T00:00:00Z", "probes":{"x":1}}

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
assert led_ok.body["declaration"] == DECL, "full declaration body NOT committed to chain"
print("    full declaration body present in chain event: True\n")

f, p, e = run("2 commit raises", lambda path: m.persist_declaration(DECL, path, FakeLedger("raise")))
assert not f and not p and e, "commit-raise must leave NO file and refuse"
print()

f, p, e = run("3 commit returns None", lambda path: m.persist_declaration(DECL, path, FakeLedger("none")))
assert not f and not p and e, "commit-None must leave NO file and refuse"
print()

def boom(a, b): raise OSError("read-only filesystem")
led2 = FakeLedger("ok")
f, p, e = run("4 rename fails AFTER commit", lambda path: m.persist_declaration(DECL, path, led2, _rename=boom))
assert not f and p and e, "rename failure must PRESERVE .pending for recovery"
assert "COMMITTED BUT NOT PUBLISHED" in e and "mv" in e and "Do NOT re-run" in e, "recovery instructions missing"
assert led2.body is not None, "commit should have happened"
print("    chain committed, .pending preserved, recovery instructions printed\n")

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
print("ALL FAILURE PATHS BEHAVE AS SPECIFIED")

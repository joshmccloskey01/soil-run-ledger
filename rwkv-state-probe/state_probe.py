#!/usr/bin/env python3
"""
state-retention apparatus test  --  RWKV recurrent state

This does NOT test the continuity thesis. Passing it establishes exactly one thing:

    A live internal state can be saved, survive process death, and causally
    affect later computation without replay.

That earns the apparatus. Nothing more.

DISCRIMINATOR (fixed before any run, never chosen after seeing output):

    D = log P(correct_token | C) - log P(wrong_token | C)

  Computed as the raw logit difference at the final position. This is exact,
  not an approximation: log-softmax differences equal logit differences
  because the log-sum-exp denominator is identical for both candidates and
  cancels. No temperature, no sampling, no prose judged anywhere.

BATTERY, in order. Each gate must pass before the next is meaningful.

    jitter       runtime noise floor        (calibration; sets restart tolerance)
    floor        detection floor            (probe can see a known injected relation)
    causality    same C, different state    (D flips sign with the state)
    specificity  same state, different C    (state moves its own query, not everything)
    restart      live vs saved/restored     (survives process death within tolerance)

PRECOMMITMENT. `declare` writes the probe set, candidate token ids, and
thresholds into the ledger BEFORE step 1 runs. Tests refuse to run without a
matching declaration hash. Changing a probe after seeing a result requires a
NEW declaration, applies forward only, and leaves the old one in the chain.
"""

import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------- constants

DECL_VERSION = "state-probe-decl-v1"


def _utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def canon_hash(obj):
    """Stable hash of a declaration. Sorted keys, no whitespace drift."""
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------- ledger

class Ledger:
    """
    Thin binding to ledger core. The ledger is the RECORD and the REFEREE.
    It is never the thing that recreates the model -- that would make the
    instrument part of the build.

    Optional: if --ledger is not given, results still print but are not
    committed, and every result is stamped uncommitted=True.
    """

    def __init__(self, core_dir=None, db_path=None):
        self.ok = False
        self.reason = "not requested"
        if not core_dir:
            return
        code = Path(core_dir) / "code"
        if not code.is_dir():
            self.reason = f"no code/ dir under {core_dir}"
            return
        sys.path.insert(0, str(code))
        try:
            from genesis import create_ledger, verify_chain  # noqa
            from storage import open_authoritative
            from append import append, read_head
        except Exception as e:  # pragma: no cover
            self.reason = f"import failed: {e}"
            return

        self._append = append
        self._read_head = read_head
        self._verify = verify_chain
        self.db = db_path or str(Path(core_dir) / "state_probe.db")

        if not os.path.exists(self.db):
            try:
                create_ledger(
                    self.db,
                    contract_path=str(Path(core_dir) / "docs" / "Irreversible_Ledger_Contract_v0.1.md"),
                    canon_module_path=str(code / "canon1.py"),
                    protocol_module_path=str(code / "canon1_protocol.py"),
                    vector_package_path=str(Path(core_dir) / "vectors" / "jcs_vectors_v1.json"),
                    vector_manifest_path=str(Path(core_dir) / "vectors" / "PACKAGE.sha256"),
                )
            except Exception as e:
                self.reason = f"create_ledger failed: {e}"
                return
        try:
            self.vc = open_authoritative(self.db)
        except Exception as e:
            self.reason = f"open failed: {e}"
            return
        self.ok = True
        self.reason = "ok"

    def commit(self, event_type, body):
        if not self.ok:
            return None
        ev = self._append(
            self.vc,
            event_type=event_type,
            body=body,
            expected_head=self._read_head(self.vc.conn),
        )
        return ev.get("event_id")

    def verify(self):
        if not self.ok:
            return None
        return self._verify(self.db)

    def close(self):
        if self.ok:
            try:
                self.vc.close()
            except Exception:
                pass


# ---------------------------------------------------------------- engine

class Engine:
    """
    Wraps llama-cpp-python with exact-token scoring and explicit state control.

    Why direct bindings and not llama-server: the server keeps a prompt-prefix
    cache and decides on its own whether to reuse or reprocess. For a recurrent
    model that decision is invisible from outside and silently determines
    whether a result means anything. Here every measurement loads an explicit
    state and feeds an explicit token list. Nothing is inferred.
    """

    def __init__(self, model_path, n_ctx=512, n_threads=None, n_batch=512, seed=0,
                 verbose=False):
        import llama_cpp
        from llama_cpp import Llama

        self.llama_cpp = llama_cpp
        self.model_path = model_path
        self.cfg = dict(
            n_ctx=n_ctx,
            n_threads=n_threads or max(1, (os.cpu_count() or 4) // 2),
            n_batch=n_batch,
            seed=seed,
        )
        def _build(verbose):
            return Llama(
                model_path=model_path,
                n_ctx=n_ctx,
                n_threads=self.cfg["n_threads"],
                n_batch=n_batch,
                seed=seed,
                logits_all=False,
                verbose=verbose,
            )

        try:
            self.llm = _build(verbose)
        except Exception as e:
            # llama.cpp writes the real reason to stderr and llama-cpp-python
            # then raises a bare ValueError. With verbose=False those lines are
            # suppressed, so the only thing that survives is a message that
            # names no cause. Re-run loudly so the diagnostic is on the record,
            # then re-raise. Never silently swallow the reason.
            if not verbose:
                sys.stderr.write(
                    "\n=== context creation failed; re-running with llama.cpp "
                    "logging enabled so the reason is visible ===\n")
                sys.stderr.flush()
                try:
                    _build(True)
                except Exception:
                    pass
                sys.stderr.write("=== end llama.cpp output ===\n")
                sys.stderr.flush()
            raise RuntimeError(
                f"could not create llama context (n_ctx={n_ctx}, n_batch={n_batch}, "
                f"n_threads={self.cfg['n_threads']}). Original: {e!r}. "
                f"The llama.cpp output above names the cause. This is an apparatus "
                f"fault before any declaration exists -- no gate failed and nothing "
                f"has been established about the model."
            ) from e

    # -- architecture check ------------------------------------------------

    def arch_is_recurrent(self):
        """
        Best-effort. If this is False the whole battery is meaningless --
        a transformer's 'state' is a KV cache of replayed tokens, which is
        exactly the thing the test exists to rule out.
        """
        try:
            md = self.llm.metadata
            for k, v in md.items():
                if k.endswith(".architecture") or k == "general.architecture":
                    return str(v).lower() in {
                        "rwkv6", "rwkv7", "arwkv7", "rwkv6qwen2", "mamba", "mamba2"
                    }, str(v)
        except Exception:
            pass
        return None, "unknown"

    # -- tokens ------------------------------------------------------------

    def tok(self, s, add_bos=False):
        return self.llm.tokenize(s.encode("utf-8"), add_bos=add_bos, special=False)

    def single_token_id(self, s):
        """
        Resolve a candidate string to exactly one token id, or fail loudly.
        A multi-token candidate silently changes what D means, so it is
        rejected at declare time rather than averaged over at run time.
        """
        ids = self.tok(s)
        if len(ids) != 1:
            raise ValueError(
                f"candidate {s!r} is {len(ids)} tokens ({ids}); D requires exactly 1. "
                f"Pick a different candidate at declare time."
            )
        return ids[0]

    def verify_alignment(self, query, value_str, candidate_id):
        """
        Apparatus validation, run at declare time, before any experiment.

        The discriminator assumes the first token generated after `query` is
        the candidate. Two ways that silently breaks:
          - the tokenizer merges across the query/value boundary, so `query`
            is not a token prefix of `query + value` at all;
          - `value` does not begin with the candidate token (e.g. "7319"
            tokenizes as a single unit, or as "73" + "19", not "7" + ...).
        Either way D would compare a token the model was never going to emit
        against another it was never going to emit, and report a clean number.
        """
        q = self.tok(query)
        full = self.tok(query + value_str)
        if full[: len(q)] != q:
            return False, {"reason": "tokenizer merges across the query/value boundary",
                           "query_tokens": q, "full_tokens": full}
        if len(full) <= len(q):
            return False, {"reason": "value contributes no tokens",
                           "query_tokens": q, "full_tokens": full}
        nxt = full[len(q)]
        return nxt == candidate_id, {
            "reason": "ok" if nxt == candidate_id else "first value token is not the candidate",
            "query_tokens": q,
            "next_token_id": nxt,
            "next_token_str": self.llm.detokenize([nxt]).decode("utf-8", "replace"),
            "candidate_id": candidate_id,
            "full_tokens": full,
        }

    # -- state -------------------------------------------------------------

    def reset(self):
        self.llm.reset()

    def eval_tokens(self, ids):
        self.llm.eval(ids)

    def logits_now(self):
        """
        Logits at the current final position, read straight from the context.

        NOT from llm.scores. With logits_all=False (the default) llama-cpp-python's
        eval() deliberately does not populate `scores` at all -- it is a `pass`.
        Reading scores there returns zeros, which would make D == 0.0 for every
        probe and produce a uniform FAIL that looks like a result about the model
        and is actually a result about this function. Verified in
        llama_cpp/llama.py eval() at v0.3.35.
        """
        import numpy as np
        ptr = self.llm._ctx.get_logits()
        return np.ctypeslib.as_array(ptr, shape=(self.llm._n_vocab,))

    def D(self, correct_id, wrong_id):
        lg = self.logits_now()
        # Guard the exact failure described above: if logits are degenerate,
        # say so loudly instead of emitting a confident 0.0.
        if not float(lg.any()):
            raise RuntimeError(
                "logits are all zero -- the runtime did not expose logits for this "
                "position. D is not measurable; this is an apparatus fault, not a "
                "result about the model. Do not record it as a failed probe."
            )
        return float(lg[correct_id]) - float(lg[wrong_id])

    # in-process state

    def snapshot(self):
        return self.llm.save_state()

    def restore(self, snap):
        self.llm.load_state(snap)

    # cross-process state -> disk

    def state_to_file(self, path, n_tokens_hint):
        """
        Writes the recurrent state to disk via the low-level C API, plus a
        sidecar recording how many tokens produced it. The sidecar is
        bookkeeping only; it is NOT replayed on load. If it were, the test
        would be measuring replay, which is the thing being ruled out.
        """
        lc = self.llama_cpp
        ctx = self.llm._ctx.ctx
        fn = getattr(lc, "llama_state_save_file", None) or getattr(lc, "llama_save_session_file", None)
        if fn is None:
            raise RuntimeError("no llama_state_save_file in this llama_cpp build")
        toks = (lc.llama_token * n_tokens_hint)(*self.llm.input_ids[:n_tokens_hint].tolist())
        ok = fn(ctx, path.encode("utf-8"), toks, ctypes.c_size_t(n_tokens_hint))
        if not ok:
            raise RuntimeError("llama_state_save_file returned false")
        with open(path + ".meta.json", "w") as f:
            json.dump({"n_tokens": n_tokens_hint, "saved_utc": _utc()}, f)
        return os.path.getsize(path)

    def state_from_file(self, path, n_ctx_cap=None):
        lc = self.llama_cpp
        ctx = self.llm._ctx.ctx
        fn = getattr(lc, "llama_state_load_file", None) or getattr(lc, "llama_load_session_file", None)
        if fn is None:
            raise RuntimeError("no llama_state_load_file in this llama_cpp build")
        meta = json.load(open(path + ".meta.json"))
        cap = n_ctx_cap or self.cfg["n_ctx"]
        buf = (lc.llama_token * cap)()
        n_out = ctypes.c_size_t(0)
        ok = fn(ctx, path.encode("utf-8"), buf, ctypes.c_size_t(cap), ctypes.byref(n_out))
        if not ok:
            raise RuntimeError("llama_state_load_file returned false")
        # sync python-side bookkeeping so eval() appends rather than restarts
        n = int(n_out.value)
        self.llm.n_tokens = n
        try:
            self.llm.input_ids[:n] = list(buf)[:n]
        except Exception:
            pass
        return n, meta


# ---------------------------------------------------------------- measure

def measure(eng, state_loader, context_text, correct_id, wrong_id):
    """
    One measurement. ALWAYS starts by loading an explicit state, because a
    recurrent state cannot be rewound -- there is no way to 'undo' an eval.
    Every D in this file is produced by this function and no other path.
    """
    state_loader()
    ids = eng.tok(context_text)
    if not ids:
        raise ValueError("empty context tokenization")
    eng.eval_tokens(ids)
    return eng.D(correct_id, wrong_id)


# ---------------------------------------------------------------- probes

def load_probes(path):
    """
    Probe strings and candidates are DECLARED INPUT, not code.

    In 3e18e8d they were hardcoded here, so disqualifying a probe forced a
    change to the instrument itself. The alignment gate refused that probe
    (trailing space in the query merged with the value's digits) and the
    instrument could not carry a correction without ceasing to be the same
    object. Probes now arrive as a reviewed file, hashed into the
    declaration, so a probe revision never touches measurement code again.

    The file is produced by qualify_probes.py, which loads the model with
    vocab_only=True and therefore cannot observe model behaviour at all.
    """
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    for section, keys in (("relation", ("state_A", "state_B", "query",
                                        "value_A", "value_B",
                                        "correct_str", "wrong_str")),
                          ("unrelated", ("query", "value_correct", "value_wrong",
                                         "correct_str", "wrong_str"))):
        if section not in data:
            raise SystemExit(f"probe file missing section {section!r}")
        for k in keys:
            if k not in data[section]:
                raise SystemExit(f"probe file: {section}.{k} missing")
    # consistency: the state text must actually contain what the gate checks
    rel = data["relation"]
    for label, val in (("state_A", rel["value_A"]), ("state_B", rel["value_B"])):
        if rel["query"] + val not in rel[label]:
            raise SystemExit(
                f"probe file: {label} does not contain query+value. The alignment "
                f"gate would validate a boundary the state never builds."
            )
    return data, hashlib.sha256(raw).hexdigest()


def build_declaration(eng, args, probe_data, probe_sha):
    """
    Resolve every probe to concrete token ids NOW, freeze them, hash them.
    After this, the harness cannot quietly pick a different comparison.
    """
    probes = {
        "relation": dict(probe_data["relation"]),
        "unrelated": dict(probe_data["unrelated"]),
    }
    for name, p in probes.items():
        p["correct_id"] = eng.single_token_id(p["correct_str"])
        p["wrong_id"] = eng.single_token_id(p["wrong_str"])
        if p["correct_id"] == p["wrong_id"]:
            raise ValueError(f"probe {name}: candidates tokenize identically")

    # Apparatus validation BEFORE the experiment. This is not outcome selection:
    # it checks that the discriminator compares the tokens it claims to compare.
    align = {}
    rel = probes["relation"]
    unr = probes["unrelated"]
    # Validation EXTENSION beyond 3e18e8d, reviewed and approved: the frozen
    # gate checked only the two relation values, so an edited probe file could
    # carry unrelated candidates that are distinct single tokens -- passing
    # single_token_id -- while not being the first token of their declared
    # values. The specificity gate would then compare tokens the model would
    # never emit, in the very gate meant to detect spurious drift.
    for label, q, value, cand in (
        ("state_A", rel["query"], rel["value_A"], rel["correct_id"]),
        ("state_B", rel["query"], rel["value_B"], rel["wrong_id"]),
        ("unrelated_correct", unr["query"], unr["value_correct"], unr["correct_id"]),
        ("unrelated_wrong", unr["query"], unr["value_wrong"], unr["wrong_id"]),
    ):
        ok, detail = eng.verify_alignment(q, value, cand)
        align[label] = {"pass": ok, **detail}
    if not all(a["pass"] for a in align.values()):
        raise SystemExit(
            "REFUSING to declare: probe/tokenizer alignment failed.\n"
            + json.dumps(align, indent=2)
            + "\n\nThe discriminator would compare tokens the model was never going "
              "to emit. Pick candidates that match the tokenization above, then declare."
        )

    recurrent, arch = eng.arch_is_recurrent()

    decl = {
        "decl_version": DECL_VERSION,
        "declared_utc": _utc(),
        "purpose": "state-retention apparatus test; NOT a test of the continuity thesis",
        "discriminator": "D = logit[correct] - logit[wrong] at final position "
                         "(== logP(correct) - logP(wrong); denominator cancels)",
        "model_path": os.path.abspath(args.model),
        "model_sha256": sha256_file(args.model),
        "model_arch": arch,
        "model_arch_is_recurrent": recurrent,
        "runtime": {
            "llama_cpp_version": eng.llama_cpp.__version__,
            **eng.cfg,
        },
        "probes": probes,
        "probe_file": os.path.abspath(args.probes),
        "probe_file_sha256": probe_sha,
        "probe_set_id": probe_data.get("probe_set_id", "(unnamed)"),
        "probe_alignment": align,
        "thresholds": {
            "jitter_n": 20,
            "jitter_n_provenance": "frozen before the run. Fixed now so the noise floor "
                                   "cannot move by choosing how many repetitions to collect "
                                   "after seeing the values.",
            "noise_k": 3.0,
            "noise_k_meaning": "CONSERVATIVE POLICY MULTIPLE OF THE OBSERVED RANGE "
                               "(max - min) over jitter_n repeats. This is NOT a 3-sigma "
                               "threshold and carries no statistical interpretation. "
                               "spread_stdev is recorded alongside so a later declaration "
                               "can adopt a sigma-based rule with stated provenance.",
            "noise_k_provenance": "policy constant, set by Claude 2026-09-19, no empirical "
                                  "basis. Replaceable in a NEW declaration; this one stays "
                                  "in the chain.",
            "min_margin_abs": 0.5,
            "min_margin_abs_provenance": "policy constant, arbitrary, set by Claude "
                                         "2026-09-19, in logit units. Exists because a "
                                         "deterministic runtime yields spread == 0.0, which "
                                         "would collapse the required margin to zero and "
                                         "reinstate the exact failure the noise floor was "
                                         "added to prevent. required_margin = "
                                         "max(noise_k * range, min_margin_abs). When this "
                                         "is the binding term the result is flagged, because "
                                         "the gate is then resting on an arbitrary number "
                                         "rather than a measured floor.",
            "floor_requires": "D(state_A) - D(fresh) > noise_k * jitter_spread. An absolute "
                              "threshold of 0.0 would pass on noise: a margin smaller than the "
                              "runtime's own wobble is not a detection. This is why jitter runs "
                              "first -- it is calibration, and it supplies the threshold the "
                              "floor gate is scored against. floor is still the first GATE; "
                              "jitter is not a gate and cannot fail.",
            "floor_note": "If this fails there is no instrument, and that is a recorded "
                          "result, not something to tune around.",
            "causality_requires": "D(state_A) > +noise_k*spread AND D(state_B) < -noise_k*spread "
                                  "-- same C, same candidate tokens, opposite states, D flips "
                                  "sign by more than the noise floor",
            "specificity_min_ratio": 3.0,
            "specificity_note": "|dD_related| must exceed |dD_unrelated| by this factor. "
                                "Requiring zero drift would be too strong: any state shifts "
                                "general distributions somewhat.",
            "restart_tol": None,
            "restart_tol_note": "NOT declarable in advance. Set by the jitter calibration, "
                                "then frozen forward-only in a stage-2 declaration. A tolerance "
                                "picked after seeing the restart result would be selection.",
        },
    }
    decl["declaration_sha256"] = canon_hash({k: v for k, v in decl.items()})
    return decl


# ---------------------------------------------------------------- battery

def run_jitter(eng, decl, reps=None):
    """
    NOT in the original spec. Added because 'restart equivalence within a
    predeclared tolerance' cannot be declared without knowing the runtime's
    own nondeterminism first. Same state, same C, repeated: any spread here
    is floating-point reduction-order noise, not state loss. This is the
    detection floor for the restart probe.
    """
    reps = reps or decl["thresholds"]["jitter_n"]
    p = decl["probes"]["relation"]
    base = p["state_A"]

    snap = None

    def load_fresh():
        eng.reset()
        eng.eval_tokens(eng.tok(base))

    # build once, snapshot, then replay from snapshot repeatedly
    load_fresh()
    snap = eng.snapshot()

    vals = []
    for _ in range(reps):
        vals.append(measure(eng, lambda: eng.restore(snap), p["query"],
                            p["correct_id"], p["wrong_id"]))
    rng = max(vals) - min(vals)
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / max(1, len(vals) - 1)
    stdev = var ** 0.5
    return {"n": reps, "spread_range": rng, "spread_stdev": stdev, "mean": mean,
            "values": vals, "deterministic": rng == 0.0,
            "suggested_restart_tol": max(rng * 10.0, 1e-3)}


def required_margin(decl, spread_range):
    """max(noise_k * observed range, min_margin_abs). Returns which term binds."""
    t = decl["thresholds"]
    a = t["noise_k"] * spread_range
    b = t["min_margin_abs"]
    return (a, "noise_k*range") if a >= b else (b, "min_margin_abs (ARBITRARY)")


def run_floor(eng, decl, spread):
    """Scored against the measured noise floor, not against zero."""
    p = decl["probes"]["relation"]
    need, binding = required_margin(decl, spread)

    def with_A():
        eng.reset()
        eng.eval_tokens(eng.tok(p["state_A"]))

    d_state = measure(eng, with_A, p["query"], p["correct_id"], p["wrong_id"])
    d_fresh = measure(eng, eng.reset, p["query"], p["correct_id"], p["wrong_id"])
    delta = d_state - d_fresh
    return {"D_with_state": d_state, "D_fresh": d_fresh, "delta": delta,
            "required_margin": need, "margin_binding_term": binding,
            "jitter_range": spread, "pass": delta > need}


def run_causality(eng, decl, spread):
    p = decl["probes"]["relation"]

    def mk(text):
        def f():
            eng.reset()
            eng.eval_tokens(eng.tok(text))
        return f

    d_a = measure(eng, mk(p["state_A"]), p["query"], p["correct_id"], p["wrong_id"])
    d_b = measure(eng, mk(p["state_B"]), p["query"], p["correct_id"], p["wrong_id"])
    need, binding = required_margin(decl, spread)
    return {"D_state_A": d_a, "D_state_B": d_b, "required_margin": need,
            "margin_binding_term": binding, "jitter_range": spread,
            "pass": (d_a > need and d_b < -need)}


def run_specificity(eng, decl):
    rel = decl["probes"]["relation"]
    unr = decl["probes"]["unrelated"]

    def with_A():
        eng.reset()
        eng.eval_tokens(eng.tok(rel["state_A"]))

    d_rel_state = measure(eng, with_A, rel["query"], rel["correct_id"], rel["wrong_id"])
    d_rel_fresh = measure(eng, eng.reset, rel["query"], rel["correct_id"], rel["wrong_id"])
    d_unr_state = measure(eng, with_A, unr["query"], unr["correct_id"], unr["wrong_id"])
    d_unr_fresh = measure(eng, eng.reset, unr["query"], unr["correct_id"], unr["wrong_id"])

    m_rel = abs(d_rel_state - d_rel_fresh)
    m_unr = abs(d_unr_state - d_unr_fresh)
    ratio = (m_rel / m_unr) if m_unr > 1e-9 else float("inf")
    return {"shift_related": m_rel, "shift_unrelated": m_unr, "ratio": ratio,
            "pass": ratio >= decl["thresholds"]["specificity_min_ratio"]}


def run_restart_save(eng, decl, state_file):
    """Process 1: build state, measure live D, write state to disk, exit."""
    p = decl["probes"]["relation"]
    eng.reset()
    ids = eng.tok(p["state_A"])
    eng.eval_tokens(ids)
    nbytes = eng.state_to_file(state_file, eng.llm.n_tokens)
    # measure live AFTER saving, from a snapshot of the same point
    snap = eng.snapshot()
    d_live = measure(eng, lambda: eng.restore(snap), p["query"],
                     p["correct_id"], p["wrong_id"])
    return {"D_live": d_live, "state_bytes": nbytes, "n_tokens": len(ids)}


def run_restart_load(eng, decl, state_file):
    """Process 2: fresh process, restore from disk, measure. No replay."""
    p = decl["probes"]["relation"]

    def load():
        eng.reset()
        eng.state_from_file(state_file)

    d_restored = measure(eng, load, p["query"], p["correct_id"], p["wrong_id"])
    return {"D_restored": d_restored}


# ---------------------------------------------------------------- cli

def persist_declaration(decl, decl_path, led, _link=None):
    """
    Order of operations, and why each part is the way it is.

    The revision before this wrote declaration.json FIRST and swallowed every
    ledger failure, so `declare` could exit 0 with a declaration on disk and
    nothing in the chain. An uncommitted declaration is exactly what the
    precommitment exists to prevent.

    Reversing that naively creates three further hazards, all found in review:

    FLOATS. canon/1 is "RFC 8785 (JCS) MINUS IEEE-754 floats" -- integers only,
    and a token containing `.`, `e` or `E` is rejected as FLOAT_IN_HASHED_FIELD.
    Committing the declaration as a dict therefore fails on noise_k 3.0,
    min_margin_abs 0.5 and specificity_min_ratio 3.0. The declaration is
    committed as serialized JSON TEXT plus its byte hash instead. The thresholds
    themselves are unchanged; only the representation inside the event differs.
    The committed text is byte-identical to the published file, so the hash in
    the chain verifies the file exactly.

    CLOBBERING. `open(pending, "w")` truncates an existing recovery file and
    `os.replace` overwrites an existing declaration -- so a second declare could
    destroy an unrecovered .pending or an existing commitment. Both paths are
    now refused up front, the pending file is created O_EXCL, and publication
    uses os.link, which fails with EEXIST rather than overwriting.

      1. refuse if either the declaration or a .pending already exists
      2. create .pending exclusively, write, fsync
      3. commit the serialized declaration text to the chain
      4. publish by hard link (atomic, cannot overwrite), then drop .pending

    Failure at 2 -> nothing committed, nothing written.
    Failure at 3 -> .pending removed, nothing in the chain, refuse.
    Failure at 4 -> chain HAS it and .pending HAS it: recoverable twice over,
                    with the recovery command printed.
    """
    link = _link or os.link
    blob = json.dumps(decl, indent=2, sort_keys=True) + "\n"
    blob_bytes = blob.encode("utf-8")
    blob_sha = hashlib.sha256(blob_bytes).hexdigest()
    pending = decl_path + ".pending"

    if os.path.exists(decl_path):
        raise SystemExit(
            f"REFUSING: {decl_path} already exists. A declaration is a "
            f"precommitment; overwriting one silently replaces a claim that has "
            f"already been committed to the chain. Move it aside deliberately, "
            f"or declare to a different path."
        )
    if os.path.exists(pending):
        raise SystemExit(
            f"REFUSING: {pending} already exists. That is an unrecovered "
            f"declaration from a previous run whose publication failed, and its "
            f"commitment is already in the chain. Recover or remove it "
            f"deliberately before declaring again."
        )

    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "wb") as f:
        f.write(blob_bytes)
        f.flush()
        os.fsync(f.fileno())

    try:
        ev = led.commit("measurement_commitment", {
            "kind": "state_probe_declaration",
            "declaration_sha256": decl["declaration_sha256"],
            "model_sha256": decl["model_sha256"],
            "probe_file_sha256": decl["probe_file_sha256"],
            "probe_set_id": decl["probe_set_id"],
            "declared_utc": decl["declared_utc"],
            # Serialized TEXT, never a dict: canon/1 rejects floats, and the
            # thresholds are floats. The chain is still sufficient to recover
            # the declaration, because this is the whole of it.
            "declaration_json": blob,
            "declaration_json_sha256": blob_sha,
        })
    except Exception as e:
        try:
            os.remove(pending)
        except OSError:
            pass
        raise SystemExit(
            f"REFUSING: ledger commit failed ({e!r}). No declaration was written "
            f"and nothing is in the chain. This is not a probe or gate result."
        )

    if ev is None:
        try:
            os.remove(pending)
        except OSError:
            pass
        raise SystemExit(
            "REFUSING: ledger commit returned no event id. No declaration was "
            "written and nothing is in the chain."
        )

    try:
        link(pending, decl_path)
    except Exception as e:
        raise SystemExit(
            f"COMMITTED BUT NOT PUBLISHED: the declaration IS in the chain as "
            f"event {ev}, but publishing it to {decl_path} failed ({e!r}).\n"
            f"Nothing is lost. The exact bytes are at {pending} "
            f"(sha256 {blob_sha}), and the full declaration text is inside the "
            f"ledger event.\n"
            f"Recover with:  mv {pending!r} {decl_path!r}\n"
            f"Do NOT re-run declare -- that would commit a second declaration."
        )
    try:
        os.unlink(pending)
    except OSError:
        pass
    return ev


def cmd_declare(args):
    # Ledger FIRST. A declaration that cannot be committed must not be built,
    # and a ledger problem should surface before a seven-second model load.
    if not args.ledger:
        print("REFUSING: --ledger is required for declare. Without it the "
              "declaration would be written but never committed to the chain, "
              "which defeats the precommitment entirely.")
        return 3
    led = Ledger(args.ledger)
    if not led.ok:
        print(f"REFUSING: ledger unavailable ({led.reason}). Nothing was written "
              f"and nothing is in the chain. Fix the ledger path, then declare.")
        return 3

    # Everything after the ledger opens is inside try/finally. Model loading and
    # declaration construction can both raise or SystemExit, and previously
    # either one leaked an open ledger handle.
    try:
        eng = Engine(args.model, args.n_ctx, args.threads, args.n_batch, args.seed)
        rec, arch = eng.arch_is_recurrent()
        if rec is False:
            print(f"REFUSING: model architecture is {arch!r}, which is not recurrent.")
            print("A transformer's saved 'state' is a KV cache of replayed tokens.")
            print("This battery would measure replay, which is the thing it exists to rule out.")
            return 2
        probe_data, probe_sha = load_probes(args.probes)
        decl = build_declaration(eng, args, probe_data, probe_sha)
        ev = persist_declaration(decl, args.decl, led)
    finally:
        led.close()

    print(f"declaration written: {args.decl}")
    print(f"declaration_sha256:  {decl['declaration_sha256']}")
    print(f"probe_set_id:        {decl['probe_set_id']}")
    print(f"probe_file_sha256:   {decl['probe_file_sha256']}")
    print(f"model arch:          {arch} (recurrent={rec})")
    print(f"ledger:              committed {ev}")
    return 0


def cmd_run(args):
    decl = json.loads(Path(args.decl).read_text())
    eng = Engine(args.model, decl["runtime"]["n_ctx"], decl["runtime"]["n_threads"],
                 decl["runtime"]["n_batch"], decl["runtime"]["seed"])

    live_hash = sha256_file(args.model)
    if live_hash != decl["model_sha256"]:
        print("REFUSING: model file does not match the declaration.")
        return 2

    results = {"declaration_sha256": decl["declaration_sha256"], "run_utc": _utc()}
    spread = None
    order = ["jitter", "floor", "causality", "specificity"]
    gate_failed = None

    for name in order:
        if name == "jitter":
            r = run_jitter(eng, decl)
            r["pass"] = True  # calibration, not a gate -- it cannot fail
            spread = r["spread_range"]
        elif name == "floor":
            r = run_floor(eng, decl, spread)
        elif name == "causality":
            r = run_causality(eng, decl, spread)
        else:
            r = run_specificity(eng, decl)
        results[name] = r
        verdict = "PASS" if r.get("pass") else "FAIL"
        print(f"[{verdict}] {name}: " + json.dumps(
            {k: (round(v, 5) if isinstance(v, float) else v)
             for k, v in r.items() if k != "values"}))
        if not r.get("pass"):
            gate_failed = name
            break

    if gate_failed:
        print(f"\nSTOPPED at {gate_failed}. Later gates are not meaningful once an "
              f"earlier one fails. This is a recorded result, not a tuning prompt:")
        print("changing a probe now requires a NEW declaration, forward-only.")

    led = Ledger(args.ledger)
    ev = led.commit("observation", {
        "kind": "state_probe_battery",
        "declaration_sha256": decl["declaration_sha256"],
        "results": json.loads(json.dumps(results)),
        "gate_failed": gate_failed,
    })
    chain = led.verify()
    led.close()
    Path(args.out).write_text(json.dumps(results, indent=2, sort_keys=True))
    print(f"\nresults: {args.out}")
    print(f"ledger:  {'committed ' + str(ev) if ev else 'NOT COMMITTED (' + led.reason + ')'}")
    if chain is not None:
        print(f"chain:   {'clean' if chain == [] else chain}")
    return 0 if not gate_failed else 1


def cmd_restart(args):
    """Two real processes. Parent orchestrates; children do the work."""
    decl = json.loads(Path(args.decl).read_text())
    if args.phase == "save":
        eng = Engine(args.model, decl["runtime"]["n_ctx"], decl["runtime"]["n_threads"],
                     decl["runtime"]["n_batch"], decl["runtime"]["seed"])
        print(json.dumps(run_restart_save(eng, decl, args.state_file)))
        return 0
    if args.phase == "load":
        eng = Engine(args.model, decl["runtime"]["n_ctx"], decl["runtime"]["n_threads"],
                     decl["runtime"]["n_batch"], decl["runtime"]["seed"])
        print(json.dumps(run_restart_load(eng, decl, args.state_file)))
        return 0

    # orchestrate
    tol = args.tol
    if tol is None:
        print("REFUSING: --tol is required and must come from the jitter calibration.")
        print("A tolerance chosen after seeing the restart result is selection, not a test.")
        return 2

    base = [sys.executable, __file__, "restart", "--model", args.model,
            "--decl", args.decl, "--state-file", args.state_file]
    s = json.loads(subprocess.run(base + ["--phase", "save"],
                                  capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])
    l = json.loads(subprocess.run(base + ["--phase", "load"],
                                  capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])

    delta = abs(s["D_live"] - l["D_restored"])
    passed = delta <= tol
    res = {"D_live": s["D_live"], "D_restored": l["D_restored"], "delta": delta,
           "tol": tol, "state_bytes": s["state_bytes"], "pass": passed,
           "declaration_sha256": decl["declaration_sha256"], "run_utc": _utc()}
    print(f"[{'PASS' if passed else 'FAIL'}] restart: " + json.dumps(res))

    led = Ledger(args.ledger)
    ev = led.commit("observation", {"kind": "state_probe_restart", "results": res})
    led.close()
    print(f"ledger: {'committed ' + str(ev) if ev else 'NOT COMMITTED (' + led.reason + ')'}")
    return 0 if passed else 1


def cmd_doctor(args):
    """
    Diagnostic only. Not part of the battery, cannot pass or fail anything,
    and touches no declaration. It exists to make the runtime say out loud
    why it will not start.
    """
    import llama_cpp
    print(f"llama_cpp version : {llama_cpp.__version__}")
    print(f"model             : {args.model}")
    print(f"exists            : {os.path.exists(args.model)}")
    if os.path.exists(args.model):
        print(f"size              : {os.path.getsize(args.model)/1e9:.2f} GB")
    print()
    tried = []
    for n_ctx, n_batch in [(args.n_ctx, args.n_batch), (2048, 2048), (4096, 512), (1024, 1024)]:
        print(f"--- attempting n_ctx={n_ctx} n_batch={n_batch} (llama.cpp logging ON) ---")
        try:
            eng = Engine(args.model, n_ctx, args.threads, n_batch, 0, verbose=True)
            rec, arch = eng.arch_is_recurrent()
            print(f"  OK. arch={arch} recurrent={rec}")
            tried.append({"n_ctx": n_ctx, "n_batch": n_batch, "ok": True, "arch": arch})
            print()
            print("WORKING CONFIGURATION FOUND. Pass these to declare:")
            print(f"  --n-ctx {n_ctx} --n-batch {n_batch}")
            print()
            print("Note: this sweep is apparatus diagnosis, not probe tuning. It changes "
                  "no threshold and no probe, and no declaration existed to alter.")
            return 0
        except Exception as e:
            print(f"  FAILED: {e}")
            tried.append({"n_ctx": n_ctx, "n_batch": n_batch, "ok": False, "err": repr(e)})
        print()
    print("No configuration created a context. The llama.cpp output above is the evidence.")
    print("Most likely: this build of llama.cpp cannot load this rwkv7 GGUF at all,")
    print("which is a finding about the runtime, not about state retention.")
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--model", required=True)
        p.add_argument("--decl", default="declaration.json")
        p.add_argument("--ledger", default=None,
                       help="path to 'ledger core 2' dir; REQUIRED for declare")

    d = sub.add_parser("declare", help="freeze probes+thresholds into the ledger BEFORE running")
    common(d)
    d.add_argument("--probes", required=True,
                   help="reviewed probe file from qualify_probes.py")
    d.add_argument("--n-ctx", type=int, default=512)
    d.add_argument("--threads", type=int, default=None)
    d.add_argument("--n-batch", type=int, default=512)
    d.add_argument("--seed", type=int, default=0)
    d.set_defaults(fn=cmd_declare)

    r = sub.add_parser("run", help="jitter -> floor -> causality -> specificity")
    common(r)
    r.add_argument("--out", default="results.json")
    r.set_defaults(fn=cmd_run)

    s = sub.add_parser("restart", help="two-process save/restore equivalence")
    common(s)
    s.add_argument("--state-file", default="s2.state")
    s.add_argument("--tol", type=float, default=None)
    s.add_argument("--phase", choices=["save", "load"], default=None)
    s.set_defaults(fn=cmd_restart)

    dr = sub.add_parser("doctor", help="diagnose why the runtime will not start (no gates, no declaration)")
    dr.add_argument("--model", required=True)
    dr.add_argument("--n-ctx", type=int, default=512)
    dr.add_argument("--n-batch", type=int, default=512)
    dr.add_argument("--threads", type=int, default=None)
    dr.set_defaults(fn=cmd_doctor)

    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()

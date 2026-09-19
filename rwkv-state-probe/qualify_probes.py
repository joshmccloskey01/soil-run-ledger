#!/usr/bin/env python3
"""
Probe qualification -- TOKENIZER ONLY.

Loads the model with vocab_only=True. No context is created, no forward pass
is possible, and no logit can be read. Selecting a probe because the model
answers it correctly is therefore not merely forbidden here, it is
unavailable: this tool cannot observe model behaviour at all.

What it checks, per candidate design, for BOTH state values:

  1. PREFIX      query is a genuine token prefix of query+value
                 (this is what disqualified KOR = 7319 against 3e18e8d:
                  the query's trailing space merged with the digits)
  2. FIRST TOKEN the value contributes at least one token past the prefix
  3. ROUND TRIP  detokenize(first_token) re-tokenizes to exactly that one
                 token, so the candidate can be written into the probe file
                 as a string and re-verified later by the alignment gate
  4. DISTINCT    candidate_A != candidate_B, or D cannot discriminate

A design passes only if all four hold for both values, and for the unrelated
probe. Passing means the discriminator compares tokens the model could emit
at that position. It says nothing about whether the model will emit them --
that is the floor gate's job, and it is not this tool's business.

Usage:
    python3 qualify_probes.py --model MODEL.gguf
    python3 qualify_probes.py --model MODEL.gguf --designs designs.json
    python3 qualify_probes.py --model MODEL.gguf --choose B --emit probes.json
"""

import argparse
import hashlib
import json
import os
import sys
import time

# Structural variations of the query/value boundary only. None of these is
# here because of anything a model did. The trailing-space hypothesis is a
# candidate to validate, not a verified fix, so design A -- the disqualified
# one -- is retained and re-measured rather than dropped.
DEFAULT_DESIGNS = {
    "A_frozen_disqualified": {
        "query": "KOR = ", "value_A": "7319", "value_B": "4412",
        "u_query": "ZIV = ", "u_value_correct": "8", "u_value_wrong": "3",
        "note": "the 3e18e8d design; retained so its refusal is reproducible",
    },
    "B_space_in_value": {
        "query": "KOR =", "value_A": " 7319", "value_B": " 4412",
        "u_query": "ZIV =", "u_value_correct": " 8", "u_value_wrong": " 3",
        "note": "trailing space moved from query into value",
    },
    "C_colon_no_space": {
        "query": "KOR:", "value_A": " 7319", "value_B": " 4412",
        "u_query": "ZIV:", "u_value_correct": " 8", "u_value_wrong": " 3",
        "note": "colon separator, space in value",
    },
    "D_equals_tight": {
        "query": "KOR=", "value_A": "7319", "value_B": "4412",
        "u_query": "ZIV=", "u_value_correct": "8", "u_value_wrong": "3",
        "note": "no space anywhere at the boundary",
    },
    "E_newline_boundary": {
        "query": "KOR =\n", "value_A": "7319", "value_B": "4412",
        "u_query": "ZIV =\n", "u_value_correct": "8", "u_value_wrong": "3",
        "note": "newline as the boundary character",
    },
    "F_word_values": {
        "query": "KOR =", "value_A": " seven", "value_B": " four",
        "u_query": "ZIV =", "u_value_correct": " eight", "u_value_wrong": " three",
        "note": "word values instead of digit runs",
    },
}


class Vocab:
    """vocab_only load. No context, no logits, no forward pass."""

    def __init__(self, model_path):
        from llama_cpp import Llama
        self.llm = Llama(model_path=model_path, vocab_only=True, verbose=False)

    def tok(self, s):
        return self.llm.tokenize(s.encode("utf-8"), add_bos=False, special=False)

    def detok(self, ids):
        return self.llm.detokenize(ids).decode("utf-8", "replace")


def check_pair(v, query, value):
    """The four checks for one query/value pair. Pure tokenization."""
    q = v.tok(query)
    full = v.tok(query + value)
    out = {"query_tokens": q, "full_tokens": full}

    if full[: len(q)] != q:
        out.update(pass_=False, reason="PREFIX: query is not a token prefix of query+value "
                                       "(boundary merge)")
        return out
    if len(full) <= len(q):
        out.update(pass_=False, reason="FIRST TOKEN: value contributes no tokens")
        return out

    first = full[len(q)]
    s = v.detok([first])
    rt = v.tok(s)
    out.update(first_token=first, first_token_str=s, round_trip=rt)

    if rt != [first]:
        out.update(pass_=False, reason=f"ROUND TRIP: detokenized {s!r} re-tokenizes to {rt}, "
                                       f"not [{first}]")
        return out

    out.update(pass_=True, reason="ok")
    return out


def check_design(v, d):
    r = {
        "relation_A": check_pair(v, d["query"], d["value_A"]),
        "relation_B": check_pair(v, d["query"], d["value_B"]),
        "unrelated_correct": check_pair(v, d["u_query"], d["u_value_correct"]),
        "unrelated_wrong": check_pair(v, d["u_query"], d["u_value_wrong"]),
    }
    failures = [k for k, x in r.items() if not x["pass_"]]

    distinct = None
    if r["relation_A"]["pass_"] and r["relation_B"]["pass_"]:
        distinct = r["relation_A"]["first_token"] != r["relation_B"]["first_token"]
        if not distinct:
            failures.append("DISTINCT: state_A and state_B yield the same first token; "
                            "D cannot discriminate")
    if r["unrelated_correct"]["pass_"] and r["unrelated_wrong"]["pass_"]:
        if r["unrelated_correct"]["first_token"] == r["unrelated_wrong"]["first_token"]:
            failures.append("DISTINCT: unrelated candidates are the same token")

    r["distinct"] = distinct
    r["failures"] = failures
    r["pass_"] = not failures
    return r


def build_probe_file(d, r, design_name, model_path, model_sha):
    """Emit probe data as DECLARED INPUT. Candidates are written explicitly so
    the alignment gate re-verifies them rather than deriving and trusting them."""
    probes = {
        "probe_set_id": design_name,
        "note": d["note"],
        "qualified_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "qualified_against_model_sha256": model_sha,
        "selection_basis": "tokenization alignment only; no model forward pass was "
                           "performed by the qualifying tool (vocab_only=True)",
        "relation": {
            "state_A": d["query"] + d["value_A"] + "\n",
            "state_B": d["query"] + d["value_B"] + "\n",
            "query": d["query"],
            "value_A": d["value_A"],
            "value_B": d["value_B"],
            "correct_str": r["relation_A"]["first_token_str"],
            "wrong_str": r["relation_B"]["first_token_str"],
        },
        "unrelated": {
            "query": d["u_query"],
            "value_correct": d["u_value_correct"],
            "value_wrong": d["u_value_wrong"],
            "correct_str": r["unrelated_correct"]["first_token_str"],
            "wrong_str": r["unrelated_wrong"]["first_token_str"],
        },
    }
    return probes


def sha256_file(p, chunk=1 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--designs", help="JSON file of candidate designs; default is built-in")
    ap.add_argument("--choose", help="design name to emit")
    ap.add_argument("--emit", help="path to write probes.json for --choose")
    a = ap.parse_args()

    designs = DEFAULT_DESIGNS
    if a.designs:
        designs = json.load(open(a.designs))

    print(f"model: {a.model}")
    model_sha = sha256_file(a.model)
    print(f"sha256: {model_sha}")
    print("loading vocabulary only -- no context, no forward pass possible\n")
    v = Vocab(a.model)

    results = {}
    for name, d in designs.items():
        r = check_design(v, d)
        results[name] = r
        print(f"{'PASS' if r['pass_'] else 'FAIL'}  {name}   ({d['note']})")
        for key in ("relation_A", "relation_B", "unrelated_correct", "unrelated_wrong"):
            x = r[key]
            if x["pass_"]:
                print(f"    {key:18} q={x['query_tokens']} full={x['full_tokens']} "
                      f"-> {x['first_token']} {x['first_token_str']!r}")
            else:
                print(f"    {key:18} q={x['query_tokens']} full={x['full_tokens']}")
                print(f"    {'':18} {x['reason']}")
        for f in r["failures"]:
            if f.startswith("DISTINCT"):
                print(f"    {'':18} {f}")
        print()

    passing = [n for n, r in results.items() if r["pass_"]]
    print("=" * 70)
    print(f"designs passing tokenization alignment: {passing or 'NONE'}")
    if not passing:
        print("\nNo candidate design satisfies alignment against this tokenizer.")
        print("The single-token-margin discriminator may be unusable for this model,")
        print("and D would need redefining. That is a finding, not a prompt to invent")
        print("more designs until one passes.")
        return 1

    print("\nPassing means the discriminator compares tokens the model COULD emit at")
    print("that position. It says nothing about whether it WILL -- that is the floor")
    print("gate, and nothing here has tested it.")

    if a.choose:
        if a.choose not in results:
            print(f"\n--choose {a.choose}: no such design")
            return 2
        if not results[a.choose]["pass_"]:
            print(f"\n--choose {a.choose}: that design FAILED qualification; refusing to emit")
            return 2
        probes = build_probe_file(designs[a.choose], results[a.choose],
                                  a.choose, a.model, model_sha)
        blob = json.dumps(probes, indent=2, sort_keys=True)
        if a.emit:
            open(a.emit, "w").write(blob + "\n")
            print(f"\nwrote {a.emit}")
            print(f"probe_file_sha256: {sha256_file(a.emit)}")
            print("\nReview this file before any declaration attempt.")
        else:
            print("\n" + blob)
    return 0


if __name__ == "__main__":
    sys.exit(main())

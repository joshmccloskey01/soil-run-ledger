#!/usr/bin/env python3
"""
EXTERNAL diagnosis of the pre-declaration context-creation failure.

Standalone. It does not import state_probe, does not read or write any
declaration, does not touch the ledger, and does not change the frozen
harness. It only asks the runtime to say why it will not start.

Protocol, in order:

  1. CPU-only, library defaults otherwise, verbose.
     If this FAILS -> stop. Report the verbose llama.cpp cause. Change
     nothing else: not the version, not the model file, not the harness.

  2. Only if 1 succeeds: repeat with the settings the frozen harness
     requests, including its backend/offload behaviour (the frozen harness
     sets no n_gpu_layers, so the wheel's default backend is used).

  3. Only if 2 fails: bisect. One frozen setting at a time on top of the
     known-good CPU baseline, so the failing variable is named rather than
     guessed.

Each trial runs in its own SUBPROCESS. llama.cpp can abort() the process on
some failures; in-process capture would lose the log at exactly the moment
it matters. The parent captures the child's real stdout and stderr file
descriptors, so C-level writes are preserved.

Usage:
    python3 diagnose_context.py --model /path/to/model.gguf
    python3 diagnose_context.py --model ... --log run.log
"""

import argparse
import json
import os
import subprocess
import sys
import time

FROZEN_N_CTX = 512
FROZEN_N_BATCH = 512
FROZEN_SEED = 0
FROZEN_LOGITS_ALL = False


def frozen_threads():
    """Exactly what the frozen harness computes."""
    return max(1, (os.cpu_count() or 4) // 2)


# ---------------------------------------------------------------- trials

def trial_specs():
    t = frozen_threads()
    cpu = {"n_gpu_layers": 0}
    frozen = {
        "n_ctx": FROZEN_N_CTX,
        "n_batch": FROZEN_N_BATCH,
        "n_threads": t,
        "seed": FROZEN_SEED,
        "logits_all": FROZEN_LOGITS_ALL,
    }
    return {
        # stage 1
        "1_cpu_only_defaults": dict(cpu),
        # stage 2 -- what the frozen harness actually requests, backend included
        "2_frozen_as_requested": dict(frozen),
        # stage 3 -- bisect, each on the CPU baseline
        "3a_cpu_plus_nctx": {**cpu, "n_ctx": FROZEN_N_CTX},
        "3b_cpu_plus_nbatch": {**cpu, "n_batch": FROZEN_N_BATCH},
        "3c_cpu_plus_threads": {**cpu, "n_threads": t},
        "3d_cpu_plus_seed": {**cpu, "seed": FROZEN_SEED},
        "3e_cpu_plus_logits_all": {**cpu, "logits_all": FROZEN_LOGITS_ALL},
        "3f_cpu_plus_all_frozen": {**cpu, **frozen},
    }


def run_child(model, kwargs):
    """One construction attempt, in this process. Invoked via --child."""
    import llama_cpp
    from llama_cpp import Llama

    sys.stderr.write(f"interpreter {sys.executable}\n")
    sys.stderr.write(f"llama_cpp {llama_cpp.__version__} "
                     f"({os.path.dirname(llama_cpp.__file__)})\n")
    sys.stderr.write(f"kwargs {json.dumps(kwargs, sort_keys=True)}\n")
    sys.stderr.flush()

    llm = Llama(model_path=model, verbose=True, **kwargs)

    info = {"ok": True}
    try:
        info["n_ctx"] = llm.n_ctx()
        md = getattr(llm, "metadata", {}) or {}
        for k, v in md.items():
            if k.endswith(".architecture") or k == "general.architecture":
                info["arch"] = str(v)
                break
    except Exception as e:
        info["post_check_error"] = repr(e)
    sys.stdout.write("RESULT " + json.dumps(info) + "\n")
    sys.stdout.flush()
    return 0


def run_trial(model, name, kwargs, log):
    cmd = [sys.executable, os.path.abspath(__file__), "--child",
           "--model", model, "--kwargs", json.dumps(kwargs)]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.time() - t0

    ok = p.returncode == 0 and "RESULT " in p.stdout
    header = (
        f"\n{'=' * 78}\nTRIAL {name}\n"
        f"kwargs   : {json.dumps(kwargs, sort_keys=True)}\n"
        f"exit     : {p.returncode}   ({dt:.1f}s)\n"
        f"verdict  : {'OK' if ok else 'FAILED'}\n{'-' * 78}\n"
    )
    body = "--- stdout ---\n" + p.stdout + "\n--- stderr (llama.cpp) ---\n" + p.stderr + "\n"
    log.write(header + body)
    log.flush()
    print(header.rstrip())
    if not ok:
        tail = [l for l in p.stderr.strip().splitlines() if l.strip()][-25:]
        print("  last 25 lines of llama.cpp output:")
        for l in tail:
            print("    " + l)
    return ok, p.stdout, p.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--log", default="context-diagnosis.log")
    ap.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--kwargs", default="{}", help=argparse.SUPPRESS)
    a = ap.parse_args()

    if a.child:
        sys.exit(run_child(a.model, json.loads(a.kwargs)))

    # ---- preflight: environment provenance, before any trial ----------------
    import platform
    env = {
        "interpreter": sys.executable,
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "machine": platform.machine(),          # arm64 vs x86_64 (Rosetta) matters
        "cpu_count": os.cpu_count(),
        "frozen_threads": frozen_threads(),
        "VIRTUAL_ENV": os.environ.get("VIRTUAL_ENV", "(none)"),
        "CONDA_PREFIX": os.environ.get("CONDA_PREFIX", "(none)"),
    }
    print("PREFLIGHT")
    for k, v in env.items():
        print(f"  {k:16}: {v}")

    try:
        import llama_cpp
        env["llama_cpp_version"] = llama_cpp.__version__
        env["llama_cpp_path"] = os.path.dirname(llama_cpp.__file__)
        print(f"  {'llama_cpp':16}: {llama_cpp.__version__}")
    except ImportError as e:
        print(f"  {'llama_cpp':16}: NOT IMPORTABLE -- {e}")
        print()
        print("STOP -- and this is NOT a trial-1 failure. No trial ran, llama.cpp was")
        print("never reached, and nothing has been established about context creation,")
        print("this model, or state retention.")
        print()
        print("The package is installed under a DIFFERENT interpreter than this one.")
        print("Find the one that has it, then re-run this script with it explicitly:")
        print()
        print("  for p in python3 python3.11 python3.12 python3.13 \\")
        print("           /usr/bin/python3 /opt/homebrew/bin/python3; do")
        print("    echo -n \"$p -> \"; $p -c \\")
        print("      'import llama_cpp,sys;print(sys.executable, llama_cpp.__version__)' \\")
        print("      2>/dev/null || echo 'no llama_cpp'")
        print("  done")
        print()
        print("  <that interpreter> diagnose_context.py --model <path>")
        sys.exit(3)

    if not os.path.exists(a.model):
        print(f"model not found: {a.model}")
        sys.exit(2)

    specs = trial_specs()
    with open(a.log, "w") as log:
        log.write(f"context diagnosis  {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
        log.write(f"model    : {a.model}\n")
        log.write(f"size     : {os.path.getsize(a.model)/1e9:.2f} GB\n")
        log.write("environment:\n")
        for k, v in env.items():
            log.write(f"  {k}: {v}\n")

        # ---- stage 1 -------------------------------------------------------
        ok1, _, _ = run_trial(a.model, "1_cpu_only_defaults",
                              specs["1_cpu_only_defaults"], log)
        if not ok1:
            msg = (
                "\nSTOP. CPU-only construction with library defaults failed.\n"
                "Per protocol nothing further is varied: not the llama-cpp-python\n"
                "version, not the model file, not the harness. The llama.cpp output\n"
                "above and in the log is the cause to report.\n\n"
                "This is a runtime/model-load finding. It establishes nothing about\n"
                "RWKV state retention, and no gate has failed.\n"
            )
            log.write(msg)
            print(msg)
            print(f"full log: {a.log}")
            sys.exit(1)

        # ---- stage 2 -------------------------------------------------------
        ok2, _, _ = run_trial(a.model, "2_frozen_as_requested",
                              specs["2_frozen_as_requested"], log)
        if ok2:
            msg = (
                "\nCPU-only succeeds AND the frozen harness settings succeed here.\n"
                "The original failure is therefore not reproduced by these settings\n"
                "alone. Something else differed at the time of the aborted run --\n"
                "environment, working directory, available memory, or a different\n"
                "interpreter/wheel. Report this log before changing anything.\n"
            )
            log.write(msg)
            print(msg)
            print(f"full log: {a.log}")
            sys.exit(0)

        # ---- stage 3 -------------------------------------------------------
        print("\nCPU-only works; frozen settings fail. Bisecting one variable at a time.\n")
        log.write("\nBISECT: CPU baseline is good, frozen settings are not.\n")
        culprits, cleared = [], []
        for name in ["3a_cpu_plus_nctx", "3b_cpu_plus_nbatch", "3c_cpu_plus_threads",
                     "3d_cpu_plus_seed", "3e_cpu_plus_logits_all", "3f_cpu_plus_all_frozen"]:
            ok, _, _ = run_trial(a.model, name, specs[name], log)
            (cleared if ok else culprits).append(name)

        summary = (
            "\n" + "=" * 78 + "\nBISECT SUMMARY\n"
            f"  cleared (context created) : {cleared or 'none'}\n"
            f"  failed                    : {culprits or 'none'}\n\n"
        )
        if "3f_cpu_plus_all_frozen" in cleared:
            summary += (
                "  All frozen parameters are fine ON CPU. Since trial 2 -- the same\n"
                "  parameters WITHOUT n_gpu_layers=0 -- failed, the discriminating\n"
                "  variable is the BACKEND/OFFLOAD, not any parameter I chose.\n"
            )
        elif culprits:
            summary += (
                "  The failing variable(s) are named above. Note which are mine:\n"
                f"    n_ctx={FROZEN_N_CTX} and n_batch={FROZEN_N_BATCH} are non-default\n"
                "    values I introduced; n_threads/seed/logits_all follow from them.\n"
            )
        summary += (
            "\n  None of this is a result about state retention. No gate ran and no\n"
            "  declaration exists.\n"
        )
        log.write(summary)
        print(summary)
        print(f"full log: {a.log}")
        sys.exit(1)


if __name__ == "__main__":
    main()

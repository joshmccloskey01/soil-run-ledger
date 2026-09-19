# state-retention apparatus test — runbook

## What this is and is not

It tests **one** claim:

> A live internal state can be saved, survive process death, and causally
> affect later computation without replay.

Passing earns the apparatus. It does **not** establish that continuity improves
learning, calibration, or capability. That is a later, separate verdict recorded
under a separate name.

Sequence, and nothing skips:

1. Prove state exists.
2. Prove the instrument can detect it.
3. Prove save/restore preserves it.
4. Prove return can correct it.   *(not built yet)*
5. Only then test whether continuity improves learning.   *(not built yet)*

This file covers 1–3.

## The discriminator, fixed before any run

    D = log P(correct token | C) − log P(wrong token | C)

Computed as the raw logit difference at the final position. That is exact rather
than an approximation: the log-sum-exp denominator is identical for both
candidates and cancels. No prose is judged. No sampling. No temperature.

## Setup on the Mac

```bash
pip3 install llama-cpp-python
```

Takes several minutes — it compiles. Then:

```bash
cd ~/soil-run-ledger/rwkv-state-probe
```

## Step 1 — declare, before anything runs

```bash
python3 state_probe.py declare \
  --model ~/Downloads/rwkv/rwkv7-2.9B-g1-iq4_nl.gguf \
  --ledger "/path/to/ledger core 2"
```

This freezes the probe set, the exact candidate token ids, and the thresholds,
hashes them, and commits the hash to the ledger **before** step 1 produces a
number. It refuses to continue if the model is not a recurrent architecture,
because a transformer's saved "state" is a KV cache of replayed tokens — the
exact thing this test exists to rule out.

Changing a probe after seeing a result requires a **new** declaration. It applies
forward only. The old one stays in the chain.

## Step 2 — run the battery

```bash
python3 state_probe.py run \
  --model ~/Downloads/rwkv/rwkv7-2.9B-g1-iq4_nl.gguf \
  --ledger "/path/to/ledger core 2"
```

Runs in order, stops at the first failure:

| step | what it asks | gate? |
|---|---|---|
| `jitter` | how much does D wobble with the state held identical? | no — calibration, cannot fail |
| `floor` | can the probe see a known injected relation (`KOR = 7319`)? | **first gate** |
| `causality` | same C, opposite states — does D flip sign? | gate |
| `specificity` | does the state move its own query rather than everything? | gate |

**Why `jitter` runs first even though `floor` is the first gate.** Jitter is not
a test, it is the measurement of the runtime's own wobble, and it supplies the
threshold the gates are scored against. `floor` passes only when the margin
exceeds `noise_k × jitter_spread`. Scored against a flat zero instead, a margin
smaller than the runtime's own noise would print PASS, and the battery would
hand over an instrument that detects nothing. `noise_k` is currently 3.0 — a
policy constant with no empirical basis, set by Claude, declared with that
provenance and replaceable by a better-founded value in a new declaration.

**If `floor` fails there is no instrument.** That is a recorded result, not a
tuning prompt. Do not adjust `KOR` until it works — that is choosing the probe
after seeing the outcome, and it converts the test into a description of its own
output.

## Step 3 — restart equivalence, two real processes

`jitter` prints `suggested_restart_tol`. Use it:

```bash
python3 state_probe.py restart \
  --model ~/Downloads/rwkv/rwkv7-2.9B-g1-iq4_nl.gguf \
  --ledger "/path/to/ledger core 2" \
  --tol <the number jitter printed>
```

One process builds the state, writes it to disk, and exits. A **second** process
starts cold, loads the state from disk, and measures. The token list is stored
beside the state as bookkeeping and is deliberately **not** replayed on load — if
it were, this would be measuring replay.

The command refuses to run without `--tol`, because a tolerance chosen after
seeing the restart number is selection rather than a test.

## What is not covered

- **Probe memory.** Divergence between restored and fresh could be the state
  carrying history, or the runtime's own prefix handling. Separating those needs
  the three variations: same state / different C, same C / different state, and
  restart / no-restart. The first two are in the battery. The third is the
  restart gate. They are not yet run as one attribution.
- **Steps 4 and 5.** Correction, and whether continuity beats the same
  information delivered without continuity. Not built.

## Status

Written against llama-cpp-python 0.3.35, verified by reading its source.
**Never executed against a real model** — the container it was written in has
HuggingFace blocked by egress policy, so no RWKV weights were reachable. First
run on the Mac is also its first test.

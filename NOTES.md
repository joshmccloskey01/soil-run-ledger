# Session notes

Append-only. Never rewrite an entry. Four parts, all required.

---

## 2026-09-19 — Local RWKV chat setup (no ledger work)

**Checked**
- The machine this session is actually running on: `uname` reports Linux
  (kernel 6.18.44), user `root`, home `/root`. Not macOS.
- `~/Downloads` and `~/Downloads/rwkv` — neither directory exists here.
- Filesystem-wide `find / -name "*.gguf"` — zero results.
- `which ollama lmstudio llama-cli llama-server` — all four absent.
- Repo contents: CLAUDE.md, ROPEU_Core_Corpus_v1_1.md, gym.html, run.html,
  seven zip archives. No NOTES.md existed before this entry; this file is new.

**Found**
- The session is a remote Linux container, not Josh's Mac. The three requested
  steps (run an Ollama tag, import a GGUF via Modelfile, place a file for
  LM Studio) all act on the Mac's filesystem and applications, so none of them
  can be executed from here regardless of which one would have worked.
- Deliverable produced instead: `rwkv-setup.sh`, a single macOS script that
  performs all three steps in the requested order with fallbacks. Syntax-checked
  with `bash -n` only. It has not been run on macOS, so nothing about its
  behaviour on the real machine is verified.

**Failed**
- The task as literally stated could not be done. Claimed capability here is
  zero, not partial.
- Unverified in the script: whether the Ollama tag `mollysama/rwkv-7-g1:2.9b`
  resolves; whether this build of llama.cpp/Ollama loads an rwkv7 GGUF at all;
  whether the User/Assistant template and stop tokens match what RWKV-7 G1
  expects; whether the LM Studio models directory on this Mac is `~/.lmstudio`
  or `~/.cache/lm-studio`. Each is a guess with a fallback, not a checked fact.
- The script is untested against a real GGUF. First run may fail.

**Would kill it**
- The script printing "DONE" and the model still not answering, or `ollama create`
  erroring on an unsupported architecture, refutes the claim that this path works.
  Checked the next time Josh runs it and reports the terminal output.

---

## 2026-09-19 (second entry) — RWKV state apparatus: verification + harness

**Checked**
- llama.cpp source at commit `e613ef2` (cloned, dated 2026-09-19):
  `llm_arch_is_recurrent()` in `src/llama-arch.cpp` lists `LLM_ARCH_RWKV7`;
  `src/llama-memory-recurrent.cpp::state_write_data` writes per-layer `r_l`,
  `s_l`, and PLE conv `p_l` tensors; `llama_state_seq_save_file` /
  `llama_state_seq_load_file` exported in `include/llama.h`; server route
  `POST /slots/:id_slot` with `--slot-save-path` in `tools/server/server.cpp:288`.
- llama-cpp-python 0.3.35 installed here; inspected `Llama.__init__` kwargs,
  `eval()`, `save_state()`, `load_state()`, and the ctypes signatures of
  `llama_state_save_file` / `llama_state_load_file`.
- Ledger core zip: README, `Llm/demo.py`, Regime Identity Contract v0.1,
  Reading Check Loop v0.1.

**Found**
- The state interface exists one layer below Ollama. RWKV7 routes to recurrent
  memory, and that memory serializes the actual state tensors to disk; restore
  sets state directly rather than replaying tokens. This supports steps 1–3 of
  the apparatus sequence. Read from source only.
- A real bug in my own first draft, caught before it could produce a fake result:
  with `logits_all=False` (the default), llama-cpp-python's `eval()` does not
  populate `llm.scores` — the branch is a literal `pass`. Reading scores there
  returns zeros, making D = 0.0 for every probe. That would have rendered a
  uniform FAIL that looked like a finding about the model and was a finding about
  my function. Fixed to read `_ctx.get_logits()`, plus a loud guard that raises
  on all-zero logits instead of emitting a confident 0.0.
- Two further attribute errors in the draft: `_input_ids` is `input_ids` in
  0.3.35, and `Llama.metadata` is an instance attribute, not a class one.
- Built `rwkv-state-probe/state_probe.py`: declare / run / restart, with the
  precommitment hash committed to the ledger before any number is produced,
  and `restart` refusing to run without a tolerance derived from the jitter
  calibration.

**Failed**
- **Nothing was executed against a real model.** HuggingFace is blocked by this
  container's egress policy, so no RWKV weights were reachable. The harness is
  syntax-checked and API-verified, never run. Its first run on the Mac is also
  its first test, and the most likely outcome of a first run is that it breaks.
- The llama.cpp slot save/restore test in-repo (`tools/server/tests/unit/
  test_slot_save.py`) uses tinyllama2, a transformer. I found no RWKV-specific
  state save/restore test. The recurrent path is implemented; I cannot show it
  is exercised in CI.
- Earlier in this session I recommended a ledger catch-up loader as the default
  build and filed state persistence as the unverified alternative. For the test
  actually being run that ranking was backwards, and the corpus rule that should
  have caught it is Josh's own: an instrument that is also part of the build is
  contaminated. Superseded by the apparatus-test framing, 2026-09-19.
- Probe-memory attribution is specified but not implemented as a single pass.
  A restored-vs-fresh divergence cannot yet be attributed to the state rather
  than the runtime's prefix handling.
- Steps 4 (return corrects state) and 5 (continuity vs. no continuity) are not
  built and are not claimed.

**Would kill it**
- `floor` failing — the probe cannot see `KOR = 7319` injected into state — kills
  the claim that this instrument can detect retained state at all, and no amount
  of changing the probe string afterward repairs it; that would be selection.
  Checked on Josh's first run.
- `restart` diverging beyond the jitter-derived tolerance kills the claim that
  state survives process death. Checked on the same run.
- If `causality` passes but the same D-shift appears on the unrelated query at
  comparable magnitude, the probe is reading general drift rather than the
  relation, and the specificity gate is what catches it.

## 2026-09-19 (third entry) — apparatus constants hardened before first declaration

**Checked**
- `run_jitter` as shipped: it returned `spread = max(vals) - min(vals)`, an
  observed range, while `noise_k = 3.0` was documented as though it were a
  sigma multiple.
- The zero-spread case: llama.cpp CPU inference at fixed thread and batch count
  is expected to be deterministic for an identical state and identical token
  list, which makes `range == 0.0` a likely rather than exotic outcome.
- The probe/tokenizer assumption: whether `KOR = ` is a token prefix of
  `KOR = 7319`, and whether the first token of `7319` is the declared candidate.

**Found**
- `noise_k × range` is a conservative policy multiple with no statistical
  interpretation. Recorded as such; `spread_stdev` now also reported so a later
  declaration can adopt a sigma rule with provenance.
- A hole in the fix committed one step earlier: with a deterministic runtime,
  `range == 0.0` makes `required_margin == 0.0`, which reinstates exactly the
  pass-on-noise failure the noise floor was added to prevent. Added
  `min_margin_abs = 0.5` logits and `required_margin = max(noise_k*range,
  min_margin_abs)`, with every result recording which term was binding.
- `jitter_n = 20` frozen in the declaration.
- Added a declare-time alignment gate: `declare` refuses to write a declaration
  unless the query is a genuine token prefix of query+value and the first value
  token is the declared candidate.

**Failed**
- My previous entry described the noise-floor fix without noticing that its own
  threshold degenerates to zero on a deterministic runtime. The fix was
  incomplete when committed and is superseded here, 2026-09-19. The general
  pattern is the one Josh's CD Gradient §4.1 names: a constraint discharged at
  the layer it was written and not against the quantity derived from it. That is
  now three times in this session.
- `min_margin_abs = 0.5` is arbitrary. It has no basis beyond being a round
  number in logit units, and when it binds, the gate rests on it rather than on
  anything measured.
- Still nothing executed against a real model. Still no probe-memory attribution
  as a single pass. Steps 4 and 5 still not built.

**Would kill it**
- Jitter returning `range == 0.0` AND floor passing only via `min_margin_abs`
  would mean the first qualification rests entirely on an arbitrary constant, and
  the apparatus should not be called qualified on that basis. Checked on the
  first run.
- The declare-time alignment gate refusing `KOR = 7319` would disqualify the
  probe before any experiment, and Declaration 2 would need different candidates.
  Checked on the first run.

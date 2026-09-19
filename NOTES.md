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

## 2026-09-19 (fourth entry) — first declared run aborted before any gate

**Checked**
- Josh ran `declare` from frozen commit `3e18e8d` against the real GGUF on his
  Mac. It raised `ValueError: Failed to create llama_context`. `run` and
  `restart` were not executed. No declaration file was written.
- The path of that error in the harness: `Engine.__init__` constructed
  `Llama(..., verbose=False)`.

**Found**
- No gate failed. No probe was disqualified. Nothing whatsoever was established
  about RWKV state retention. The run aborted before the declaration existed,
  so there is no Declaration 1 to supersede and no Declaration 2 is owed.
- The harness suppressed the diagnostic that names the cause. llama.cpp writes
  its reason to stderr and llama-cpp-python then raises a bare `ValueError`;
  with `verbose=False` the reason is discarded and only the causeless message
  survives. This is the second time in this session that I built a measurement
  path whose failure channel was dead — the first was `llm.scores` returning
  zeros.
- Repaired: context creation now re-runs with llama.cpp logging on when it
  fails, prints the output, and re-raises with the configuration named. Added a
  `doctor` subcommand that sweeps context configurations with logging enabled.

**Failed**
- I set `n_ctx=512` as a non-default value earlier in this session to keep logit
  buffers small. That is a prime suspect precisely because I introduced it, and
  I have no evidence either way — I still cannot run any of this, so the repair
  above is again unverified against a real model.
- I cannot read the raw output or the verification archive Josh linked: they are
  paths on his Mac and this session has no access to that filesystem. The
  diagnosis above rests on the one-line error text alone.
- Root cause is not established. Candidates not yet separated: the non-default
  n_ctx, a batch/ubatch constraint specific to recurrent architectures, this
  build of llama.cpp being unable to load this rwkv7 GGUF at all, or memory.
  `doctor` is the discriminating probe and has not been run.

**Would kill it**
- `doctor` finding a working configuration would show the fault was my
  non-default context sizing, and the apparatus proceeds unchanged.
- `doctor` failing at every configuration with a load error naming rwkv7 would
  mean this llama.cpp build cannot load this model, which is a finding about the
  runtime and not about state retention — and would kill the plan of using this
  binding for the battery at all.
- Checked on Josh's next run.

## 2026-09-19 (fifth entry) — separation of instrument/diagnostics/results; hygiene defect

**Checked**
- Git object state: `3e18e8d` exists and is unchanged; branch head has since
  moved to `8708201`. `git ls-files` on the frozen commit shows
  `rwkv-state-probe/__pycache__/state_probe.cpython-311.pyc` as a tracked file.

**Found**
- Decision made by Josh, recorded rather than re-derived: the frozen instrument
  is preserved by commit identity, not by holding the branch head still. Three
  layers stay explicitly separate — instrument = checkout `3e18e8d`;
  diagnostics = current branch; results = external run record and ledger.
  `60fcfd1` is not reverted.
- Hygiene defect, recorded as such at Josh's instruction: a compiled `.pyc` of
  the harness is carried inside `3e18e8d`, swept in by an earlier `git add -A`
  of mine. It does not invalidate the declaration attempt — CPython validates a
  `.pyc` against its source before use — and the historical commit is left
  untouched. Untracked going forward, with `.gitignore` added for build and run
  outputs.

**Failed**
- The defect is mine and was avoidable: `git add -A` on a directory I had just
  run `py_compile` in. It put a build artifact inside the one commit whose
  entire purpose is to be a fixed reference.
- `.gitignore` was added only after four commits had already been made, so any
  run output produced before now could have been swept into the source tree the
  same way. None was, but that was luck rather than design.
- The diagnostic has not been run. I cannot run it: it needs the model file and
  a Mac, and this session is a Linux container with no access to either. Nothing
  new is established about the context-creation failure.

**Would kill it**
- If a future checkout of `3e18e8d` behaves differently from what the runbook
  describes, the `.pyc` would become a real provenance problem rather than a
  cosmetic one, and the frozen commit could no longer be treated as a clean
  reference. Checked whenever `3e18e8d` is next checked out and run.

## 2026-09-19 (sixth entry) — context-creation cause identified: Metal init, not a parameter

**Checked**
- Josh's Trial 1 stderr: `ggml_metal_init: picking default device: (null)` ->
  `failed to create command queue` -> `ggml_backend_metal_device_init_backend:
  error: failed to allocate context` -> `llama_init_from_model: failed to
  initialize the context: failed to initialize backend`.
- Preflight recorded: Python 3.9.6, arm64, llama_cpp 0.3.35, probe-venv.
- llama.cpp source at `e613ef2`: `src/llama-context.cpp` lines 331-338 loop over
  `model.devices` calling `ggml_backend_dev_init` and throw on null, with no
  `n_gpu_layers` condition; `src/llama.cpp` `llama_prepare_model_devices` fills
  `model->devices` from enumerated GPUs, also without consulting `n_gpu_layers`.
- `inspect.signature(Llama.__init__)` in 0.3.35: exposes `n_gpu_layers`,
  `split_mode`, `main_gpu`, `tensor_split`. Does not expose `devices`.

**Found**
- `n_gpu_layers=0` governs layer offload only. It does not prevent Metal being
  enumerated or its backend being initialized, and a failed Metal init is fatal
  to context creation regardless. Josh identified this from the log before I
  verified it at source.
- The failure is Metal device acquisition returning null on a machine that has a
  GPU. That points at the process lacking access to the GPU / logged-in GUI
  session rather than at the model, the build, or any harness parameter.
- `n_ctx_seq (512) < n_ctx_train (1048576)` is an informational warning, not the
  failure. My non-default `n_ctx=512` is cleared as the cause.
- llama.cpp honours an explicit `params.devices` list, but llama-cpp-python
  0.3.35 never sets it, so there is no Python-level way to avoid Metal init.

**Failed**
- My Trial 1 was labelled "CPU-only" and was not CPU-only. `n_gpu_layers=0` does
  not produce a CPU-only run in this llama.cpp, so the trial did not test the
  category it claimed, and the protocol's "CPU-only FAIL -> stop" branch fired on
  a verdict that had no such meaning. Fourth instance this session of my
  apparatus reporting a category it had not established. The previous three:
  `llm.scores` returning zeros, `verbose=False` eating the diagnostic, and
  running trial 1 after an import error and calling it a failure.
- Root cause is still not isolated: session context (no GUI/window-server
  access) versus Metal genuinely unavailable on this machine has not been
  separated. The discriminating probe -- identical command from a
  user-opened Terminal window -- has not been run.
- Nothing established about RWKV state retention. No gate has run. No
  declaration exists.

**Would kill it**
- Metal initializing in a user-opened Terminal window would establish the fault
  as session context and clear the build, the model and my parameters entirely.
- `(null)` again in that window would mean Metal is unavailable to this runtime
  on this machine, and the only remaining route is a build with Metal compiled
  out -- a version change, which is Josh's decision, not mine.
- Checked on Josh's next run.

## 2026-09-19 (seventh entry) — Metal denial localized to the Codex seatbelt sandbox

**Checked**
- Direct `MTLCreateSystemDefaultDevice()` via ctypes from `probe-venv/bin/python`,
  with no llama.cpp and no model loaded: returned `None`.
- Same call from `/usr/bin/python3`: also `None`. No third interpreter present.
- `system_profiler SPDisplaysDataType`: Apple M4 Pro, 20 GPU cores, Metal:
  Supported.
- Environment of the failing runner: `CODEX_SANDBOX=seatbelt`,
  `CODEX_SANDBOX_NETWORK_DISABLED=1`, `XPC_SERVICE_NAME=0`. `ps` is blocked
  ("operation not permitted"), so process ancestry could not be walked.
- Earlier: `launchctl managername` returned `Aqua`, `SSH_TTY=none`.

**Found**
- The failure is reproducible in six lines with neither llama.cpp nor the model
  present. It is process-environment denial of a Metal device, not a property of
  the model file, the llama.cpp build, the frozen harness, or any parameter I
  chose. Every apparatus-side suspicion I raised across this session is
  excluded by this result.
- The hardware is fully Metal-capable, so "Metal unavailable on this machine" is
  dead as a hypothesis.
- Two different interpreters inside the same sandbox both get `None`, which
  weakens the interpreter hypothesis — the denial is not binary-specific.
- Both remaining routes converge on one dependency: a shell outside the sandbox.
  Confirming the cause needs it, and so does a Metal-free rebuild, because
  `pip` cannot reach the network with `CODEX_SANDBOX_NETWORK_DISABLED=1`.

**Failed**
- The sandbox is a strong candidate, not an established cause. The
  discriminating test — the same call from outside the sandbox — has not run,
  because the available tooling cannot open an unsandboxed shell. Recording it
  as "localized to the sandboxed process" rather than "caused by the sandbox".
- Probe 4 was presented by me as testing the interpreter hypothesis. It did not:
  both interpreters ran inside the same sandbox, so it could only show the
  denial is not binary-specific. The hypothesis remains untested independently.
- `launchctl managername` returning `Aqua` was, in hindsight, weak evidence I
  proposed as a discriminator. It reports the launchd domain, which a seatbelt
  sandbox does not change. The probe could not have distinguished the cases I
  claimed it would.
- Still nothing established about RWKV state retention. No gate has run. No
  declaration exists. Six sessions of apparatus work, zero returns from the
  instrument.

**Would kill it**
- The same ctypes call returning a non-null device outside the sandbox would
  establish the sandbox as the cause and clear everything else.
- It returning `None` outside the sandbox too would mean the cause is something
  else entirely on this machine, and the diagnosis restarts.
- Checked when an unsandboxed shell is available.

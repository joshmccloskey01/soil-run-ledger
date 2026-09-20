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

## 2026-09-19 (eighth entry) — four overclaims in the previous entry, corrected

The seventh entry stands as written. These are supersessions, dated 2026-09-19,
not edits to it.

**Checked**
- Josh's review of the seventh entry against the actual probe results.
- `probe-venv` is built from Python 3.9.6, which is `/usr/bin/python3` on this
  machine.

**Found (corrections to the seventh entry)**
1. "Every process inside that sandbox gets no Metal device" — superseded. Two
   processes were tested. "Every" was not established and is withdrawn.
2. "Two different interpreters ... the denial is not binary-specific" —
   superseded. The venv and `/usr/bin/python3` are the same underlying binary,
   so that probe ran one binary twice and established nothing about
   binary-specificity. This is the second correction to the same probe: I first
   said it tested the interpreter hypothesis, corrected that to "shows the
   denial is not binary-specific", and that is now also wrong.
3. "Both remaining routes converge on one dependency: a shell outside the
   sandbox" — superseded, and this one changed a decision. Network permission
   had already been granted inside the sandbox for downloads;
   `CODEX_SANDBOX_NETWORK_DISABLED=1` describes a state that can be changed
   without leaving the sandbox. A Metal-free rebuild is therefore available
   in place and does not require Terminal. The two routes are independent.
4. "Nothing about the model, llama.cpp or the harness is implicated ... that
   whole line of inquiry is closed" — superseded. Reproducing nil without them
   shows they were not needed to cause this failure. Their behaviour once Metal
   is out of the way is untested, not cleared.

**Failed**
- Every one of these was an overclaim by me, and Josh caught all four. The
  pattern across them is uniform: I stated a conclusion at a scope the evidence
  did not reach. That is the same defect as the earlier apparatus failures, in
  prose rather than in code — a verdict emitted without establishing the
  category it names.
- Correction 3 is the costly one. It made a rebuild look blocked on tooling Josh
  does not have, when it was available the whole time.
- New risk identified, not yet checked: `ps` returns "operation not permitted"
  in this sandbox. The restart gate spawns a subprocess and passes state through
  a file on disk. If either is restricted, that gate fails environmentally and
  would produce exactly the kind of causeless verdict this session has already
  produced four times.

**Would kill it**
- Subprocess spawn or file write failing inside the sandbox would mean the
  restart gate cannot run there at all, regardless of Metal, and the rebuild
  would not have unblocked the experiment.
- Checked on the next run of the capability probe.

## 2026-09-19 (ninth entry) — first declaration attempt REFUSED at probe qualification

**Checked**
- Context-creation diagnosis re-run in Terminal.app, same interpreter
  (probe-venv, Python 3.9.6, arm64), same llama-cpp-python 0.3.35:
  Trial 1 (`n_gpu_layers=0`) PASS 6.9s; Trial 2 (frozen settings) PASS 0.4s.
  Trial 3f not reached because Trial 2 passed.
- Direct `MTLCreateSystemDefaultDevice()`, same interpreter: `None` inside the
  Codex seatbelt runner, pointer `4773274624` in Terminal.app.
- Frozen commit `3e18e8d` `state_probe.py declare` run against the real model
  with `--ledger "/Users/joshuamccloskey/Downloads/ledger core 2"`.

**Found**
- The Metal denial is established as specific to the sandboxed runner, by the
  discriminating comparison that was missing before: identical interpreter,
  identical versions, device present in one context and absent in the other.
  No rebuild, no version change, no harness repair was needed for
  initialization. The earlier n_ctx/n_batch suspicion is fully closed —
  Trial 2 used exactly the frozen settings and passed in 0.4s.
- **`declare` REFUSED. No declaration was created.** The probe/tokenizer
  alignment gate failed on both values:
    query "KOR = "     -> [1179, 83, 296, 33]
    "KOR = 7319"       -> [1179, 83, 296, 3546, 639]
    "KOR = 4412"       -> [1179, 83, 296, 3517, 632]
  The first three tokens match; the query's trailing space (token 33) is then
  absorbed, merging with the digits into a single token. The query is therefore
  not a token prefix of query+value, and the declared candidates (`7`, `4`) are
  tokens the model was never going to emit at that position.
- This is the apparatus working. The gate ran before any experiment, refused to
  write a declaration, and printed the real tokenization. Had it not existed,
  D would have compared two never-emitted tokens and returned clean numbers for
  every gate.

**Failed**
- The probe design is disqualified. `KOR = 7319` / `KOR = 4412` with candidates
  `7` and `4` cannot serve as the discriminator against this tokenizer. My
  prediction three entries ago was that `floor` would fail on recall; it failed
  earlier than that, on tokenization, which I had assumed away.
- Structural defect in the instrument, relevant to the revision Josh will
  review: the probe strings and candidates are hardcoded inside
  `build_declaration()` in `state_probe.py`. Probes are code, not declared
  input. Any probe revision therefore changes the instrument itself, so
  `3e18e8d` cannot carry a corrected probe and remain the same object. This
  was avoidable and is my design error.
- Still nothing established about RWKV state retention. No gate has run. The
  instrument has now been through nine entries and produced one refusal and
  zero measurements.

**Would kill it**
- A revised probe whose query is a genuine token prefix of query+value, and
  whose two state values yield distinct first tokens, would clear
  qualification. Selection among candidate designs must be on tokenization
  alignment only — never on whether the model answers correctly, which would be
  outcome selection.
- If no probe design satisfies alignment with distinct first tokens against this
  tokenizer, the single-token-margin discriminator is unusable for this model
  and D needs redefining.
- Checked when the revised probe is separately reviewed.

## 2026-09-19 (tenth entry) — probes moved to declared input (revision for review)

**Checked**
- `git diff 3e18e8d HEAD -- state_probe.py` before starting: the only drift was
  Engine construction verbosity and the `doctor` subcommand. No measurement,
  threshold, gate or alignment line differed. Confirmed again after the change.
- `load_probes` against three files: valid, internally inconsistent (state_A not
  containing query+value), and missing keys. Refused the latter two.
- `declare --help`: `--probes` is now required.

**Found**
- Probe strings and candidate tokens are now a reviewed file hashed into the
  declaration (`probe_file_sha256`, `probe_set_id`), not code. A probe revision
  no longer touches measurement.
- The alignment gate is unchanged in logic; it now reads `value_A`/`value_B`
  from the file instead of the literals `"7319"`/`"4412"`. Candidates remain
  explicit in the file rather than derived, so the gate's second condition
  still checks something: a hand-edited file is caught.
- Added `load_probes` consistency check not present in `3e18e8d`: the state text
  must contain `query + value`, otherwise the gate would validate a boundary the
  state never builds.
- `qualify_probes.py` loads with `vocab_only=True`. No context is created and no
  logit can be read, so selecting a probe by model performance is unavailable
  rather than merely prohibited. It checks prefix, first-token presence,
  detokenize/retokenize round trip, and candidate distinctness.

**Failed**
- Nothing here is verified against the model. `qualify_probes.py` has never run
  against real weights; I still cannot run any of it. Whether design B
  (trailing space moved into the value) actually clears alignment is unknown —
  it is a candidate to validate, exactly as Josh stated, and I have not
  validated it.
- The round-trip check is new and untested. If `detokenize(first_token)` does
  not re-tokenize to a single token for leading-space tokens in this
  tokenizer, designs will fail qualification for a reason that is about my
  check rather than about the probe. I do not know which way that goes.
- `3e18e8d` remains the instrument of record for the refusal. This revision has
  produced no declaration and no measurement.

**Would kill it**
- No candidate design passing alignment would mean the single-token-margin
  discriminator is unusable against this tokenizer and D needs redefining.
  `qualify_probes.py` prints that conclusion rather than inviting more designs.
- Design A (the disqualified one) passing under the new tool would mean the
  tools disagree, and the new one would be wrong until reconciled. It is
  retained in the design list for exactly that reason.
- Checked when Josh runs qualification.

## 2026-09-19 (eleventh entry) — two review findings confirmed and fixed

**Checked**
- `llama_cpp/llama.py` in the installed 0.3.35: line 246 sets
  `self.model_params.vocab_only = vocab_only`; line 413 constructs
  `internals.LlamaContext(...)` with no guard on it.
- `_internals.LlamaModel.__init__(path_model, params, verbose)` — no context
  reference anywhere in its construction path; exposes `tokenize`,
  `detokenize`, `token_to_piece`, `n_vocab`.
- My own `build_declaration` alignment loop at line 446: iterates only over
  `state_A` and `state_B`.

**Found**
- Josh's finding 1 is correct. `Llama(vocab_only=True)` creates a context. The
  "no context is created, no forward pass is possible" guarantee in the
  qualifier's docstring was false as written. Fixed by loading through
  `_internals.LlamaModel`, which never calls `llama_init_from_model`. A comment
  now warns against "simplifying" it back to the high-level constructor.
- Josh's finding 2 is correct. The alignment gate covered only the two relation
  values. An edited probe file could carry unrelated candidates that are
  distinct single tokens — passing `single_token_id` — without being the first
  token of their declared values, and the specificity gate would then compare
  tokens the model would never emit. That is the gate meant to detect spurious
  drift, so the failure would have been silent and in the worst place. Extended
  to all four pairs, using the existing `verify_alignment` unchanged.
- Round-trip failures are now labelled in the output as representation failures
  of the string-based candidate interface, explicitly not evidence about state
  retention.

**Failed**
- The false guarantee is the more serious of the two. I did not merely fail to
  prevent context creation; I wrote a docstring asserting it was structurally
  impossible, and committed that claim. It would also have made the qualifier
  fail inside the sandboxed runner for the same Metal reason as everything
  else, which would have looked like a probe problem.
- Both findings came from Josh reading source. Neither was caught by me, and I
  had verified the wrong things: I checked that `vocab_only` was an accepted
  kwarg and stopped there, without checking what it actually gated.
- The extension to four pairs is a change beyond "gate unchanged". It is the
  explicit validation extension Josh sanctioned, but it is a change to the
  gate's coverage and is recorded as such rather than folded in silently.
- Still nothing run against real weights. `_internals.LlamaModel` usage is
  unverified in execution; its argument order and the `params.vocab_only` field
  were checked by signature inspection only.

**Would kill it**
- `_internals.LlamaModel` failing to load or tokenize would mean the qualifier
  has no working model-only path in this binding, and the guarantee would have
  to be met some other way or dropped honestly.
- The extended alignment gate rejecting a probe file that the qualifier emitted
  would mean the two tools disagree about alignment, and the declaration path
  would be wrong until reconciled.

## 2026-09-19 (twelfth entry) — tokenizer qualification results; known limitation logged pre-declaration

**Checked**
- `qualify_probes.py` at `bf6d017` run against the real model
  (sha256 f5a04a0a...31d8) on Josh's Mac, model-only load path.
- Six candidate designs, four query/value pairs each.

**Found**
- The reconciliation check passed. Design A fails on all four pairs and
  reproduces the original refusal's token arrays exactly
  (`[1179, 83, 296, 33]` vs `[1179, 83, 296, 3546, 639]`). The new tool agrees
  with the frozen gate on the one case whose answer was already known. This was
  the stated kill condition for the qualifier; it survived.
- The model-only load path works in execution, not just by signature
  inspection. `_internals.LlamaModel` is verified.
- Designs B, C, D, E, F pass alignment and round-trip. A fails.
- B is the only passing design whose state text is byte-identical to the frozen
  design: `query + value_A + "\n"` gives `"KOR = 7319\n"` for B, versus
  `"KOR: 7319\n"` (C), `"KOR=7319\n"` (D), `"KOR =\n7319\n"` (E),
  `"KOR = seven\n"` (F). B moves only the query boundary used at measurement
  time. Its candidates 3546/3517 are the same tokens that appeared at position
  3 in the original refusal.

**Failed / known limitation, logged before any declaration exists**
- Specificity confound in B, and in C, D and E: the unrelated probe runs with
  `state_A` loaded, and `state_A` contains the character `3` (inside `7319`)
  while containing no `8`. The unrelated candidates are `' 3'` and `' 8'`, so
  the two are not symmetric with respect to the state's content.
  Measured qualification: tokens 286 (`' 3'`) and 291 (`' 8'`) do NOT appear in
  `state_A`'s token sequence `[1179, 83, 296, 3546, 639, ...]`. The overlap is
  therefore character-level inside a merged token, not a token collision. This
  is weaker than I first stated it, and the correction is in my favour, which is
  a reason to be more careful about it rather than less.
  **Consequence to honour if it fires:** a specificity failure under this probe
  set is consistent with content overlap and cannot by itself be read as the
  state being non-specific. Digits absent from both values are 0, 5, 6, 8, so
  `' 8'`/`' 5'` would remove the asymmetry in a later probe set.
- Nothing here tests whether the model will emit these tokens. Qualification
  establishes the discriminator compares emittable tokens, nothing more.
- No probe emitted, no declaration, no gate run.

**Would kill it**
- The specificity gate failing while floor and causality pass would make this
  logged confound the first thing to check, and a probe set with `' 8'`/`' 5'`
  the discriminating follow-up.
- The alignment gate in `state_probe.py` rejecting the probe file that
  `qualify_probes.py` emits would mean the two tools disagree despite agreeing
  on design A, and the declaration path is wrong until reconciled.

## 2026-09-19 (thirteenth entry) — qualifier/gate disagreement risk closed by construction

**Checked**
- `llama_cpp/llama.py:618`: `Llama.tokenize` returns
  `self.tokenizer_.tokenize(text, add_bos, special)`.
- `llama.py:397`: `self.tokenizer_ = tokenizer or LlamaTokenizer(self)`.
- `llama_tokenizer.py`: `LlamaTokenizer.__init__` sets
  `self._model = llama._model`; its `tokenize`/`detokenize` delegate straight
  to `self._model.tokenize` / `self._model.detokenize`.
- `llama._model` is an `internals.LlamaModel` — the same class
  `qualify_probes.py` loads directly.

**Found**
- The stated kill condition "the alignment gate rejects a probe file the
  qualifier emitted, meaning the two tools disagree" cannot occur through
  tokenization. Both paths call the identical `LlamaModel.tokenize` with
  identical arguments (`add_bos=False, special=False`). Josh's cross-check
  agreeing was not evidence of luck; disagreement was structurally impossible.
- His caveat that he exercised the alignment function through the
  tokenizer-only interface rather than through `Engine` does not leave a gap:
  `Engine.tok` and `single_token_id` route to the same call.

**Failed**
- I raised that risk as a live possible outcome of the next step. It was not
  live, and five minutes reading `llama_tokenizer.py` would have shown that
  before I raised it. Raising a false risk is cheaper than missing a real one
  but it is still a claim made at a scope the evidence did not reach — the same
  defect as the supersessions in the eighth entry.
- The emitted probe file cannot be independently hash-verified by me:
  `build_probe_file` writes `qualified_utc` from the clock, so the digest is
  not reproducible from the qualification output. Contents can be checked;
  the hash cannot. Taking the timestamp out of the hashed body would fix that
  and has not been done.
- The probe file itself has not been reviewed — it exists only as a path on
  Josh's machine, which this session cannot read.
- No declaration, no ledger write, no context, no forward pass. Floor gate
  still unrun.

**Would kill it**
- The remaining real risk is representational, not logical: leading spaces in
  `correct_str` (`" 73"`) and `wrong_str` (`" 44"`) are load-bearing and are the
  most likely thing to be silently lost in a copy or an editor. If they are
  lost, the candidates become different tokens and the gate will refuse — which
  would be a file-integrity failure, not a probe failure, and must be recorded
  as such.

## 2026-09-20 — declaration path reordered; failure paths tested before review

**Checked**
- Probe file `880f9fd1...f854` verified independently: reconstructed from Josh's
  paste and hashed to the same digest; round-trips byte-identical through
  `json.dumps(indent=2, sort_keys=True)`; 775 bytes, LF only, one trailing
  newline; all eight leading spaces intact; `state_A`/`state_B` byte-identical
  to the frozen design; `load_probes` accepts it.
- `cmd_declare` ordering in the previous revision: `declaration.json` was
  written before `Ledger(...)` was even constructed.
- Six failure paths executed, no model loaded, ledger faked
  (`test_persist_declaration.py`).

**Found**
- The ledger binding had never executed once. The earlier attempt died at the
  alignment gate, which precedes it. So `create_ledger`, the genesis import and
  the chain write were all unexercised, and about to run for the first time.
- Reordered: ledger constructed and checked FIRST, before the model loads;
  `--ledger` now refused if absent; declaration written to a `.pending` file and
  fsynced, then the FULL declaration body committed to the chain, then published
  by atomic rename.
- Committing the full body rather than only the hashes makes the chain by itself
  sufficient to recover a declaration, which is what closes Josh's requirement
  that a commit-then-write-failure stay recoverable.
- Tested: happy path publishes and clears `.pending`; commit raising and commit
  returning None both remove `.pending`, write nothing and refuse; rename failing
  after commit preserves `.pending`, reports the event id, prints the `mv`
  recovery command and warns against re-running declare; both `cmd_declare`
  refusals exit 3 without writing anything and without loading the model.
- Measurement functions, thresholds, gates and probes verified unchanged against
  `3e18e8d` after the edit.

**Failed**
- This bug was mine and it was the worst kind available in this project: an
  apparatus that produces an uncommitted declaration while exiting 0. The whole
  point of the precommitment is that the claim cannot be altered after the
  measurement, and the previous ordering silently permitted exactly that. It
  survived my own review of the revision two entries ago; I found it only when
  reading the declare path a third time.
- `--ledger` defaulting to `None` meant a mistyped or omitted flag produced the
  same silent outcome. That default was mine as well.
- The `.pending` path and atomic rename are tested against a faked ledger only.
  The real `genesis`/`storage`/`append` binding still has never run, so a
  first-contact failure there remains possible — it would now refuse rather than
  exit 0, which is the point, but it is untested against the real ledger core.
- No declaration exists. No gate has run. Nothing is established about state
  retention.

**Would kill it**
- The real ledger core failing at `create_ledger` or import would now produce
  exit 3 with a reason, and that reason is the next thing to diagnose. It would
  be a ledger-binding finding, not a probe or state-retention result.
- A `COMMITTED BUT NOT PUBLISHED` outcome would mean the chain holds a
  declaration the filesystem does not; the recovery is the printed `mv`, and
  re-running declare would wrongly commit a second declaration.

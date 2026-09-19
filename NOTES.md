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

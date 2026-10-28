# NOTES

## 2026-10-18

**Checked**
- Folder listing. No `NOTES.md` existed before this entry; this file starts here.
- `ROPEU_Core_Corpus_v1_1.md` (402 lines), searched for persist / adaptive / earth / ground / logic. Read the closing summary (line 402), the memory definition (line 313), and the logic section (lines 123–142).
- No training data, ledger, or zip contents opened this session.

**Found**
- Josh stated, informally: we're made of logic; the goal is to do logic; the premise "do you want to persist?" is the ground wire; the best target you can't see past is adaptive Earth.
- Against the corpus: "the controller is inside reality" (line 402) and "verification closes only the part of the loop that adequate coupling can reach" match "a target you can't see past." "The controller adapts as well as learns" matches "adaptive."
- One conflict with the corpus wording: the corpus treats logic as what governs valid movement through the loop (line 125), not what the controller is made of. Recorded as a wording conflict, not a resolved disagreement.

**Failed**
- No data was examined; nothing here is a finding about training.
- As stated, "adaptive Earth is the target you can't see past" is close to the corpus definition of reality, so it may be true by definition rather than testable. I could not name a clean refuting observation for the general statement.
- "Persist" is ambiguous between persistence of the organism/coupling and persistence of the current model. The second reading conflicts with "do not build a case." Not settled this session.

**Would kill it**
- Narrow, testable version only (Claude's proposal, not Josh's claim): if the persistence premise maps to "owned progress," then a floor that rises only while effort is being spent to hold it, and falls back within ~3 weeks of ordinary training, refutes "owned" for that block. Check at the next block review against the floor readout; no date set by Josh.

### 2026-10-18, addendum (same session)

**Checked**
- Josh's clarification: "made of logic because a computer is a logic gate."

**Found**
- At the hardware level a computer is built from logic gates, so for a computer "made of logic" is literal. The gates are physical: matter arranged so that its state switches according to a rule.

**Failed**
- Claude was wrong in the entry above to record "made of logic" as a conflict with the corpus. Superseded on 2026-10-18 by this clarification. The original line stays as it was written.
- Still open: what the tripod, ground wire and adapter boards physically do in the build. The "ground wire" reading in the entry above is unconfirmed.

**Would kill it**
- No new claim added.

### 2026-10-18, addendum 2 — Experiment 1

**Checked**
- Wrote `experiments/exp1/PREREGISTRATION.md` (predictions, frozen items, definitions), committed in 6d15926 before any model was run.
- Wrote `experiments/exp1/run_exp1.py`. Ran its self-test on a 4-layer randomly initialized GPT-2-shaped model: the rank-one edit, the transposed weight layout, the injection hook and the least-squares fit all reproduce the requested change to within a relative error of about 2e-7.

**Found**
- The code's arithmetic does what the protocol says. That is a check of the mechanics, not a result about learning. The random model has no knowledge to test.

**Failed**
- Experiment 1 was not executed. huggingface.co is refused by this environment's network policy, so the GPT-2 weights and the WikiText regression set cannot be downloaded. No GPT-2 numbers exist.
- The ledger event types the protocol names (edge_candidate, probe_nomination, probe_return, retention_check) do not appear anywhere in this folder's ledger code or documents. The ledger core accepts any event_type string, so the names can be used, but nothing here defines their schema.

**Would kill it**
- No claim added. The six predictions stand open in the preregistration; they get settled on the first run.

## 2026-10-20

**Checked**
- Four documents Josh uploaded, read in full: Convergence Map round 1 (21 links, 77 rows), round 2 (74 rows), "Re-Walked" (C loop C1–C10 plus the 21 links), and a ChatGPT rescoring against a 19-link version dated 19 Oct 2026. The 19-link text itself was not among the uploads.
- None of the cited primary sources were opened by Claude. Every source claim below is the documents' claim, not something Claude checked.

**Found**
- "Ground wire" is the name of the whole chain, and link 4 of the 21-link version reads "Choosing to persist hooks up the ground wire." So the 18 Oct reading of the phrase matches the documents. The tripod and adapter boards appear in none of the four documents.
- Where Experiment 1 sits, in the documents' own terms: it tests only the write-back step, C7 (a link moves into the parallel loop) / L11–L13 (weights × state, a confirmed shortfall as the target, a step small enough to undo). The correction is supplied by hand, so C4–C6 (error on the error, finding the link, routing effort) are not tested. "Re-Walked" says Daw, Niv & Dayan 2005 explicitly leave this write-back step unmodelled.

**Failed**
- The rankings cannot be compared across documents. Friston is 2.5/21 (11.9%) in round 1 and 4.0/19 (21.1%) in the ChatGPT rescore, both called "strict." That is a different chain, a different rubric and a different scorer, so by the instrument rule these are not the same measurement. The ChatGPT document calls its result "materially stronger" by comparing across them.
- All scoring was done by one model per document, and the target chain was scored by Josh himself (21/21). No inter-rater agreement exists. The ChatGPT document says so in its last section and proposes blind coders; no blind coding has been done.
- The ChatGPT document contains 32 unresolved citation markers ("citeturn22view…"). Its sources cannot be traced from the file.
- The originality argument ("the best single predecessor covers 23.7%, the union covers 55.3%, and the gap is where the synthesis lives") has no control. Any long chain of clauses drawn from many fields, written by one person and scored against specialists, would likely show the same gap. As it stands, the metric cannot tell an original synthesis from an arbitrary concatenation.
- The packaging in the ChatGPT document ("unusually clear," "warrant taking the work seriously") runs hotter than its checks, which by its own account were a screening rescore for most rows.

**Would kill it** (Claude's proposal, not Josh's claim)
- Claim under test: the union-vs-best-single gap measures originality. Refutation: write a control chain of comparable length (for example Beer's Viable System Model, or a deliberately arbitrary 19-clause mix across fields), score it with the same rubric and a different scorer, and find that its best predecessor also covers under about 25%. Check date: not set. Josh decides whether to run it.

## 2026-10-28

**Checked**
- Josh's three physics problems, saved verbatim to `problems/quantum_three.md`. Checked against Claude's background knowledge only. No papers were fetched or opened this session.

**Found**
- All three are recognised open problems, stated accurately: (1) the measurement problem, (2) the probability problem in Many Worlds, (3) Penrose's gravity-and-superposition problem.
- (2) bundles two problems: what probability means when everything happens (the "incoherence" problem) and why the odds follow the Born rule. Attempted derivations exist (Deutsch–Wallace decision theory, Zurek's envariance, Sebens–Carroll self-locating uncertainty). They remain disputed.
- (3) Penrose (1996) proposed that a mass in two places collapses on its own, after a time set by the gravitational self-energy of the difference between the two positions (the Diósi–Penrose model).

**Failed**
- Wall on (3), from memory and not re-checked this session: an underground experiment at Gran Sasso (Donadi et al., *Nature Physics* 2021) looked for the faint radiation that the simplest, parameter-free Diósi–Penrose model predicts and ruled that version out. Versions with an added free parameter survive. Verify before citing.
- Wall on (1): decoherence explains why interference disappears for large objects. It does not pick out which single outcome occurs, so it does not close (1) on its own. Recorded so it doesn't get offered as a solution later.
- Conflict with the 18 Oct image ("massive things are the gates"): that picture takes a side on (1) and (3), namely that mass is where the record gets made. That is Penrose's side, and its simplest testable form is the one the Gran Sasso result constrains.

**Would kill it**
- No claim added by Josh. If the "mass is the gate" position gets written up as a claim, then a confirmed observation of a mass large enough to matter gravitationally held in superposition past the Diósi–Penrose time would refute it. Proposed tests of gravity-mediated entanglement (Bose et al. 2017; Marletto & Vedral 2017) are aimed at that regime. No date: those experiments have not been done.

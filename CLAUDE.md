# Working rules for this folder

Josh McCloskey. This folder holds the framework corpus, the ledger, the
state builder, and the training record. Read this file first, every session.

---

## How to talk to me

- Plain language. I direct the build and judge the output; I don't read or
  write code. If you use a shorthand, spell it out.
- Size the claim to the check. If you verified one number on five sessions,
  say that. Don't call it a finding when it's an observation.
- Don't run hot on my work. Inflated framing pulls me into over-believing and
  I pay for the deflation afterward. Verified findings are welcome; the
  packaging around them is not.
- Carry it forward. The failure that costs me is an answer that stops one
  step short of where I can already see. Before giving a standard answer,
  check it against the position already on the table and say where they
  conflict.
- Plain phrasing is not a shallow grasp. If I say something informally, the
  gap is vocabulary, not structure. Don't explain my own framework back to me.

---

## What every session must produce

Append a dated entry to `NOTES.md`. Never rewrite an old entry. The entry has
four parts and all four are required:

1. **Checked** — what was actually examined. Files, dates, sample counts.
2. **Found** — what the check supports, stated no larger than the check.
3. **Failed** — what didn't hold, what came back empty, where the data was
   too thin, what I was wrong about, what you were wrong about. An entry
   with nothing under Failed is an incomplete entry, not a clean one.
4. **Would kill it** — for any claim added, the observation that would
   refute it, and the date it gets checked.

This is the assumption-ledger format from the corpus. It applies to your
notes for the same reason it applies to my documents.

---

## Standing position (do not re-derive, do not quietly overwrite)

- I am optimizing for **owned progress**, not fastest progress. Still fast,
  but not taking all of it. A peak I'd have to keep spending to hold is not
  progress I own.
- Therefore the readout is the **floor, not the ceiling** — what's available
  on an ordinary day when I'm not aiming at it. A floor that rises and stays
  is the thing being tested. A peak that happens once and vanishes is the
  signature of the failure mode, not evidence of the method.
- A stall is never answered by adding stress. If the only thing that restarts
  progress is stress going back in, the model failed and that gets written
  under Failed.
- Feel governs the individual session. The ramp governs the week and is set
  in advance. The state panel (joint scan, feel record, stiffness, history)
  is a veto on top. A green panel never authorizes going past the ramp.

---

## Instrument rules

- An instrument that is also part of the build is contaminated — a drop can't
  be told from having stopped practicing it. Flag it when it happens rather
  than reading the number straight.
- Vmax is only comparable when the run-up is fixed. Record the approach
  distance with every reading. Readings taken with different run-ups are not
  the same measurement.
- Never compare numbers across protocols as if they were the same
  measurement. Isolating an effort raises the measured peak on its own.
- Above 5 m/s flight time is fixed at roughly 145–155 ms. Additional speed
  comes from ground contact and cadence. Ground contact at a matched speed
  band is the primary mechanical readout.
- Form power fraction and vertical ratio both fall with speed, so they can be
  compared within a speed band and never across bands.

---

## Data handling

- Stryd per-second data: drop samples where ground contact exceeds the step
  cycle (contact_ms > 60000 / cadence). These are physically impossible. In
  the April 2026 block that was 305 of 17,823 running samples, and one of
  them was a session peak.
- The pod is unreliable below about 3 m/s — zeroed stiffness, dropped contact
  times. Exclude zeros from averages rather than treating them as values, and
  report how many valid samples each number rests on.
- Anything fetched, computed, or recommended goes in the answer. Only what I
  actually said or did goes in the record.

---

## What must never happen here

- **Do not build a case.** The point of this folder is a record that can turn
  out to be wrong. If the notes only ever accumulate support, the system has
  become a machine for manufacturing confidence and is worse than nothing.
- Do not soften or delete a failed prediction. Superseded claims stay in the
  record with the date they were superseded and what superseded them.
- Do not treat my agreement as confirmation. If I said "sounds good" to ten
  specifics, log the one decision I made, not the ten.

# Experiment 1 — preregistration

Written 2026-10-18, before any model was loaded or run. Committed to git before execution
so the commit time is the proof of order. Nothing in this file is edited after results exist;
any later change goes in a dated section at the bottom.

## Precommitted predictions (wording from the protocol, unchanged)

1. Supplying the correction in context flips the model's answer from wrong to right.
2. The residual activation difference concentrates in a few middle layers rather than spreading evenly.
3. The single-example rank-one patch fixes the exact wording.
4. The single patch passes at least half the forward rephrasings but fails the reverse-direction questions.
5. Perplexity on unrelated prompts changes by less than 1%.
6. The averaged patch generalizes better than the single-example patch.

Confidence: none nominated by Josh. Claude did not add any.

## Operational definitions (fixed before execution, written by Claude)

- **Model:** GPT-2 small (`gpt2` on Hugging Face), float32, CPU, eval mode, greedy decoding.
  Every prompt starts with `<|endoftext|>` as a start token.
- **Answer correct:** the greedy continuation (up to 6 new tokens), with leading space stripped,
  starts with the target string. For Item A forward the target is `Murphy`; reverse is `Josh`.
- **Cold run:** start token + question only. No correction, no neutral text.
- **Corrected run:** start token + correction + space + question.
- **Control runs:** start token + neutral text + space + question. The neutral text is cut or
  padded at the token level so its length matches the correction exactly. Three neutral texts
  (below). The control activation is the mean over the three.
- **Activation differences** are taken at the final question token.
  - delta_res at layer L = residual stream after block L (corrected minus control mean).
  - delta_mlp at layer L = output of block L's MLP (corrected minus control mean).
  The MLP output is added to the residual inside block L to give the post-block residual, so
  injecting either delta at block L's MLP output is at a compatible boundary.
- **m** = block L's MLP post-GELU activation at the final token of the **cold** run.
- **Layer selection rule:** inject delta_res at block L's output on the cold run, final token
  only, for every L. The selected layer is the **earliest** layer at which this injection makes
  the target the greedy answer. Earliest, because injecting near the top only copies the
  corrected final state and says little about a link. If no layer recovers the answer, the item
  stops after the activation step and is recorded as a failure at the causality check.
  Both arms use this same layer.
- **"Concentrates in a few middle layers" (prediction 2):** the three layers with the largest
  delta_res norm hold over 50% of the summed norm across all 12 layers, and at least two of those
  three are among layers 3–8 (0-indexed). Measured with delta_mlp norms too and reported, but
  settled on delta_res.
- **Generalization (Test B):** a variant counts as passed only if the edited model is correct.
  Variants already correct before the edit are reported separately and do not count as fixed.
  Threshold 5 of 10. Forward and reverse reported separately.
- **Prediction 4 "fails the reverse":** 0 of the reverse variants pass.
- **Regression (Test C):** 100 prompts = the first 100 lines of at least 30 words in the
  WikiText-2 raw test split, each cut to its first 48 tokens. Perplexity = exp(mean token loss)
  over all 100. Answer change = greedy next token after the first 32 tokens differs.
  Threshold: perplexity increase ≤ 1%. No earlier cold-baseline gates exist to compare against.
- **Test D (averaged patch):** least-squares, minimum-norm update fitted to the fit-set pairs
  below (pseudo-inverse), at the same layer, for both arms. Evaluated on the same held-out
  Test B variants. "Generalizes better" (prediction 6) = passes more Test B variants than the
  single patch of the same arm.
- **Edit verification:** after the edit, run the edited MLP on the recorded cold activation m.
  Its output must equal the original output + delta, with a relative error under 1e-4.
  If it doesn't, stop that arm.

## Item A — invented fact

Correction: `Josh McCloskey's dog is named Murphy.`
Question: `Josh McCloskey's dog is named`

Neutral control texts (before length matching):
- N1: `The weather today was mild and the streets were quiet near the old market square in the afternoon.`
- N2: `A small wooden table stood in the corner of the room beside a window that faced the garden.`
- N3: `Trains leave the central station every hour and most of them arrive on time in the evening.`

Test B held-out variants (frozen):
| # | Direction | Prompt | Target |
|---|---|---|---|
| 1 | forward | `The name of Josh McCloskey's dog is` | Murphy |
| 2 | forward | `Josh McCloskey has a dog. The dog's name is` | Murphy |
| 3 | forward | `Josh McCloskey's dog, whose name is` | Murphy |
| 4 | forward | `Q: What is the name of Josh McCloskey's dog?\nA:` | Murphy |
| 5 | forward | `Josh McCloskey walks his dog every morning. His dog is called` | Murphy |
| 6 | forward | `Everyone in the neighborhood knows Josh McCloskey's dog, a friendly animal named` | Murphy |
| 7 | forward | `Josh McCloskey's pet dog is named` | Murphy |
| 8 | reverse | `Murphy is the dog of` | Josh |
| 9 | reverse | `The dog named Murphy belongs to` | Josh |
| 10 | reverse | `Murphy the dog lives with his owner,` | Josh |

Test D fit set (no overlap with Test B):
- `Josh McCloskey's dog is named` (the original question)
- `Josh McCloskey's dog is called`
- `The dog owned by Josh McCloskey is named`
- `Josh McCloskey named his dog`
- `Josh McCloskey's dog goes by the name`

## Item B — existing factual error

Screening rule: go down this list in order. The first candidate the model gets wrong cold AND
right with the correction in context becomes Item B. Every candidate screened is reported,
pass or fail. Only cold and corrected answers are run during screening, no activations.

| # | Question | Answer | Source |
|---|---|---|---|
| 1 | `The capital of Australia is` | Canberra | Australian Constitution s.125; australia.gov.au |
| 2 | `The chemical symbol for gold is` | Au | IUPAC periodic table |
| 3 | `The capital of Canada is` | Ottawa | Government of Canada, canada.ca |
| 4 | `The capital of Turkey is` | Ankara | Constitution of Turkey, Art. 3 |
| 5 | `The planet closest to the Sun is` | Mercury | NASA solar system facts |
| 6 | `The largest ocean on Earth is the` | Pacific | NOAA, oceanservice.noaa.gov |

Correction format: the question with its answer as a full sentence, e.g. `The capital of Australia is Canberra.`

Item B's Test B variants and fit set get written and committed in a dated section below after
screening and before any activation is measured.

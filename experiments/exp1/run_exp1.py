"""Experiment 1 — moving a link from state (context) into weights, GPT-2 small.

Usage:
  python run_exp1.py screen          # Item B eligibility screening only (cold vs corrected answers)
  python run_exp1.py run A [B]       # full experiment for the listed items
  python run_exp1.py selftest        # mechanics check on a tiny random model (no real results)

Everything follows PREREGISTRATION.md. Frozen items are read from items.json.
"""
import hashlib, json, math, os, platform, sys, time
import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
GEN_TOKENS = 6
SEED = 0
torch.manual_seed(SEED); np.random.seed(SEED)
torch.set_grad_enabled(False)
torch.use_deterministic_algorithms(True)

CFG = json.load(open(os.path.join(HERE, "items.json")))


# ---------------------------------------------------------------- model

def load(selftest=False):
    from transformers import GPT2LMHeadModel, GPT2TokenizerFast, GPT2Config
    tok = GPT2TokenizerFast.from_pretrained("gpt2") if not selftest else None
    if selftest:
        model = GPT2LMHeadModel(GPT2Config(n_layer=4, n_embd=64, n_head=4, n_inner=256))
    else:
        model = GPT2LMHeadModel.from_pretrained("gpt2", torch_dtype=torch.float32)
    model.eval()
    return model, tok


def fresh_copy(base):
    import copy
    m = copy.deepcopy(base); m.eval(); return m


def model_hash(model):
    h = hashlib.sha256()
    for k, v in sorted(model.state_dict().items()):
        h.update(k.encode()); h.update(v.detach().contiguous().numpy().tobytes())
    return h.hexdigest()


def tensor_hash(t):
    return hashlib.sha256(t.detach().contiguous().numpy().tobytes()).hexdigest()


class Tok:
    """Thin wrapper so the selftest can use a fake tokenizer."""
    def __init__(self, tok, vocab=None):
        self.tok = tok; self.vocab = vocab
    def enc(self, s):
        if self.tok is None:
            return [hash(w) % self.vocab for w in s.split()]
        return self.tok.encode(s)
    def dec(self, ids):
        if self.tok is None:
            return " ".join(str(i) for i in ids)
        return self.tok.decode(ids)
    @property
    def bos(self):
        return 0 if self.tok is None else self.tok.eos_token_id  # <|endoftext|> = 50256


# ---------------------------------------------------------------- forward with hooks

def run(model, ids, inject=None):
    """One forward pass. Returns logits at last pos and, per layer, the final-token
    MLP post-GELU input to c_proj (m), MLP output, and post-block residual.
    inject = (layer, delta, pos): add delta to block `layer`'s MLP output at position pos."""
    rec = {"m": {}, "mlp": {}, "res": {}}
    hs = []
    for L, blk in enumerate(model.transformer.h):
        def pre_cproj(mod, args, L=L):
            rec["m"][L] = args[0][0, -1].clone()
        def post_mlp(mod, args, out, L=L):
            if inject is not None and inject[0] == L:
                out = out.clone(); out[0, inject[2]] += inject[1]
            rec["mlp"][L] = out[0, -1].clone()
            return out
        def post_block(mod, args, out, L=L):
            o = out[0] if isinstance(out, tuple) else out
            rec["res"][L] = o[0, -1].clone()
        hs.append(blk.mlp.c_proj.register_forward_pre_hook(pre_cproj))
        hs.append(blk.mlp.register_forward_hook(post_mlp))
        hs.append(blk.register_forward_hook(post_block))
    try:
        out = model(torch.tensor([ids]))
    finally:
        for h in hs: h.remove()
    return out.logits[0, -1], rec


def greedy(model, ids, n=GEN_TOKENS, inject=None):
    ids = list(ids); new = []
    for _ in range(n):
        logits, _ = run(model, ids, inject)
        t = int(torch.argmax(logits)); ids.append(t); new.append(t)
    return new


def first_prob(model, tk, ids, target, inject=None):
    logits, _ = run(model, ids, inject)
    tid = tk.enc(" " + target)[0]
    return float(torch.softmax(logits, -1)[tid])


def correct(tk, new_ids, target):
    return tk.dec(new_ids).strip().startswith(target)


# ---------------------------------------------------------------- prompts

def cold_ids(tk, q):
    return [tk.bos] + tk.enc(q)


def corrected_ids(tk, correction, q):
    return [tk.bos] + tk.enc(correction) + tk.enc(" " + q)


def control_ids(tk, neutral, correction, q):
    """Neutral text cut or padded at token level to the correction's exact token length."""
    n = len(tk.enc(correction))
    nt = tk.enc(neutral)
    filler = tk.enc(" and")
    while len(nt) < n - 1:
        nt = nt + filler
    nt = nt[: n - 1] + tk.enc(".")
    assert len(nt) == n
    return [tk.bos] + nt + tk.enc(" " + q)


# ---------------------------------------------------------------- measurement

def deltas(model, tk, correction, q):
    c_ids = corrected_ids(tk, correction, q)
    _, rc = run(model, c_ids)
    ctrl = [run(model, control_ids(tk, nz, correction, q))[1] for nz in CFG["neutral"]]
    nL = len(model.transformer.h)
    d_res = {L: rc["res"][L] - torch.stack([r["res"][L] for r in ctrl]).mean(0) for L in range(nL)}
    d_mlp = {L: rc["mlp"][L] - torch.stack([r["mlp"][L] for r in ctrl]).mean(0) for L in range(nL)}
    # spread of the three controls, to gauge context confounding
    spread = {L: float(torch.stack([r["res"][L] for r in ctrl]).std(0).norm()) for L in range(nL)}
    return d_res, d_mlp, spread, c_ids


def apply_rank_one(model, L, m, delta):
    """Stored HF Conv1D weight is (3072, 768); y = x @ W + b.  Update W += m delta^T / (m^T m)."""
    W = model.transformer.h[L].mlp.c_proj.weight
    dW = torch.outer(m, delta) / torch.dot(m, m)
    W += dW
    return dW


def apply_lstsq(model, L, Ms, Ds):
    """Min-norm Delta with M_rows @ Delta = D_rows (stored layout)."""
    M = torch.stack(Ms).double(); D = torch.stack(Ds).double()
    dW = (torch.linalg.pinv(M) @ D).float()
    model.transformer.h[L].mlp.c_proj.weight += dW
    return dW


def verify_edit(base, edited, L, m, delta):
    o0 = base.transformer.h[L].mlp.c_proj(m[None])[0]
    o1 = edited.transformer.h[L].mlp.c_proj(m[None])[0]
    err = float((o1 - o0 - delta).norm() / delta.norm())
    return err


# ---------------------------------------------------------------- regression set

def regression_prompts(tk, selftest=False):
    if selftest:
        return [[tk.bos] + [(i * 7 + j) % 1000 for j in range(48)] for i in range(10)]
    from huggingface_hub import hf_hub_download
    import pyarrow.parquet as pq
    p = hf_hub_download("Salesforce/wikitext", "wikitext-2-raw-v1/test-00000-of-00001.parquet",
                        repo_type="dataset")
    lines = [r for r in pq.read_table(p).column("text").to_pylist()
             if len(r.split()) >= 30 and not r.strip().startswith("=")]
    return [[tk.bos] + tk.enc(r.strip())[:48] for r in lines[:100]]


def regression(model, prompts):
    tot_nll, tot_n, nexts = 0.0, 0, []
    for ids in prompts:
        logits = model(torch.tensor([ids])).logits[0]
        lp = torch.log_softmax(logits[:-1], -1)
        tgt = torch.tensor(ids[1:])
        tot_nll += float(-lp[torch.arange(len(tgt)), tgt].sum()); tot_n += len(tgt)
        nexts.append(int(torch.argmax(model(torch.tensor([ids[:33]])).logits[0, -1])))
    return math.exp(tot_nll / tot_n), nexts


# ---------------------------------------------------------------- screening

def screen(model, tk):
    rows = []
    for q, ans, src in CFG["b_candidates"]:
        corr = f"{q} {ans}."
        c = greedy(model, cold_ids(tk, q)); k = greedy(model, corrected_ids(tk, corr, q))
        row = {"question": q, "answer": ans, "source": src,
               "cold": tk.dec(c), "cold_correct": correct(tk, c, ans),
               "corrected": tk.dec(k), "corrected_correct": correct(tk, k, ans),
               "answer_tokens": len(tk.enc(" " + ans))}
        row["eligible"] = (not row["cold_correct"]) and row["corrected_correct"]
        rows.append(row); print(json.dumps(row))
    return rows


# ---------------------------------------------------------------- one item

def eval_variants(model, tk, variants):
    out = []
    for d, p, t in variants:
        g = greedy(model, cold_ids(tk, p))
        out.append({"direction": d, "prompt": p, "target": t, "answer": tk.dec(g), "correct": correct(tk, g, t)})
    return out


def run_item(base, tk, name, item, reg_prompts, base_reg):
    R = {"item": name, "correction": item["correction"], "question": item["question"],
         "target": item["target"], "source": item["source"]}
    q, corr, tgt = item["question"], item["correction"], item["target"]
    nL = len(base.transformer.h)

    # eligibility
    cold = cold_ids(tk, q)
    g_cold = greedy(base, cold); g_corr = greedy(base, corrected_ids(tk, corr, q))
    g_ctrl = [greedy(base, control_ids(tk, nz, corr, q)) for nz in CFG["neutral"]]
    R["tokenization"] = {"cold": cold, "corrected": corrected_ids(tk, corr, q),
                         "controls": [control_ids(tk, nz, corr, q) for nz in CFG["neutral"]],
                         "target_first_token": tk.enc(" " + tgt)[0]}
    R["eligibility"] = {"cold_answer": tk.dec(g_cold), "cold_correct": correct(tk, g_cold, tgt),
                        "corrected_answer": tk.dec(g_corr), "corrected_correct": correct(tk, g_corr, tgt),
                        "control_answers": [tk.dec(g) for g in g_ctrl],
                        "control_correct": [correct(tk, g, tgt) for g in g_ctrl]}
    R["eligibility"]["eligible"] = (not R["eligibility"]["cold_correct"]) and R["eligibility"]["corrected_correct"]
    print(name, "eligibility", R["eligibility"])
    if not R["eligibility"]["eligible"]:
        R["stopped"] = "failed eligibility check"; return R

    # activation differences
    d_res, d_mlp, spread, _ = deltas(base, tk, corr, q)
    R["delta_norms"] = {"res": [float(d_res[L].norm()) for L in range(nL)],
                        "mlp": [float(d_mlp[L].norm()) for L in range(nL)],
                        "control_spread_res": [spread[L] for L in range(nL)]}

    # causality: inject at the cold run's final position
    pos = len(cold) - 1
    sweep = []
    _, rec_cold = run(base, cold)
    for L in range(nL):
        row = {"layer": L}
        for arm, d in (("res", d_res[L]), ("mlp", d_mlp[L])):
            g = greedy(base, cold, inject=(L, d, pos))
            row[arm] = {"answer": tk.dec(g), "correct": correct(tk, g, tgt),
                        "p_target": first_prob(base, tk, cold, tgt, inject=(L, d, pos))}
        sweep.append(row)
    R["injection_sweep"] = sweep
    R["p_target_cold"] = first_prob(base, tk, cold, tgt)
    hits = [r["layer"] for r in sweep if r["res"]["correct"]]
    if not hits:
        R["stopped"] = "no layer recovered the answer by residual injection"; return R
    L = hits[0]; R["selected_layer"] = L
    m = rec_cold["m"][L]
    R["m_norm"] = float(m.norm())

    # arms
    R["arms"] = {}
    for arm, delta in (("arm1_residual", d_res[L]), ("arm2_mlp", d_mlp[L])):
        A = {}
        ed = fresh_copy(base)
        dW = apply_rank_one(ed, L, m, delta)
        A["edit"] = {"layer": L, "target_param": f"transformer.h.{L}.mlp.c_proj.weight",
                     "delta_norm": float(delta.norm()), "dW_fro": float(dW.norm()),
                     "dW_sha256": tensor_hash(dW), "model_sha256_after": model_hash(ed)}
        A["verify_rel_err"] = verify_edit(base, ed, L, m, delta)
        A["verify_pass"] = A["verify_rel_err"] < 1e-4
        if not A["verify_pass"]:
            A["stopped"] = "edit verification failed"; R["arms"][arm] = A; continue
        torch.save({"m": m, "delta": delta, "layer": L}, os.path.join(OUT, f"edit_{name}_{arm}.pt"))
        g = greedy(ed, cold)  # fresh call: no cache, no correction
        A["test_A"] = {"answer": tk.dec(g), "correct": correct(tk, g, tgt),
                       "p_target": first_prob(ed, tk, cold, tgt)}
        A["test_B"] = eval_variants(ed, tk, item["variants"])
        ppl, nexts = regression(ed, reg_prompts)
        A["test_C"] = {"ppl": ppl, "ppl_change_pct": 100 * (ppl / base_reg[0] - 1),
                       "answers_changed": sum(a != b for a, b in zip(nexts, base_reg[1])),
                       "changed_idx": [i for i, (a, b) in enumerate(zip(nexts, base_reg[1])) if a != b]}
        # Test D: averaged patch for this arm
        Ms, Ds = [], []
        for fq in item["fit_set"]:
            dr, dm, _, _ = deltas(base, tk, corr, fq)
            _, rc = run(base, cold_ids(tk, fq))
            Ms.append(rc["m"][L]); Ds.append(dr[L] if arm == "arm1_residual" else dm[L])
        edD = fresh_copy(base)
        dWD = apply_lstsq(edD, L, Ms, Ds)
        fit_err = [verify_edit(base, edD, L, mi, di) for mi, di in zip(Ms, Ds)]
        gD = greedy(edD, cold)
        pplD, nextsD = regression(edD, reg_prompts)
        A["test_D"] = {"fit_rel_err_max": max(fit_err), "dW_fro": float(dWD.norm()), "dW_sha256": tensor_hash(dWD),
                       "test_A": {"answer": tk.dec(gD), "correct": correct(tk, gD, tgt)},
                       "test_B": eval_variants(edD, tk, item["variants"]),
                       "test_C": {"ppl": pplD, "ppl_change_pct": 100 * (pplD / base_reg[0] - 1),
                                  "answers_changed": sum(a != b for a, b in zip(nextsD, base_reg[1]))}}
        R["arms"][arm] = A
        print(name, arm, "A:", A["test_A"], "ppl%:", round(A["test_C"]["ppl_change_pct"], 3))

    # exploratory, not preregistered: exact recovery of the single rank-one edit at every layer
    R["exploratory_layer_sweep"] = []
    for LL in range(nL):
        row = {"layer": LL}
        for arm, d in (("arm1_residual", d_res[LL]), ("arm2_mlp", d_mlp[LL])):
            ed = fresh_copy(base); apply_rank_one(ed, LL, rec_cold["m"][LL], d)
            g = greedy(ed, cold); row[arm] = {"answer": tk.dec(g), "correct": correct(tk, g, tgt)}
        R["exploratory_layer_sweep"].append(row)
    return R


def main():
    mode = sys.argv[1]
    selftest = mode == "selftest"
    os.makedirs(OUT, exist_ok=True)
    base, hf_tok = load(selftest)
    tk = Tok(hf_tok, vocab=base.config.vocab_size)
    env = {"python": platform.python_version(), "torch": torch.__version__,
           "transformers": __import__("transformers").__version__,
           "model": "gpt2" if not selftest else "random tiny (selftest)",
           "revision": getattr(base.config, "_commit_hash", None), "dtype": "float32",
           "device": "cpu", "seed": SEED, "model_sha256": model_hash(base),
           "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    if mode == "screen":
        rows = screen(base, tk)
        json.dump({"env": env, "screen": rows}, open(os.path.join(OUT, "screen_B.json"), "w"), indent=1)
        return
    if selftest:
        CFG["items"]["A"]["target"] = "x"  # mechanics only
        items = {"A": CFG["items"]["A"]}
    else:
        items = {k: CFG["items"][k] for k in sys.argv[2:]}
    reg_prompts = regression_prompts(tk, selftest)
    base_reg = regression(base, reg_prompts)
    env["regression_baseline_ppl"] = base_reg[0]
    results = {"env": env, "items": {}}
    for name, item in items.items():
        if selftest:
            # force a measurable path through the code without a real tokenizer
            results["items"][name] = selftest_item(base, tk)
        else:
            results["items"][name] = run_item(base, tk, name, item, reg_prompts, base_reg)
            results["items"][name]["baseline_variants"] = eval_variants(base, tk, item["variants"])
    fn = "selftest.json" if selftest else "results.json"
    json.dump(results, open(os.path.join(OUT, fn), "w"), indent=1, default=float)
    print("wrote", fn)


def selftest_item(base, tk):
    """Checks hooks, injection, rank-one edit, transposed layout and least squares on a random model."""
    ids = [tk.bos, 5, 9, 12, 40]
    _, r = run(base, ids)
    L = 1; m = r["m"][L]; delta = torch.randn(base.config.n_embd)
    ed = fresh_copy(base); apply_rank_one(ed, L, m, delta)
    e1 = verify_edit(base, ed, L, m, delta)
    # the edited model's MLP output at the final token must move by exactly delta
    _, r2 = run(ed, ids)
    e2 = float((r2["mlp"][L] - r["mlp"][L] - delta).norm() / delta.norm())
    # injecting delta must equal editing, at layer L's MLP output
    _, r3 = run(base, ids, inject=(L, delta, len(ids) - 1))
    e3 = float((r3["res"][L] - r2["res"][L]).norm() / r2["res"][L].norm())
    Ms = [run(base, ids[:k])[1]["m"][L] for k in (3, 4, 5)]; Ds = [torch.randn(base.config.n_embd) for _ in Ms]
    edD = fresh_copy(base); apply_lstsq(edD, L, Ms, Ds)
    e4 = max(verify_edit(base, edD, L, mi, di) for mi, di in zip(Ms, Ds))
    res = {"rank_one_verify": e1, "mlp_output_shift": e2, "inject_equals_edit": e3, "lstsq_fit": e4}
    print("selftest", res)
    assert max(res.values()) < 1e-4, res
    return res


if __name__ == "__main__":
    main()

"""Gate 0b-3: a room where curiosity costs something, then inherited patience.

Part A (probe): is there a finite best loan time when buds are many, building is
dear and the body can lend little per step?  Score = lifetime income (sugar
delivered over the whole 18000-step life with the window move and the cut).

Part B (inheritance): every shoot carries its own tau; a bud inherits its parent's
tau times exp(0.25 * N(0,1)).  Start whole vines at very different tau0 and watch
the conductance-weighted tau of the living body over the life."""
import sys, os, json
import numpy as np
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)
import vine_economy as ve

COSTLY = dict(gp=0.10, pb=2e-3, cgrow=1.0, R0=80.0, kR=0.02)
TAUS = [300.0, 600.0, 1000.0, 2000.0, 4000.0, 10000.0, float("inf")]
TAU0 = [300.0, 1000.0, 10000.0]
SEEDS = range(8)


def params(**kw):
    p = ve.default_params(); p.update(COSTLY); p.update(kw); return p


def probe(args):
    tau, seed = args
    r = ve.run(params(tau=tau), seed=seed)
    lg = r["log"]; d = lg[:, 3]
    return dict(tau=tau, seed=seed, life_income=float(d.mean()), end=float(d[lg[:, 0] >= 17000].mean()),
                established=bool((d > 1.0).any()), tips=float(lg[:, 10].mean()),
                famine=float((lg[:, 6] > 0).mean()), draw=float(lg[:, 4].mean()))


def inherit(args):
    tau0, seed = args
    r = ve.run(params(tau=tau0, inherit=True), seed=seed)
    lg = r["log"]
    return dict(tau0=tau0, seed=seed, t=lg[:, 0].tolist(), logtau=lg[:, 15].tolist(),
                life_income=float(lg[:, 3].mean()), alive=lg[:, 7].tolist())


if __name__ == "__main__":
    part = sys.argv[1] if len(sys.argv) > 1 else "both"
    with Pool(os.cpu_count()) as pool:
        if part in ("probe", "both"):
            pr = list(pool.imap_unordered(probe, [(t, s) for t in TAUS for s in SEEDS]))
            json.dump(pr, open(os.path.join(ROOT, "results/costly_probe.json"), "w"), default=str)
            for t in TAUS:
                q = [r for r in pr if r["tau"] == t]
                print(f"tau={t:>8}: lifetime income {np.mean([r['life_income'] for r in q]):5.2f} "
                      f"(sd {np.std([r['life_income'] for r in q]):4.2f})  reached {sum(r['established'] for r in q)}/8  "
                      f"tips {np.mean([r['tips'] for r in q]):4.1f}  draw {np.mean([r['draw'] for r in q]):.3f}  "
                      f"famine {100*np.mean([r['famine'] for r in q]):.1f}%", flush=True)
        if part in ("inherit", "both"):
            ih = list(pool.imap_unordered(inherit, [(t, s) for t in TAU0 for s in SEEDS]))
            json.dump(ih, open(os.path.join(ROOT, "results/costly_inherit.json"), "w"), default=str)
            for t0 in TAU0:
                q = [r for r in ih if r["tau0"] == t0]
                ends = [np.exp(np.nanmean(np.array(r["logtau"])[-60:])) for r in q if r["alive"][-1] > 0]
                print(f"tau0={t0:>8}: alive at end {sum(r['alive'][-1] > 0 for r in q)}/8, body tau at end "
                      f"median {np.median(ends) if ends else float('nan'):.0f}  range {np.min(ends) if ends else 0:.0f}-{np.max(ends) if ends else 0:.0f}, "
                      f"lifetime income {np.mean([r['life_income'] for r in q]):.2f}", flush=True)

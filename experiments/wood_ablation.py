"""Wood ablation: slow thick channels (lignified) vs uniformly fast channels,
under exactly the same seeds, moving window and cut."""
import sys, os, json
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import vine_economy as ve
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.dirname(__file__))
from sweep import first_at_least, ROOMS, T_MOVE, T_CUT, T

def one(args):
    room, tau, seed, lign = args
    p = ve.default_params(); p["gp"] = ROOMS[room]; p["tau"] = tau; p["lignify"] = lign
    r = ve.run(p, seed=seed, T=T, t_move=T_MOVE, t_cut=T_CUT)
    lg = r["log"]; t, d, alive = lg[:, 0], lg[:, 3], lg[:, 7]
    ph1 = d[(t >= T_MOVE - 1000) & (t < T_MOVE)].mean()
    ph2 = d[(t >= T_CUT - 1000) & (t < T_CUT)].mean()
    a1 = alive[(t >= T_MOVE - 1000) & (t < T_MOVE)].mean()
    win = (t > T_MOVE) & (t < T_MOVE + 3000)
    return dict(room=room, tau=tau, seed=seed, lignify=lign,
                established=bool((d > 1.0).any()),
                ph1=ph1, ph2=ph2, end=d[t >= T - 1000].mean(),
                alive_end=bool(d[t >= T - 500].mean() > 0.5),
                died_after_move=bool(ph1 > 1 and d[(t >= T_MOVE + 500) & (t < T_MOVE + 3000)].max() < 0.5),
                retained_move=float(d[win].min() / ph1) if ph1 > 1 else np.nan,
                structure_kept_500=float(alive[(t >= T_MOVE + 450) & (t <= T_MOVE + 550)].mean() / a1) if a1 > 0 else np.nan,
                rec_move=first_at_least(t, d, T_MOVE, 0.8 * ph1, after=100) if ph1 > 1 else np.nan,
                retained_cut=float(d[(t > T_CUT) & (t < T_CUT + 3000)].min() / ph2) if ph2 > 1 else np.nan,
                rec_cut=first_at_least(t, d, T_CUT, 0.8 * ph2, after=100) if ph2 > 1 else np.nan)

if __name__ == "__main__":
    jobs = [(room, tau, s, lign) for room in ROOMS for tau in [1000.0, float("inf")]
            for lign in [True, False] for s in range(8)]
    with Pool(os.cpu_count()) as pool:
        res = list(pool.imap_unordered(one, jobs))
    json.dump(res, open(ROOT + "/results/wood_ablation.json", "w"), indent=1, default=str)
    lines = ["| room | tau | channels | reached light | alive at end | died after window move | transport kept at worst (after move) | living structure kept 500 steps after move | median steps to recover (move) | transport kept at worst (after cut) | median steps to recover (cut) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for room in ROOMS:
        for tau in [1000.0, float("inf")]:
            for lign in [True, False]:
                q = [r for r in res if r["room"] == room and r["tau"] == tau and r["lignify"] == lign]
                med = lambda k: np.nanmedian([r[k] for r in q]) if np.isfinite([r[k] for r in q]).any() else np.nan
                fm = lambda x, n=0: "–" if not np.isfinite(x) else f"{x:.{n}f}"
                lines.append(f"| {room} | {'∞' if not np.isfinite(tau) else int(tau)} | {'slow wood' if lign else 'all fast'} | "
                             f"{sum(r['established'] for r in q)}/8 | {sum(r['alive_end'] for r in q)}/8 | {sum(r['died_after_move'] for r in q)}/8 | "
                             f"{fm(med('retained_move'), 2)} | {fm(med('structure_kept_500'), 2)} | {fm(med('rec_move'))} | {fm(med('retained_cut'), 2)} | {fm(med('rec_cut'))} |")
    out = "\n".join(lines); print(out)
    open(ROOT + "/results/wood_ablation.md", "w").write(out + "\n")

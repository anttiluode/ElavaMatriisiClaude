"""Gate 0b-2: leakage control. Same protocol as the Gate 0 sweep, but with no hard
conductance floor: channels only leak toward zero and are never removed (except
by the gardener's cut). Closing events are still counted when D crosses D_dead."""
import sys, os, json
import numpy as np
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
import vine_economy as ve
from sweep import first_at_least, ROOMS, T_MOVE, T_CUT, T


def one(args):
    room, tau, floor, seed = args
    p = ve.default_params(); p["gp"], p["tau"], p["floor"] = ROOMS[room], tau, floor
    r = ve.run(p, seed=seed)
    lg = r["log"]; t, d = lg[:, 0], lg[:, 3]
    ph1 = d[(t >= T_MOVE - 1000) & (t < T_MOVE)].mean()
    ph2 = d[(t >= T_CUT - 1000) & (t < T_CUT)].mean()
    st = r["st"]
    w1 = (t >= T_MOVE - 1000) & (t < T_MOVE)
    w2 = (t >= T_CUT - 1000) & (t < T_CUT)
    return dict(room=room, tau=tau, floor=floor, seed=seed,
                established=bool((d > 1.0).any()), alive_end=bool(d[t >= T - 500].mean() > 0.5),
                ph1=ph1, ph2=ph2, end=float(d[t >= T - 1000].mean()),
                rec_move=first_at_least(t, d, T_MOVE, 0.8 * ph1, after=100) if ph1 > 1 else np.nan,
                rec_cut=first_at_least(t, d, T_CUT, 0.8 * ph2, after=100) if ph2 > 1 else np.nan,
                closings=st[12], light_at_closing=st[13] / st[12] if st[12] > 0 else np.nan,
                light_alive=float(np.nanmean(lg[lg[:, 7] > 0, 11])),
                segments=float(lg[w2, 7].mean()), upkeep=float(lg[w2, 5].mean()),
                align_count_ph2=float(lg[w2, 9].mean()), alignD_ph1=float(lg[w1, 14].mean()),
                alignD_ph2=float(lg[w2, 14].mean()))


if __name__ == "__main__":
    jobs = [(room, tau, fl, s) for room in ROOMS for tau in [1000.0, float("inf")]
            for fl in [True, False] for s in range(8)]
    with Pool(os.cpu_count()) as pool:
        res = list(pool.imap_unordered(one, jobs))
    json.dump(res, open(os.path.join(ROOT, "results/leakage.json"), "w"), default=str)
    fm = lambda x, n=0: "–" if not np.isfinite(x) else f"{x:.{n}f}"
    lines = ["| room | tau | floor | reached light | alive at end | income before cut | segments in body | upkeep | light at closing vs living | where the conductance sits (D-weighted light alignment, before move / before cut) | median steps to recover: move / cut |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for room in ROOMS:
        for tau in [1000.0, float("inf")]:
            for fl in [True, False]:
                q = [r for r in res if r["room"] == room and r["tau"] == tau and r["floor"] == fl]
                med = lambda k: float(np.nanmedian([r[k] for r in q]))
                lines.append(f"| {room} | {'∞' if not np.isfinite(tau) else int(tau)} | {'hard floor' if fl else 'leak only'} | "
                             f"{sum(r['established'] for r in q)}/8 | {sum(r['alive_end'] for r in q)}/8 | {fm(med('ph2'),1)} | {fm(med('segments'))} | {fm(med('upkeep'),2)} | "
                             f"{fm(med('light_at_closing'),3)} vs {fm(med('light_alive'),3)} | {fm(med('alignD_ph1'),2)} / {fm(med('alignD_ph2'),2)} | {fm(med('rec_move'))} / {fm(med('rec_cut'))} |")
    s = "\n".join(lines); print(s)
    open(os.path.join(ROOT, "results/leakage.md"), "w").write(s + "\n")

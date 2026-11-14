"""Gate 0b-1: savings. Is a forgotten canopy re-grown faster than a new one?

Treatment: window right for 6000 steps (the vine learns the right side), then left
for `away` steps, then right again.
Control:   window left for 6000 + away steps, then right (the vine has never had
light on the right).
Both switch to the right window at the same moment, with the same total age.
Savings = how much faster / more the treatment earns on the right after the switch.
Run with slow wood and with all-fast channels (wood ablation as the control for the
mechanism)."""
import sys, os, json
import numpy as np
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)
import vine_economy as ve

ROOMS = {"bright": 0.30, "dim": 0.10}
AWAYS = [1000, 3000, 6000]
AFTER = 4000
TAU = 1000.0


def one(args):
    room, lign, away, arm, seed = args
    p = ve.default_params()
    p["gp"], p["lignify"], p["tau"] = ROOMS[room], lign, TAU
    ts = 6000 + away
    sched = [(0, "R"), (6000, "L"), (ts, "R")] if arm == "treat" else [(0, "L"), (ts, "R")]
    r = ve.run(p, seed=seed, T=ts + AFTER, schedule=sched, cut_times=[])
    lg = r["log"]
    t, d = lg[:, 0], lg[:, 3]
    pre_R = float(d[(t >= 5000) & (t < 6000)].mean()) if arm == "treat" else np.nan
    at = lg[np.argmin(np.abs(t - ts)), :]
    post = (t > ts) & (t <= ts + AFTER)
    return dict(room=room, lignify=lign, away=away, arm=arm, seed=seed,
                pre_R=pre_R, wood_R_at_switch=float(at[16]), alive_at_switch=float(at[7]),
                t_post=t[post].tolist(), d_post=d[post].tolist(),
                alive_end=bool(d[t >= ts + AFTER - 500].mean() > 0.5))


def analyse(res):
    out = []
    for room in ROOMS:
        for lign in [True, False]:
            for away in AWAYS:
                tr = [r for r in res if r["room"] == room and r["lignify"] == lign and r["away"] == away and r["arm"] == "treat"]
                co = [r for r in res if r["room"] == room and r["lignify"] == lign and r["away"] == away and r["arm"] == "control"]
                target = np.nanmedian([r["pre_R"] for r in tr])

                def rec(r):
                    t = np.array(r["t_post"]); d = np.array(r["d_post"])
                    m = d >= 0.8 * target
                    return float(t[m][0] - t[0] + 50) if m.any() else np.nan

                def area(r, horizon=2000):
                    t = np.array(r["t_post"]); d = np.array(r["d_post"])
                    m = t <= t[0] + horizon
                    return float(d[m].mean() / target)

                rt = [rec(r) for r in tr]; rc = [rec(r) for r in co]
                at = [area(r) for r in tr]; ac = [area(r) for r in co]
                # paired by seed
                diff = [a - b for a, b in zip(sorted(at, key=lambda _: 0), ac)]
                tr_s = sorted(tr, key=lambda r: r["seed"]); co_s = sorted(co, key=lambda r: r["seed"])
                pdiff = [area(a) - area(b) for a, b in zip(tr_s, co_s)]
                wins = sum(x > 0 for x in pdiff)
                out.append(dict(room=room, wood=lign, away=away, target=target,
                                rec_treat=np.nanmedian(rt), rec_ctrl=np.nanmedian(rc),
                                n_rec_treat=int(np.isfinite(rt).sum()), n_rec_ctrl=int(np.isfinite(rc).sum()),
                                area_treat=np.median(at), area_ctrl=np.median(ac),
                                paired_gain=np.median(pdiff), treat_wins=wins, n=len(pdiff),
                                wood_left_at_return=np.median([r["wood_R_at_switch"] for r in tr]),
                                wood_ctrl=np.median([r["wood_R_at_switch"] for r in co])))
    return out


if __name__ == "__main__":
    jobs = [(room, lign, away, arm, s) for room in ROOMS for lign in [True, False]
            for away in AWAYS for arm in ["treat", "control"] for s in range(8)]
    with Pool(os.cpu_count()) as pool:
        res = list(pool.imap_unordered(one, jobs))
    json.dump(res, open(os.path.join(ROOT, "results/savings.json"), "w"))
    rows = analyse(res)
    lines = ["| room | channels | time away | conductance left on the right at return | steps to 80% income: returning / never-lit | income in first 2000 steps (× old level): returning / never-lit | paired gain | returning vine ahead |",
             "|---|---|---|---|---|---|---|---|"]
    fm = lambda x, n=0: "–" if not np.isfinite(x) else f"{x:.{n}f}"
    for r in rows:
        lines.append(f"| {r['room']} | {'slow wood' if r['wood'] else 'all fast'} | {r['away']} | "
                     f"{fm(r['wood_left_at_return'],1)} (never-lit {fm(r['wood_ctrl'],1)}) | "
                     f"{fm(r['rec_treat'])} ({r['n_rec_treat']}/8) / {fm(r['rec_ctrl'])} ({r['n_rec_ctrl']}/8) | "
                     f"{fm(r['area_treat'],2)} / {fm(r['area_ctrl'],2)} | {r['paired_gain']:+.2f} | {r['treat_wins']}/{r['n']} |")
    s = "\n".join(lines); print(s)
    open(os.path.join(ROOT, "results/savings.md"), "w").write(s + "\n")

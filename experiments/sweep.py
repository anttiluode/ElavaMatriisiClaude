"""Gate 0 sweep: loan time tau x room brightness x seeds, plus the FREE reference.

Each life: 18000 steps. Window top-right until t=6000, then top-left.
At t=12000 the busiest living segment in the middle band is cut.
"""
import sys, os, json
import numpy as np
from multiprocessing import Pool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import vine_economy as ve

TAUS = [150, 300, 450, 600, 800, 1000, 1500, 2000, 4000, 10000, float("inf")]
ROOMS = {"bright": 0.30, "dim": 0.10}
SEEDS = list(range(8))
T_MOVE, T_CUT, T = 6000, 12000, 18000


def first_at_least(t, x, t0, level, after=0):
    """Steps from t0 until x first reaches level again, looking from t0 + after."""
    m = (t >= t0 + after) & (x >= level)
    return float(t[m][0] - t0) if m.any() else float("nan")


def one(args):
    room, tau, seed, free = args
    p = ve.default_params()
    p["gp"] = ROOMS[room]
    p["tau"] = tau
    if free:
        p["free"] = True
        p["tau"] = float("inf")
    r = ve.run(p, seed=seed, T=T, t_move=T_MOVE, t_cut=T_CUT)
    lg = r["log"]
    t, deliv, alive = lg[:, 0], lg[:, 3], lg[:, 7]
    ph1 = deliv[(t >= T_MOVE - 1000) & (t < T_MOVE)].mean()
    ph2 = deliv[(t >= T_CUT - 1000) & (t < T_CUT)].mean()
    ph3 = deliv[t >= T - 1000].mean()
    st = r["st"]
    deaths, death_light = st[12], st[13]
    est = first_at_least(t, deliv, 0, 1.0)
    out = dict(
        room=room, tau=tau, seed=seed, free=free,
        established=bool(np.isfinite(est)), t_establish=est,
        deliv_ph1=ph1, deliv_ph2=ph2, deliv_ph3=ph3,
        alive_end=bool(deliv[t >= T - 500].mean() > 0.5),
        rec_move=first_at_least(t, deliv, T_MOVE, 0.8 * ph1, after=100) if ph1 > 1 else float("nan"),
        min_after_move=float(deliv[(t >= T_MOVE) & (t < T_MOVE + 3000)].min()),
        rec_cut=first_at_least(t, deliv, T_CUT, 0.8 * ph2, after=100) if ph2 > 1 else float("nan"),
        min_after_cut=float(deliv[(t > T_CUT) & (t < T_CUT + 3000)].min()),
        align_ph1=float(lg[(t >= T_MOVE - 1000) & (t < T_MOVE), 9].mean()),
        align_ph2=float(lg[(t >= T_CUT - 1000) & (t < T_CUT), 9].mean()),
        grow=st[8], grow_own_wood=st[9], grow_room=st[10], grow_free=st[11],
        deaths=deaths, mean_light_at_death=(death_light / deaths) if deaths > 0 else float("nan"),
        mean_light_alive=float(np.nanmean(lg[lg[:, 7] > 0, 11])) if (lg[:, 7] > 0).any() else float("nan"),
        famine_frac=float((lg[:, 6] > 0).mean()),
        tips_mean=float(lg[:, 10].mean()),
        upkeep_ph2=float(lg[(t >= T_CUT - 1000) & (t < T_CUT), 5].mean()),
        draw_ph2=float(lg[(t >= T_CUT - 1000) & (t < T_CUT), 4].mean()),
        cut=r["cut"],
    )
    return out


if __name__ == "__main__":
    jobs = [(room, tau, s, False) for room in ROOMS for tau in TAUS for s in SEEDS]
    jobs += [(room, float("inf"), s, True) for room in ROOMS for s in SEEDS]
    with Pool(os.cpu_count()) as pool:
        res = []
        for k, o in enumerate(pool.imap_unordered(one, jobs)):
            res.append(o)
            if k % 20 == 0:
                print(k, len(jobs), flush=True)
    os.makedirs("results", exist_ok=True)
    with open("results/sweep.json", "w") as f:
        json.dump(res, f, indent=1, default=str)
    print("done", len(res))

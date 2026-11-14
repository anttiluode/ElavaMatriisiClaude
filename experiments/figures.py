"""Figures for Gate 0. Run after experiments/sweep.py."""
import sys, os, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import vine_economy as ve

OUT = "figures"
os.makedirs(OUT, exist_ok=True)

GREEN = "#3f8f3a"
DRY = "#8a6a45"
SUPPORT = "#9a9a9a"
INK = "#222222"


def draw_room(ax, snap, L0, S, title, cut=None):
    ax.imshow(L0.T, origin="lower", cmap="YlOrBr", alpha=0.35, vmin=0, vmax=1.2,
              extent=(-0.5, ve.W - 0.5, -0.5, ve.H - 0.5))
    sx, sy = np.nonzero(S)
    ax.scatter(sx, sy, s=4, c=SUPPORT, marker="s", lw=0)
    if len(snap["dry"]):
        ax.scatter(snap["dry"][:, 0], snap["dry"][:, 1], s=3, c=DRY, lw=0, alpha=0.8)
    if snap["edges"]:
        e = np.array(snap["edges"])
        segs = [[(a, b), (c, d)] for a, b, c, d, _ in e]
        lw = 0.6 + 3.0 * e[:, 4] / ve.default_params()["Dmax"]
        ax.add_collection(LineCollection(segs, colors=GREEN, linewidths=lw, capstyle="round"))
    if snap["tips"]:
        tp = np.array(snap["tips"])
        ax.scatter(tp[:, 0], tp[:, 1], s=14, facecolors="none", edgecolors=INK, lw=0.8)
    if cut is not None:
        ax.scatter([cut[0]], [cut[1]], marker="x", s=60, c="#c0392b", lw=2)
    ax.set_xlim(-0.5, ve.W - 0.5)
    ax.set_ylim(-0.5, ve.H - 0.5)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, fontsize=9)


def fig_life(tau=1000.0, seed=0, room_gp=0.30, name="life"):
    p = ve.default_params()
    p["tau"], p["gp"] = tau, room_gp
    snaps_at = (1500, 5999, 6800, 11999, 12400, 17999)
    r = ve.run(p, seed=seed, snap_times=snaps_at)
    titles = ["t=1500  first shoots", "t=6000  window top-right",
              "t=6800  window moved left", "t=12000  re-grown to the left",
              "t=12400  just after the cut", "t=18000  healed"]
    fig, axes = plt.subplots(1, 6, figsize=(16, 4.4))
    for ax, t, ti in zip(axes, snaps_at, titles):
        L0 = r["L1"] if t < 6000 else r["L2"]
        draw_room(ax, r["snaps"][t], L0, r["S"], ti, cut=r["cut"] if t >= 12000 else None)
    fig.suptitle(f"One life (bright room, loan time tau={tau:g}). Green: living channels, width = conductance. "
                 f"Brown: dry, cut-off stems. Circles: growing tips. Grey: chain and sign.", fontsize=9)
    fig.tight_layout()
    fig.savefig(f"{OUT}/{name}.png", dpi=130)
    plt.close(fig)
    return r


def fig_timeseries():
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    for ax, (room, gp) in zip(axes, [("bright", 0.30), ("dim", 0.10)]):
        for tau, col, lab in [(300, "#bbbbbb", "tau=300"), (1000, GREEN, "tau=1000"),
                              (float("inf"), "#2c5d8a", "tau=inf"), (None, "#c08a2c", "FREE")]:
            p = ve.default_params()
            p["gp"] = gp
            if tau is None:
                p["free"] = True
            else:
                p["tau"] = tau
            r = ve.run(p, seed=1)
            lg = r["log"]
            ax.plot(lg[:, 0], lg[:, 3], color=col, lw=1.1, label=lab)
        for x, txt in [(6000, "window moves"), (12000, "cut")]:
            ax.axvline(x, color="#999", ls="--", lw=0.8)
            ax.text(x + 100, ax.get_ylim()[1] * 0.9, txt, fontsize=8, color="#555")
        ax.set_ylabel(f"sugar delivered / step\n({room} room)")
        ax.legend(fontsize=8, ncol=4, loc="lower right")
    axes[-1].set_xlabel("step")
    fig.tight_layout()
    fig.savefig(f"{OUT}/timeseries.png", dpi=130)
    plt.close(fig)


def load():
    with open("results/sweep.json") as f:
        res = json.load(f)
    for r in res:
        r["tau"] = float(r["tau"])
        for k, v in list(r.items()):
            if isinstance(v, str):
                try:
                    r[k] = float(v)
                except ValueError:
                    pass
    return res


def tau_x(t):
    return 30000.0 if not np.isfinite(t) else t


def fig_threshold(res):
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    for room, col in [("bright", GREEN), ("dim", "#2c5d8a")]:
        rr = [r for r in res if r["room"] == room and not r["free"]]
        taus = sorted(set(r["tau"] for r in rr))
        pe = [np.mean([r["established"] for r in rr if r["tau"] == t]) for t in taus]
        pa = [np.mean([r["alive_end"] for r in rr if r["tau"] == t]) for t in taus]
        te = [np.nanmedian([r["t_establish"] for r in rr if r["tau"] == t and r["established"]])
              if any(r["established"] for r in rr if r["tau"] == t) else np.nan for t in taus]
        xs = [tau_x(t) for t in taus]
        axes[0].plot(xs, pe, "o-", color=col, label=f"{room}: reached light")
        axes[0].plot(xs, pa, "s--", color=col, alpha=0.6, label=f"{room}: alive at end")
        axes[1].plot(xs, te, "o-", color=col, label=room)
    for ax in axes:
        ax.set_xscale("log")
        ax.set_xlabel("loan time tau (steps)   [rightmost point = never called in]")
        ax.axvline(374, color="#c0392b", ls=":", lw=1)
    axes[0].text(390, 0.05, "reach estimate\ntau* = path cost / s0", fontsize=7, color="#c0392b")
    axes[0].set_ylabel("fraction of 8 lives")
    axes[0].legend(fontsize=7)
    axes[1].set_ylabel("median steps until the vine\nfirst delivers > 1 sugar/step")
    axes[1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(f"{OUT}/threshold.png", dpi=130)
    plt.close(fig)


def fig_pruning(res):
    rr = [r for r in res if not r["free"] and r["established"]]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    for k, room in enumerate(["bright", "dim"]):
        q = [r for r in rr if r["room"] == room]
        a = np.nanmean([r["mean_light_alive"] for r in q])
        d = np.nanmean([r["mean_light_at_death"] for r in q])
        axes[0].bar([k * 3, k * 3 + 1], [a, d], color=[GREEN, DRY])
        axes[0].text(k * 3 + 0.5, max(a, d) * 1.05, room, ha="center", fontsize=9)
    axes[0].set_xticks([0, 1, 3, 4])
    axes[0].set_xticklabels(["living", "at closing", "living", "at closing"], fontsize=8)
    axes[0].set_ylabel("light actually received\n(after self-shading)")
    axes[0].set_title("Which channels close? (no prune rule)", fontsize=9)
    for k, room in enumerate(["bright", "dim"]):
        q = [r for r in rr if r["room"] == room]
        g = np.array([[r["grow_own_wood"], r["grow_room"], r["grow_free"]] for r in q]).sum(0)
        g = g / g.sum()
        left = 0
        for v, col, lab in zip(g, [GREEN, SUPPORT, "#dddddd"], ["own living wood only", "chain / sign / dry stem", "nothing (hanging)"]):
            axes[1].barh(k, v, left=left, color=col, label=lab if k == 0 else None)
            axes[1].text(left + v / 2, k, f"{100 * v:.0f}%", ha="center", va="center", fontsize=8)
            left += v
    axes[1].set_yticks([0, 1])
    axes[1].set_yticklabels(["bright", "dim"])
    axes[1].set_title("What each new segment was holding on to", fontsize=9)
    axes[1].legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3)
    fig.tight_layout()
    fig.savefig(f"{OUT}/pruning_and_scaffold.png", dpi=130)
    plt.close(fig)


def gif_life(tau=1000.0, seed=0, every=150):
    from matplotlib.animation import FuncAnimation, PillowWriter
    p = ve.default_params()
    p["tau"] = tau
    r = ve.run(p, seed=seed, frames_every=every)
    fig, ax = plt.subplots(figsize=(3.6, 4.6))

    def upd(k):
        ax.clear()
        t = k * every
        L0 = r["L1"] if t < 6000 else r["L2"]
        draw_room(ax, r["frames"][k], L0, r["S"], f"step {t}", cut=r["cut"] if t >= 12000 else None)

    anim = FuncAnimation(fig, upd, frames=len(r["frames"]))
    anim.save(f"{OUT}/life.gif", writer=PillowWriter(fps=10))
    plt.close(fig)


if __name__ == "__main__":
    which = sys.argv[1:] or ["life", "timeseries", "threshold", "pruning", "gif"]
    if "life" in which:
        fig_life()
    if "timeseries" in which:
        fig_timeseries()
    if "threshold" in which or "pruning" in which:
        res = load()
        if "threshold" in which:
            fig_threshold(res)
        if "pruning" in which:
            fig_pruning(res)
    if "gif" in which:
        gif_life()
    print("figures done")

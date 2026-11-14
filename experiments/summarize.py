"""Print the Gate 0 results table from results/sweep.json (also writes results/summary.md)."""
import json, numpy as np

def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan

res = json.load(open("results/sweep.json"))
lines = []
for room in ["bright", "dim"]:
    lines.append(f"\n### {room} room\n")
    lines.append("| tau | reached light | alive at end | median steps to first light | income before move | income at end | median steps to recover after window move (n) | median steps to recover after cut (n) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    taus = sorted(set(f(r["tau"]) for r in res if r["room"] == room and not r["free"]))
    for t in taus:
        q = [r for r in res if r["room"] == room and not r["free"] and f(r["tau"]) == t]
        qe = [r for r in q if r["established"]]
        est = sum(r["established"] for r in q)
        al = sum(r["alive_end"] for r in q)
        te = np.nanmedian([f(r["t_establish"]) for r in qe]) if qe else np.nan
        p1 = np.nanmean([f(r["deliv_ph1"]) for r in qe]) if qe else np.nan
        p3 = np.nanmean([f(r["deliv_ph3"]) for r in qe]) if qe else np.nan
        rm = [f(r["rec_move"]) for r in q if np.isfinite(f(r["rec_move"]))]
        rc = [f(r["rec_cut"]) for r in q if np.isfinite(f(r["rec_cut"]))]
        fmt = lambda x: "–" if not np.isfinite(x) else f"{x:.0f}"
        fmt1 = lambda x: "–" if not np.isfinite(x) else f"{x:.1f}"
        lab = "∞" if not np.isfinite(t) else f"{t:.0f}"
        lines.append(f"| {lab} | {est}/{len(q)} | {al}/{len(q)} | {fmt(te)} | {fmt1(p1)} | {fmt1(p3)} | "
                     f"{fmt(np.median(rm)) if rm else '–'} ({len(rm)}) | {fmt(np.median(rc)) if rc else '–'} ({len(rc)}) |")
    qe = [r for r in res if r["room"] == room and not r["free"] and r["established"]]
    qf = [r for r in res if r["room"] == room and r["free"]]
    la = np.nanmean([f(r["mean_light_alive"]) for r in qe]); ld = np.nanmean([f(r["mean_light_at_death"]) for r in qe])
    g = np.array([[f(r["grow_own_wood"]), f(r["grow_room"]), f(r["grow_free"])] for r in qe]).sum(0); g = g / g.sum()
    fi = np.mean([f(r["deliv_ph2"]) for r in qf]); fu = np.mean([f(r["upkeep_ph2"]) for r in qf])
    ei = np.nanmean([f(r["deliv_ph2"]) for r in qe]); eu = np.nanmean([f(r["upkeep_ph2"]) for r in qe])
    lines.append("")
    lines.append(f"- light received by living segments {la:.3f}, by segments as their channel closed {ld:.3f} (ratio {la/ld:.1f}x)")
    lines.append(f"- new segments holding on to: own living wood only {100*g[0]:.0f}%, chain/sign/dry stem {100*g[1]:.0f}%, nothing {100*g[2]:.0f}%")
    lines.append(f"- light alignment of the living body (mean light on segments / room mean): economy {np.nanmean([f(r['align_ph1']) for r in qe]):.2f} before move, {np.nanmean([f(r['align_ph2']) for r in qe]):.2f} after; FREE {np.mean([f(r['align_ph1']) for r in qf]):.2f}")
    lines.append(f"- income before cut: economy {ei:.1f}/step with upkeep {eu:.1f}; FREE {fi:.1f}/step, and its upkeep if billed at the same rate would be {fu:.1f} (net {fi-fu:+.1f} vs {ei-eu:+.1f})")
    lines.append(f"- famine (body reserve hit zero): {100*np.mean([f(r['famine_frac']) for r in qe]):.2f}% of logged steps")
out = "\n".join(lines)
print(out)
open("results/summary.md", "w").write(out + "\n")

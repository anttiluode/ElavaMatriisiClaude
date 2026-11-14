# Elävä Matriisi (Claude) — Gate 0: the vine economy

**Work in progress.** The full sweep is running; results and figures will land here next.

A vine grows in a lattice room toward a window. There is **no prune rule and no task**. Instead:

- Light makes sugar in the segment it falls on.
- Channels stay open only on the flux they carry (canalization).
- Everything is paid from one shared body reserve.
- Growing tips live on a loan that decays as `s0 * exp(-a / tau)`, where `a` is the time since the shoot last paid for itself. `tau` is the one knob: how long the body keeps lending to a direction that hasn't paid off yet.

`vine_economy.py` is the model. `experiments/sweep.py` and `experiments/figures.py` run it.

![one life](figures/life.png)

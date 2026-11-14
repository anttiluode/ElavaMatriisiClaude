"""
Elävä Matriisi, Gate 0: the vine economy.

A vine grows on a lattice "room" from a pot on the floor. Light comes from a
window. Every segment of the vine is an edge with a conductance D (a phloem
channel). There is NO prune rule and NO task. There are only these things:

  1. Light makes sugar in any segment it falls on. A segment can only deliver
     what its channel can carry:  deliver_i = p_i * D_i / (D_i + D_h).
  2. Everything delivered flows down the tree to the body (the pot reserve R).
     Growing tips draw sugar UP from R. Both flows pass through the channels.
  3. Canalization: a channel is kept open only by what flows through it.
         dD_i/dt = eta_i * ( f(Q_i) - D_i ),   f(Q) = D_max * Q / (Q + Q_h)
     with eta_i = eta / (1 + D_i/D_wood)^2: thick wood changes slowly (it is the
     plant's long memory), green shoots change fast.
     Q_i is the gross flux through segment i (everything delivered from above it
     plus everything drawn by tips above it). Upkeep costs m * D_i per step,
     paid from R (more if the segment hangs unsupported). A channel whose D falls
     below D_dead stops conducting; the part of the vine above it is cut off and
     dries where it hangs. Dry stems stay in the room (they can be climbed) and
     crumble after a while.
  4. The loan. A tip may draw  s0 * exp(-a / tau)  from the body, where a counts
     steps since the shoot last paid for itself. tau is the ONE knob: how long the
     body keeps lending to a direction that has not paid off yet.

Pruning, scaffolding and exploring are not separate rules here. A shoot that
finds light keeps carrying flux and keeps its channel. A shoot that does not
find light loses its loan, its flux fades, its channel closes, and it dries.
"""

import numpy as np
from numba import njit

# ----------------------------------------------------------------------------
# Room
# ----------------------------------------------------------------------------
W, H = 56, 72
POT = (W // 2, 1)


def make_room():
    """Supports: a hanging chain on the right, a sign plate, a chain on the left."""
    S = np.zeros((W, H), dtype=np.bool_)
    for y in range(26, 66):                 # right chain, pin high on the right
        S[40, y] = True
    for x in range(18, 44):                 # the sign plate's edges
        S[x, 18] = True
        S[x, 25] = True
    for y in range(18, 26):
        S[18, y] = True
        S[43, y] = True
    for k in range(0, 40):                  # left chain, hanging diagonally to the sign
        x = 8 + k // 4
        y = 64 - k
        S[x, y] = True
    return S


def light_field(wx, wy, ell=16.0, base=0.02):
    xs = np.arange(W)[:, None]
    ys = np.arange(H)[None, :]
    return base + np.exp(-((xs - wx) ** 2 + (ys - wy) ** 2) / (2 * ell ** 2))


# ----------------------------------------------------------------------------
# Parameters
# ----------------------------------------------------------------------------
def default_params():
    return dict(
        gp=0.30,      # sugar per unit light per segment
        Dh=0.30,      # channel half-saturation for delivery
        Dmax=1.5,     # max conductance
        Qh=0.40,      # flux half-saturation for canalization
        eta=0.02,     # channel relaxation rate
        m=0.003,      # upkeep per unit conductance per step
        kfree=1.0,    # extra upkeep/build factor for an unsupported segment
        s0=0.10,      # full loan rate of a tip
        tau=1000.0,   # loan time constant (THE knob); np.inf = never called in
        kR=0.05,      # fraction of reserve the body can lend per step
        cgrow=0.5,    # sugar to build one supported segment
        D0=0.15,      # conductance of a fresh segment
        Ddead=0.02,   # below this a channel no longer conducts
        Dwood=0.35,   # above this a segment is woody (others can wrap on it, it can bud)
        pb=1e-4,      # budding probability per woody segment per step
        pb_root=0.002,  # the pot resprouts much more readily (a stump buds from its base)
        cbud=1.0,     # cost of a new bud
        maxchild=2,
        earn_frac=0.5,  # a shoot pays for itself if its tip delivers > earn_frac * s0
        gstarve=0.05, # extra closing of all channels at full famine
        rho=0.5,      # fraction of a closing channel's material returned to the body
        cmat=2.0,     # material per unit conductance
        lam=0.002,    # stores above Rfree are not free to keep (respiration)
        Rfree=200.0,  # what the body can store at no cost
        Tdry=2500,    # steps before a dry stem crumbles and frees its cell
        R0=150.0,     # the cutting's starting reserve
        bu=1.0,       # upward bias of growth direction
        bs=1.5,       # bias toward cells next to a support (thigmotropism)
        bl=3.0,       # bias toward brighter cells (phototropism)
        kshade=0.12,  # each living leaf on the line to the window dims light by this
        lignify=True, # False = wood ablation: every channel relaxes at the fast green rate
        free=False,   # FREE reference: nothing costs anything, nothing ever closes
    )


NMAX = 40000
PKEYS = ["gp", "Dh", "Dmax", "Qh", "eta", "m", "kfree", "s0", "tau", "kR", "cgrow",
         "D0", "Ddead", "Dwood", "pb", "cbud", "maxchild", "earn_frac", "gstarve",
         "rho", "cmat", "bu", "bs", "bl", "free", "lam", "Tdry", "Rfree", "pb_root", "lignify"]
NST = 14   # R, prod, deliv, draw, upkeep, famine, n_alive, n_dry, grow_events,
           # grow_on_own_wood, grow_on_room_support, grow_unsupported,
           # deaths (channels that closed), sum of light on segments when they closed


def pvec(p):
    v = np.zeros(len(PKEYS))
    for i, k in enumerate(PKEYS):
        x = float(p[k])
        v[i] = x if np.isfinite(x) else 1e30
    return v


# ----------------------------------------------------------------------------
# State
# ----------------------------------------------------------------------------
class Vine:
    def __init__(self, params):
        self.p = params
        self.pv = pvec(params)
        self.px = np.zeros(NMAX, np.int64)
        self.py = np.zeros(NMAX, np.int64)
        self.parent = -np.ones(NMAX, np.int64)
        self.D = np.zeros(NMAX)
        self.alive = np.zeros(NMAX, np.bool_)
        self.tip = np.zeros(NMAX, np.bool_)
        self.G = np.zeros(NMAX)
        self.a = np.zeros(NMAX)
        self.nchild = np.zeros(NMAX, np.int64)
        self.Q = np.zeros(NMAX)
        self.deliv = np.zeros(NMAX)
        self.prod = np.zeros(NMAX)
        self.occ = -np.ones((W, H), np.int64)
        self.dry = np.zeros((W, H), np.bool_)
        self.dry_age = np.zeros((W, H), np.int64)
        self.S = make_room()
        self.n = 0
        x, y = POT
        self._add(-1, x, y, 1.0, False)            # the pot / root system
        self._add(0, x, y + 1, params["D0"], True) # the first shoot
        self.st = np.zeros(NST)
        self.st[0] = params["R0"]

    def _add(self, par, x, y, D, tip):
        i = self.n
        self.px[i], self.py[i], self.parent[i] = x, y, par
        self.D[i], self.alive[i], self.tip[i] = D, True, tip
        self.occ[x, y] = i
        if par >= 0:
            self.nchild[par] += 1
        self.n = i + 1
        return i

    def cut(self, i):
        """A gardener's cut: segment i stops conducting now."""
        self.alive[i] = False
        self.tip[i] = False
        self.dry[self.px[i], self.py[i]] = True


@njit(cache=True)
def _support_kind(x, y, self_id, par_id, parent, alive, D, occ, dry, S, Dwood):
    """0 = hanging free, 1 = room support (chain, sign, dry stem), 2 = only own living wood."""
    own = False
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            if dx == 0 and dy == 0:
                continue
            xx, yy = x + dx, y + dy
            if xx < 0 or yy < 0 or xx >= S.shape[0] or yy >= S.shape[1]:
                continue
            if S[xx, yy] or dry[xx, yy]:
                return 1
            j = occ[xx, yy]
            if j >= 0 and alive[j] and j != self_id and j != par_id and parent[j] != self_id \
                    and D[j] > Dwood:
                own = True
    return 2 if own else 0


@njit(cache=True)
def step(n, px, py, parent, D, alive, tip, G, a, nchild, Q, deliv, prod, occ, dry, dry_age,
         S, L, pv, st, rand_u):
    gp, Dh, Dmax, Qh, eta, m, kfree, s0, tau, kR, cgrow = (pv[0], pv[1], pv[2], pv[3], pv[4],
                                                          pv[5], pv[6], pv[7], pv[8], pv[9], pv[10])
    D0, Ddead, Dwood, pb, cbud, maxchild, earn_frac, gstarve = (pv[11], pv[12], pv[13], pv[14],
                                                                pv[15], pv[16], pv[17], pv[18])
    rho, cmat, bu, bs, bl, free, lam, Tdry = (pv[19], pv[20], pv[21], pv[22], pv[23], pv[24],
                                              pv[25], pv[26])
    Rfree = pv[27]
    pb_root = pv[28]
    lignify = pv[29]
    free_mode = free > 0.5
    R = st[0]
    ri = 0
    nr = rand_u.shape[0]

    # --- 0. dry stems crumble --------------------------------------------------
    for x in range(S.shape[0]):
        for y in range(S.shape[1]):
            if dry[x, y]:
                dry_age[x, y] += 1
                if dry_age[x, y] > Tdry:
                    dry[x, y] = False
                    dry_age[x, y] = 0
                    occ[x, y] = -1

    # --- 1. light -> sugar, delivered through the segment's own channel -------
    tot_prod = 0.0
    tot_deliv = 0.0
    for i in range(n):
        if not alive[i]:
            prod[i] = 0.0
            deliv[i] = 0.0
            continue
        prod[i] = gp * L[px[i], py[i]]
        deliv[i] = prod[i] * D[i] / (D[i] + Dh)
        tot_prod += prod[i]
        tot_deliv += deliv[i]

    # --- 2. tips ask for loans; the body lends what it can ------------------
    draw = np.zeros(n)
    tot_want = 0.0
    for i in range(n):
        if alive[i] and tip[i]:
            draw[i] = s0 if free_mode else s0 * np.exp(-a[i] / tau)
            tot_want += draw[i]
    scale = 1.0
    if (not free_mode) and tot_want > 0.0:
        avail = kR * max(R, 0.0)
        if avail < tot_want:
            scale = avail / tot_want
    tot_draw = 0.0
    for i in range(n):
        if draw[i] > 0.0:
            draw[i] *= scale
            G[i] += draw[i]
            tot_draw += draw[i]

    # --- 3. upkeep and the shared budget --------------------------------------
    sup = np.zeros(n, np.int64)
    upkeep = 0.0
    for i in range(1, n):                   # node 0 is the pot: no upkeep
        if alive[i]:
            sup[i] = _support_kind(px[i], py[i], i, parent[i], parent, alive, D, occ, dry,
                                   S, Dwood)
            upkeep += m * D[i] * (1.0 + kfree * (1.0 if sup[i] == 0 else 0.0))
    famine = 0.0
    if not free_mode:
        R += tot_deliv - tot_draw - upkeep - lam * max(R - Rfree, 0.0)
        if R < 0.0:
            famine = min(1.0, -R / (upkeep + 1e-9))
            R = 0.0

    # --- 4. flux through every channel (children always have larger ids) ------
    for i in range(n):
        Q[i] = (deliv[i] + draw[i]) if alive[i] else 0.0
    for i in range(n - 1, 0, -1):
        if alive[i]:
            Q[parent[i]] += Q[i]

    # --- 5. canalization: flux keeps channels open ----------------------------
    if not free_mode:
        for i in range(1, n):
            if not alive[i]:
                continue
            target = Dmax * Q[i] / (Q[i] + Qh)
            # lignification: thick wood changes slowly, green shoots change fast
            w = 1.0 + D[i] / Dwood if lignify > 0.5 else 1.0
            dD = (eta / (w * w)) * (target - D[i]) - gstarve * famine * D[i]
            if dD < 0.0:
                R += rho * cmat * (-dD)
            D[i] += dD

    # --- 6. a channel that stopped conducting cuts off everything above it ----
    n_alive = 0
    deaths = 0.0
    death_light = 0.0
    for i in range(1, n):
        if alive[i] and (D[i] < Ddead or not alive[parent[i]]):
            deaths += 1.0
            death_light += L[px[i], py[i]]
            alive[i] = False
            tip[i] = False
            dry[px[i], py[i]] = True
            dry_age[px[i], py[i]] = 0
            if alive[parent[i]]:
                nchild[parent[i]] -= 1
        if alive[i]:
            n_alive += 1

    # --- 7. the loan clock: does the shoot pay for itself? ---------------------
    for i in range(n):
        if alive[i] and tip[i]:
            if deliv[i] > earn_frac * s0:
                a[i] = 0.0
            else:
                a[i] += 1.0

    # --- 8. growth: a tip that has saved enough builds one more segment -------
    new_n = n
    g_events = 0.0
    g_own = 0.0
    g_room = 0.0
    g_free = 0.0
    for i in range(n):
        if not (alive[i] and tip[i]):
            continue
        cost = cgrow if free_mode else cgrow * (1.0 + kfree * (1.0 if sup[i] == 0 else 0.0))
        if G[i] < cost:
            continue
        best = -1e30
        bx, by, bk = -1, -1, 0
        x, y = px[i], py[i]
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                xx, yy = x + dx, y + dy
                if xx < 0 or yy < 1 or xx >= S.shape[0] or yy >= S.shape[1]:
                    continue
                if occ[xx, yy] >= 0:
                    continue
                k = _support_kind(xx, yy, -2, i, parent, alive, D, occ, dry, S, Dwood)
                score = bu * dy + (bs if k > 0 else 0.0)
                score += bl * (L[xx, yy] - L[x, y]) / (L[x, y] + 0.05)
                u = rand_u[ri % nr]
                ri += 1
                score += -np.log(-np.log(u + 1e-12) + 1e-12)   # Gumbel noise
                if score > best:
                    best = score
                    bx, by, bk = xx, yy, k
        if bx < 0 or new_n >= px.shape[0]:
            tip[i] = False                   # boxed in: the meristem stops
            R += G[i]
            G[i] = 0.0
            continue
        G[i] -= cost
        j = new_n
        new_n += 1
        px[j], py[j], parent[j] = bx, by, i
        D[j] = 1.0 if free_mode else D0
        alive[j] = True
        tip[j] = True
        G[j] = G[i]
        G[i] = 0.0
        a[j] = a[i]                          # the loan clock follows the shoot
        tip[i] = False
        nchild[i] += 1
        nchild[j] = 0
        occ[bx, by] = j
        g_events += 1.0
        if bk == 2:
            g_own += 1.0
        elif bk == 1:
            g_room += 1.0
        else:
            g_free += 1.0

    # --- 9. buds on old wood: the old stem is where new search starts --------
    #     (node 0, the pot, can also resprout: a cut-back plant buds from its base)
    for i in range(0, n):
        if new_n >= px.shape[0]:
            break
        if (not alive[i]) or tip[i] or nchild[i] >= maxchild:
            continue
        if (not free_mode) and (D[i] < Dwood or R < cbud):
            continue
        u = rand_u[ri % nr]
        ri += 1
        if u > (pb if i > 0 else pb_root):
            continue
        x, y = px[i], py[i]
        for kk in range(8):
            dx = int(rand_u[ri % nr] * 3.0) - 1
            dy = int(rand_u[(ri + 1) % nr] * 3.0) - 1
            ri += 2
            if dx == 0 and dy == 0:
                continue
            xx, yy = x + dx, y + dy
            if xx < 0 or yy < 1 or xx >= S.shape[0] or yy >= S.shape[1] or occ[xx, yy] >= 0:
                continue
            j = new_n
            new_n += 1
            px[j], py[j], parent[j] = xx, yy, i
            D[j] = 1.0 if free_mode else D0
            alive[j] = True
            tip[j] = True
            G[j] = 0.0
            a[j] = 0.0                       # a fresh bud gets a fresh loan
            nchild[i] += 1
            nchild[j] = 0
            occ[xx, yy] = j
            if not free_mode:
                R -= cbud
            break

    n_dry = 0
    for x in range(S.shape[0]):
        for y in range(S.shape[1]):
            if dry[x, y]:
                n_dry += 1
    st[0] = R
    st[1] = tot_prod
    st[2] = tot_deliv
    st[3] = tot_draw
    st[4] = upkeep
    st[5] = famine
    st[6] = n_alive
    st[7] = n_dry
    st[8] += g_events
    st[9] += g_own
    st[10] += g_room
    st[11] += g_free
    st[12] += deaths
    st[13] += death_light
    return new_n


@njit(cache=True)
def shade(L0, occ, alive, wx, wy, kshade):
    """Leaves shade what lies behind them on the line to the window."""
    Wd, Hd = L0.shape
    out = np.empty_like(L0)
    for x in range(Wd):
        for y in range(Hd):
            dx = wx - x
            dy = wy - y
            dist = np.sqrt(dx * dx + dy * dy)
            nsteps = int(dist)
            cnt = 0
            for k in range(1, nsteps + 1):
                xx = int(round(x + dx * k / dist))
                yy = int(round(y + dy * k / dist))
                if xx < 0 or yy < 0 or xx >= Wd or yy >= Hd:
                    break
                j = occ[xx, yy]
                if j >= 0 and alive[j]:
                    cnt += 1
            out[x, y] = L0[x, y] * np.exp(-kshade * cnt)
    return out


# ----------------------------------------------------------------------------
# One life of one vine
# ----------------------------------------------------------------------------
def run(params, seed=0, T=18000, t_move=6000, t_cut=12000, log_every=50, frames_every=0,
        snap_times=()):
    """Phase 1: window top-right.  At t_move the window moves to top-left.
    At t_cut the busiest living segment in the middle band of the room is cut."""
    rng = np.random.default_rng(seed)
    v = Vine(params)
    win1, win2 = (W - 4, H - 4), (4, H - 4)
    L1 = light_field(*win1)
    L2 = light_field(*win2)
    L0, win = L1, win1
    kshade = params.get("kshade", 0.12)
    L = L0
    log, snaps, frames = [], {}, []
    cut_info = None
    rand_buf = rng.random(400009)
    for t in range(T):
        if t == t_move:
            L0, win = L2, win2
        if t % 10 == 0:
            L = shade(L0, v.occ, v.alive, win[0], win[1], kshade) if kshade > 0 else L0
        if t == t_cut:
            best, bi = -1.0, -1
            for i in range(1, v.n):
                if v.alive[i] and 26 <= v.py[i] <= 44 and v.Q[i] > best:
                    best, bi = v.Q[i], i
            if bi >= 0:
                cut_info = (int(v.px[bi]), int(v.py[bi]), float(best))
                v.cut(bi)
        off = int(rng.integers(0, 200000))
        v.n = step(v.n, v.px, v.py, v.parent, v.D, v.alive, v.tip, v.G, v.a, v.nchild, v.Q,
                   v.deliv, v.prod, v.occ, v.dry, v.dry_age, v.S, L, v.pv, v.st,
                   rand_buf[off:])
        if t % log_every == 0:
            alive = v.alive[:v.n]
            ax, ay = v.px[:v.n][alive], v.py[:v.n][alive]
            Lm = L0[ax, ay].mean() if alive.any() else 0.0
            Lsh = L[ax, ay].mean() if alive.any() else 0.0
            log.append((t, *v.st[:8], Lm / L0.mean(), int(v.tip[:v.n][alive].sum()), Lsh,
                        v.st[12], v.st[13]))
        if t in snap_times:
            snaps[t] = snapshot(v)
        if frames_every and t % frames_every == 0:
            frames.append(snapshot(v))
    return dict(log=np.array(log), snaps=snaps, frames=frames, cut=cut_info,
                final=snapshot(v), L1=L1, L2=L2, S=v.S, st=v.st.copy())


# columns of the log
LOGCOLS = ["t", "R", "prod", "deliv", "draw", "upkeep", "famine", "alive", "dry", "align",
           "tips", "L_alive", "deaths_cum", "death_light_cum"]


def snapshot(v):
    n = v.n
    edges = [(int(v.px[i]), int(v.py[i]), int(v.px[v.parent[i]]), int(v.py[v.parent[i]]),
              float(v.D[i])) for i in range(1, n) if v.alive[i]]
    tips = [(int(v.px[i]), int(v.py[i])) for i in range(n) if v.alive[i] and v.tip[i]]
    dry = np.argwhere(v.dry)
    return dict(edges=edges, tips=tips, dry=dry, R=float(v.st[0]))

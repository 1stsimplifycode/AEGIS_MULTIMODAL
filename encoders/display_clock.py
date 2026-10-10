# CONTROLLED COPY of research/icsc2027/src/display_clock.py (parent AEGIS-Market project), sha256 b7075a652c6a6e775df6da89d46a996802c9587a796026a23bd8b2a05b393fc2, copied 2026-10-10
# unchanged, so the hosted app is self-contained. Theory: research/icsc2027/finalists/F1_volume_clock_inventor.md
"""Display clocks: set-valued dating of a clockless display snapshot against a bar reference.

A display record shows, for one item, a vector of quantised fields y = (Q_k(x_k(f)))_k evaluated at an unknown
snapshot epoch f on the reference clock. The reference is NOT the path x itself but a bar summary of it
(OHLC + bar volume over bars of length `dt`). The identified set is

    F(y) = { f : there is a path x consistent with the bars such that Q_k(x_k(f)) in cell_k for every k }.

Everything here is exact set computation. Nothing interpolates inside a bar: the reference class is closed under
bar-preserving time warps, so (Theorem T1 in finalists/F1_volume_clock_inventor.md) F(y) is always a union of whole
bars. Sets are returned as sorted lists of bar indices, or as `IntervalSet` in seconds when shifts are needed.

Fields
------
price    non-monotone. In bar j the price at f can be any value in [L_j, H_j].
counter  non-decreasing cumulative count (displayed cumulative volume). In bar j it ranges over
         [C_j + d_lo, C_{j+1} + d_hi], where C_j is the cumulative bar volume before bar j and [d_lo, d_hi] bounds an
         unknown additive offset between display and reference (e.g. missing pre-open auction volume).
runmax   day high, a one-sided ratchet. In bar j: [max(M_{j-1}, O_j), M_j] with M_j = max(M_{j-1}, H_j).
runmin   day low, the mirror ratchet: [m_j, min(m_{j-1}, O_j)].
const    a field that is constant over the session (previous close): all bars or none.

Cells are closed intervals [lo, hi] (conservative: a half-open display cell is replaced by its closure).
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

Cell = Tuple[float, float]
EPS = 1e-9


# --------------------------------------------------------------------------------------------- display cells
def round_cell(shown: float, quantum: float) -> Cell:
    """Cell of true values that round to `shown` at resolution `quantum`."""
    return (shown - quantum / 2.0, shown + quantum / 2.0)


def trunc_cell(shown: float, quantum: float) -> Cell:
    """Cell of true values that truncate to `shown`."""
    return (shown, shown + quantum)


def unknown_rule_cell(shown: float, quantum: float) -> Cell:
    """Union of the rounding and truncation cells (display rule unknown)."""
    return (shown - quantum / 2.0, shown + quantum)


def km_quantum(v: float) -> float:
    """TV18-style volume display: 2 decimals in k (thousands) or m (millions) units."""
    return 1e4 if v >= 1e6 else 10.0


def quantise(value: float, quantum: float) -> float:
    return round(value / quantum) * quantum


# --------------------------------------------------------------------------------------------- reference bars
@dataclass(frozen=True)
class Bars:
    open: Tuple[float, ...]
    high: Tuple[float, ...]
    low: Tuple[float, ...]
    close: Tuple[float, ...]
    volume: Tuple[float, ...]
    dt: float = 60.0

    def __post_init__(self):
        n = len(self.open)
        if not (len(self.high) == len(self.low) == len(self.close) == len(self.volume) == n):
            raise ValueError("ragged bars")
        for j in range(n):
            if not (self.low[j] - EPS <= min(self.open[j], self.close[j])
                    and max(self.open[j], self.close[j]) <= self.high[j] + EPS):
                raise ValueError(f"bar {j} violates L <= O,C <= H")
            if self.volume[j] < 0:
                raise ValueError(f"bar {j} negative volume")

    @property
    def n(self) -> int:
        return len(self.open)

    def cumulative(self) -> List[float]:
        """C[0..n]: C[j] = volume traded before bar j."""
        c = [0.0]
        for v in self.volume:
            c.append(c[-1] + v)
        return c

    def running_max(self) -> List[float]:
        """M[0..n]: M[0] = -inf, M[j+1] = max over bars 0..j of H."""
        m = [-math.inf]
        for h in self.high:
            m.append(max(m[-1], h))
        return m

    def running_min(self) -> List[float]:
        m = [math.inf]
        for lo in self.low:
            m.append(min(m[-1], lo))
        return m


def _meets(a: float, b: float, cell: Cell) -> bool:
    return a <= cell[1] + EPS and b >= cell[0] - EPS


# --------------------------------------------------------------------------------------------- per-bar ranges
def price_range(bars: Bars, j: int) -> Cell:
    return (bars.low[j], bars.high[j])


def runmax_range(bars: Bars, j: int, M: Optional[List[float]] = None) -> Cell:
    M = M or bars.running_max()
    return (max(M[j], bars.open[j]), M[j + 1])


def runmin_range(bars: Bars, j: int, m: Optional[List[float]] = None) -> Cell:
    m = m or bars.running_min()
    return (m[j + 1], min(m[j], bars.open[j]))


def counter_range(bars: Bars, j: int, C: Optional[List[float]] = None, offset: Cell = (0.0, 0.0)) -> Cell:
    C = C or bars.cumulative()
    return (C[j] + offset[0], C[j + 1] + offset[1])


# --------------------------------------------------------------------------------------------- identified sets
def price_set(bars: Bars, cell: Cell) -> List[int]:
    return [j for j in range(bars.n) if _meets(bars.low[j], bars.high[j], cell)]


def counter_set(bars: Bars, cell: Cell, offset: Cell = (0.0, 0.0), C: Optional[List[float]] = None) -> List[int]:
    """Bars j with [C_j + d_lo, C_{j+1} + d_hi] meeting the cell. Always consecutive (Theorem T3). O(log n)."""
    C = C if C is not None else bars.cumulative()
    lo, hi = cell[0] - offset[1], cell[1] - offset[0]  # move the offset onto the cell
    # j feasible iff C[j+1] >= lo and C[j] <= hi
    j_lo = bisect.bisect_left(C, lo - EPS, 1) - 1          # first j with C[j+1] >= lo
    j_hi = bisect.bisect_right(C, hi + EPS, 0, bars.n) - 1  # last j (< n) with C[j] <= hi
    j_lo = max(j_lo, 0)
    return list(range(j_lo, j_hi + 1)) if j_lo <= j_hi else []


def counter_set_bruteforce(bars: Bars, cell: Cell, offset: Cell = (0.0, 0.0)) -> List[int]:
    C = bars.cumulative()
    return [j for j in range(bars.n) if _meets(C[j] + offset[0], C[j + 1] + offset[1], cell)]


def runmax_set(bars: Bars, cell: Cell) -> List[int]:
    M = bars.running_max()
    return [j for j in range(bars.n) if _meets(*runmax_range(bars, j, M), cell)]


def runmin_set(bars: Bars, cell: Cell) -> List[int]:
    m = bars.running_min()
    return [j for j in range(bars.n) if _meets(*runmin_range(bars, j, m), cell)]


def const_set(n: int, value: float, cell: Cell) -> List[int]:
    return list(range(n)) if cell[0] - EPS <= value <= cell[1] + EPS else []


def intersect(*sets: Iterable[int]) -> List[int]:
    """Joint identified set for fields/items with a product reference class (Theorem T2)."""
    sets = [set(s) for s in sets]
    if not sets:
        return []
    out = sets[0]
    for s in sets[1:]:
        out &= s
    return sorted(out)


def joint_price_ratchets(bars: Bars, cp: Optional[Cell], cM: Optional[Cell], cm: Optional[Cell]) -> List[int]:
    """Exact joint set for (price, day high, day low) from ONE coupled price path.

    In bar j a time f is feasible iff there are representatives p in cp and [L_j,H_j], M in cM and the runmax range,
    m in cm and the runmin range with m <= p <= M (Theorem T2b: no further coupling survives a continuous-time warp
    class). Missing fields are passed as None.
    """
    INF = math.inf
    Mx, mn = bars.running_max(), bars.running_min()
    out = []
    for j in range(bars.n):
        P = _cap(price_range(bars, j), cp)
        A = _cap(runmax_range(bars, j, Mx), cM) if cM is not None else (-INF, INF)
        B = _cap(runmin_range(bars, j, mn), cm) if cm is not None else (-INF, INF)
        if P is None or A is None or B is None:
            continue
        # need m <= p <= M with m in B, p in P, M in A
        p_lo = max(P[0], B[0])   # p must be >= some m in B: p >= B.lo
        p_hi = min(P[1], A[1])   # p must be <= some M in A: p <= A.hi
        if p_lo <= p_hi + EPS:
            out.append(j)
    return out


def _cap(r: Cell, c: Optional[Cell]) -> Optional[Cell]:
    if c is None:
        return r
    lo, hi = max(r[0], c[0]), min(r[1], c[1])
    return (lo, hi) if lo <= hi + EPS else None


# --------------------------------------------------------------------------------------------- set geometry
def components(bar_set: Sequence[int]) -> int:
    s = sorted(bar_set)
    return sum(1 for i, j in enumerate(s) if i == 0 or j != s[i - 1] + 1)


def is_interval(bar_set: Sequence[int]) -> bool:
    return components(bar_set) <= 1


def chebyshev(bar_set: Sequence[int], dt: float = 60.0) -> Tuple[float, float]:
    """(centre, radius) in seconds of the hull of the union of closed bars: the minimax-optimal point estimate and
    its worst-case error (Theorem T4)."""
    if not bar_set:
        raise ValueError("empty identified set (model rejected)")
    a, b = min(bar_set) * dt, (max(bar_set) + 1) * dt
    return (a + b) / 2.0, (b - a) / 2.0


def boundaries_in_cell(bars: Bars, cell: Cell, offset: Cell = (0.0, 0.0)) -> int:
    """N_I: interior bar boundaries b = 1..n-1 whose reference value, widened by the offset band, meets the cell."""
    C = bars.cumulative()
    return sum(1 for b in range(1, bars.n) if _meets(C[b] + offset[0], C[b] + offset[1], cell))


# --------------------------------------------------------------------------------------------- interval sets (s)
class IntervalSet:
    """Finite union of closed intervals on the reference clock (seconds)."""

    def __init__(self, ivs: Iterable[Tuple[float, float]] = ()):
        ivs = sorted((float(a), float(b)) for a, b in ivs if b >= a)
        merged: List[List[float]] = []
        for a, b in ivs:
            if merged and a <= merged[-1][1] + EPS:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        self.ivs = [tuple(x) for x in merged]

    @classmethod
    def from_bars(cls, bar_set: Iterable[int], dt: float = 60.0) -> "IntervalSet":
        return cls((j * dt, (j + 1) * dt) for j in bar_set)

    def shift(self, s: float) -> "IntervalSet":
        return IntervalSet((a + s, b + s) for a, b in self.ivs)

    def __and__(self, other: "IntervalSet") -> "IntervalSet":
        out, i, k = [], 0, 0
        A, B = self.ivs, other.ivs
        while i < len(A) and k < len(B):
            lo, hi = max(A[i][0], B[k][0]), min(A[i][1], B[k][1])
            if lo <= hi + EPS:
                out.append((lo, max(lo, hi)))
            if A[i][1] < B[k][1]:
                i += 1
            else:
                k += 1
        return IntervalSet(out)

    def __contains__(self, t: float) -> bool:
        return any(a - EPS <= t <= b + EPS for a, b in self.ivs)

    def measure(self) -> float:
        return sum(b - a for a, b in self.ivs)

    def empty(self) -> bool:
        return not self.ivs

    def n_components(self) -> int:
        return len(self.ivs)

    def __repr__(self):
        return f"IntervalSet({self.ivs})"


def common_epoch_test(item_sets: Sequence[IntervalSet], shifts: Optional[Sequence[float]] = None) -> IntervalSet:
    """Feasible loop epochs f0 under the hypothesis f_i = f0 + s_i (s_i = 0: one global snapshot per loop).

    Returns the intersection of F_i - s_i. An empty result rejects the hypothesis with zero false-rejection
    probability when the reference model is correct (Theorem T6)."""
    shifts = shifts or [0.0] * len(item_sets)
    out: Optional[IntervalSet] = None
    for F, s in zip(item_sets, shifts):
        G = F.shift(-s)
        out = G if out is None else (out & G)
    return out if out is not None else IntervalSet()


# --------------------------------------------------------------------------------------------- offset calibration
def offset_set(bars: Bars, records: Sequence[Tuple[Cell, Cell]], delta_box: Cell,
               C: Optional[List[float]] = None) -> IntervalSet:
    """Feasible additive counter offsets d (display = reference + d) for several records of ONE item.

    Each record is (price_cell, counter_cell) shown at its own unknown epoch. Record r admits d iff some bar j has
    price cell meeting [L_j,H_j] and counter cell meeting [C_j + d, C_{j+1} + d], i.e.
    d in U_r = union over price-feasible j of [lo - C_{j+1}, hi - C_j]. The offset is shared, the epochs are not,
    so the identified offset set is the intersection of U_r with delta_box (Theorem T7).
    """
    C = C if C is not None else bars.cumulative()
    out = IntervalSet([delta_box])
    for pc, vc in records:
        U = IntervalSet((vc[0] - C[j + 1], vc[1] - C[j]) for j in price_set(bars, pc))
        out = out & U
    return out


def counter_set_given_offsets(bars: Bars, price_cell: Optional[Cell], counter_cell: Cell, D: IntervalSet,
                              C: Optional[List[float]] = None) -> List[int]:
    """Exact joint dating set of one record once the offset is known to lie in the set D."""
    C = C if C is not None else bars.cumulative()
    cand = price_set(bars, price_cell) if price_cell is not None else range(bars.n)
    out = []
    for j in cand:
        band = IntervalSet([(counter_cell[0] - C[j + 1], counter_cell[1] - C[j])])
        if not (band & D).empty():
            out.append(j)
    return out

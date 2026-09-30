"""Leg distance matrix and optimal tour (Held-Karp)."""
from __future__ import annotations

import itertools

import numpy as np

from ..config import get_config
from ..detect.identity import BOOTH


def node_xy(course: dict) -> dict:
    nodes = {BOOTH: (course["booth"]["x"], course["booth"]["y"])}
    for s in course["stations"]:
        nodes[s["id"]] = (s["x"], s["y"])
    return nodes


def build_matrix(course: dict, walked: list[dict], cfg=None) -> tuple[list[dict], float]:
    """walked: [{from, to, meters}] measured along the survey route.

    Returns (legs, detour_factor). Every ordered pair appears once per direction.
    """
    cfg = cfg or get_config()
    nodes = node_xy(course)
    ratios = []
    wmap: dict[tuple, list[float]] = {}
    for w in walked:
        a, b = w["from"], w["to"]
        if a not in nodes or b not in nodes or a == b:
            continue
        straight = float(np.hypot(nodes[a][0] - nodes[b][0], nodes[a][1] - nodes[b][1]))
        if straight > 3:
            ratios.append(w["meters"] / straight)
        key = tuple(sorted((a, b)))
        wmap.setdefault(key, []).append(w["meters"])
    detour = float(np.clip(np.median(ratios), 1.0, 3.0)) if ratios else cfg.course.default_detour_factor
    legs = []
    for a, b in itertools.permutations(nodes, 2):
        key = tuple(sorted((a, b)))
        straight = float(np.hypot(nodes[a][0] - nodes[b][0], nodes[a][1] - nodes[b][1]))
        if key in wmap:
            legs.append({"from": a, "to": b, "meters": round(float(np.mean(wmap[key])), 1),
                         "straight_m": round(straight, 1), "kind": "walked"})
        else:
            legs.append({"from": a, "to": b, "meters": round(straight * detour, 1),
                         "straight_m": round(straight, 1), "kind": "estimated"})
    return legs, round(detour, 3)


def leg_lookup(legs: list[dict]) -> dict:
    return {(l["from"], l["to"]): l for l in legs}


def optimal_tour(required: list[str], legs: list[dict]) -> tuple[float, list[str]]:
    """Shortest BOOTH -> all required -> BOOTH tour. Held-Karp, fine up to ~15 stations."""
    lk = leg_lookup(legs)

    def d(a, b):
        l = lk.get((a, b))
        return l["meters"] if l else 1e9

    n = len(required)
    if n == 0:
        return 0.0, [BOOTH, BOOTH]
    if n <= 7:
        best, route = 1e18, None
        for perm in itertools.permutations(required):
            seq = (BOOTH,) + perm + (BOOTH,)
            tot = sum(d(seq[i], seq[i + 1]) for i in range(len(seq) - 1))
            if tot < best:
                best, route = tot, list(seq)
        return float(best), route
    idx = {s: i for i, s in enumerate(required)}
    dp: dict[tuple[int, int], tuple[float, int]] = {}
    for s in required:
        dp[(1 << idx[s], idx[s])] = (d(BOOTH, s), -1)
    for size in range(2, n + 1):
        for subset in itertools.combinations(range(n), size):
            mask = sum(1 << i for i in subset)
            for j in subset:
                prev = mask & ~(1 << j)
                best = (1e18, -1)
                for k in subset:
                    if k == j or (prev, k) not in dp:
                        continue
                    c = dp[(prev, k)][0] + d(required[k], required[j])
                    if c < best[0]:
                        best = (c, k)
                dp[(mask, j)] = best
    full = (1 << n) - 1
    best, last = min((dp[(full, j)][0] + d(required[j], BOOTH), j) for j in range(n))
    order, mask, j = [], full, last
    while j != -1:
        order.append(required[j])
        pj = dp[(mask, j)][1]
        mask &= ~(1 << j)
        j = pj
    return float(best), [BOOTH] + order[::-1] + [BOOTH]

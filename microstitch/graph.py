from .matching import *
from .models import _noop_progress

def _candidate_pairs(tiles: list[Tile], settings: StitchSettings) -> list[tuple[int, int]]:
    n = len(tiles)
    if n <= settings.all_pairs_limit:
        return [(i, j) for i in range(n) for j in range(i + 1, n)]

    # Scalable descriptor-vote retrieval.  Each image's sampled descriptors
    # vote for likely overlapping images in one pooled index.
    descriptors: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    rng = np.random.default_rng(settings.deterministic_seed)
    for tile in tiles:
        des = tile.descriptors
        if des is None or not len(des):
            continue
        if len(des) > 900:
            des = des[rng.choice(len(des), 900, replace=False)]
        descriptors.append(des.astype(np.float32))
        labels.append(np.full(len(des), tile.index, np.int32))
    pairs: set[tuple[int, int]] = set()
    if descriptors:
        pooled = np.vstack(descriptors)
        pooled_labels = np.concatenate(labels)
        matcher = cv2.FlannBasedMatcher(dict(algorithm=1, trees=6), dict(checks=48))
        for tile in tiles:
            des = tile.descriptors
            if des is None or not len(des):
                continue
            query = des[::max(1, len(des) // 500)].astype(np.float32)
            try:
                neighbours = matcher.knnMatch(query, pooled, k=6)
            except cv2.error:
                continue
            votes: dict[int, int] = {}
            for row in neighbours:
                for match in row:
                    label = int(pooled_labels[match.trainIdx])
                    if label != tile.index:
                        votes[label] = votes.get(label, 0) + 1
                        break
            for other, _ in sorted(votes.items(), key=lambda x: -x[1])[: settings.candidate_neighbors]:
                pairs.add(tuple(sorted((tile.index, other))))

    # Capture-order neighbours are a strong but not exclusive prior.
    ordered = sorted(range(n), key=lambda i: filename_capture_key(tiles[i].path))
    for pos, idx in enumerate(ordered):
        for delta in range(1, 5):
            if pos + delta < n:
                pairs.add(tuple(sorted((idx, ordered[pos + delta]))))
    return sorted(pairs)


def find_pairwise_edges(tiles: list[Tile], settings: StitchSettings, progress: ProgressFn = _noop_progress) -> list[MatchEdge]:
    pairs = _candidate_pairs(tiles, settings)
    edges: list[MatchEdge] = []
    for k, (i, j) in enumerate(pairs):
        edge = match_pair(tiles[i], tiles[j], settings)
        if edge is not None:
            edges.append(edge)
        progress("matching", (k + 1) / max(len(pairs), 1), f"Matched {k + 1}/{len(pairs)} pairs")
    if not edges:
        raise RuntimeError("No reliable overlaps were found. Increase overlap or use higher matching quality.")
    return edges


class UnionFind:
    def __init__(self, items: Iterable[int]):
        self.parent = {x: x for x in items}

    def find(self, x: int) -> int:
        p = self.parent[x]
        if p != x:
            self.parent[x] = self.find(p)
        return self.parent[x]

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.parent[rb] = ra
        return True


def connected_components(indices: Sequence[int], edges: Sequence[MatchEdge]) -> list[list[int]]:
    uf = UnionFind(indices)
    allowed = set(indices)
    for edge in edges:
        if edge.i in allowed and edge.j in allowed:
            uf.union(edge.i, edge.j)
    groups: dict[int, list[int]] = {}
    for idx in indices:
        groups.setdefault(uf.find(idx), []).append(idx)
    return sorted(groups.values(), key=lambda g: (-len(g), g))


def estimate_log_scales(component: list[int], edges: list[MatchEdge]) -> dict[int, float]:
    root = component[0]
    variables = [idx for idx in component if idx != root]
    position = {idx: k for k, idx in enumerate(variables)}
    component_set = set(component)
    used = [e for e in edges if e.i in component_set and e.j in component_set]
    if not variables or not used:
        return {idx: 0.0 for idx in component}

    def unpack(x: np.ndarray, idx: int) -> float:
        return 0.0 if idx == root else float(x[position[idx]])

    median_score = np.median([e.score for e in used]) or 1.0

    def residual(x: np.ndarray) -> np.ndarray:
        values = []
        for e in used:
            weight = math.sqrt(np.clip(e.score / median_score, 0.25, 4.0))
            values.append(weight * ((unpack(x, e.j) - unpack(x, e.i)) - math.log(e.scale)))
        return np.asarray(values, np.float64)

    result = least_squares(residual, np.zeros(len(variables)), loss="soft_l1", f_scale=0.05, max_nfev=200)
    return {idx: unpack(result.x, idx) for idx in component}


def detect_objective_groups(tiles: list[Tile], edges: list[MatchEdge], settings: StitchSettings) -> tuple[list[ObjectiveGroup], dict[int, float]]:
    all_indices = list(range(len(tiles)))
    components = connected_components(all_indices, edges)
    all_log_scales: dict[int, float] = {}
    groups: list[ObjectiveGroup] = []
    group_id = 1
    gap = math.log(settings.objective_gap_ratio)
    for component_id, component in enumerate(components, start=1):
        log_scales = estimate_log_scales(component, edges)
        all_log_scales.update(log_scales)
        ordered = sorted(component, key=lambda idx: log_scales[idx])
        clusters: list[list[int]] = []
        for idx in ordered:
            if not clusters:
                clusters.append([idx])
                continue
            previous = clusters[-1][-1]
            if log_scales[idx] - log_scales[previous] > gap:
                clusters.append([idx])
            else:
                clusters[-1].append(idx)
        for cluster in clusters:
            median_log = float(np.median([log_scales[i] for i in cluster]))
            groups.append(ObjectiveGroup(group_id, sorted(cluster), math.exp(median_log), component_id))
            group_id += 1
    groups.sort(key=lambda g: (g.relative_scale, -len(g.tile_indices)))
    for new_id, group in enumerate(groups, start=1):
        group.id = new_id
    return groups, all_log_scales

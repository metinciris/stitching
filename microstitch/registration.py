from .graph import *

def _to_homogeneous(matrix: np.ndarray) -> np.ndarray:
    return np.vstack((matrix, np.array([0.0, 0.0, 1.0])))


def _compose(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (_to_homogeneous(a) @ _to_homogeneous(b))[:2]


def _invert(matrix: np.ndarray) -> np.ndarray:
    return cv2.invertAffineTransform(matrix.astype(np.float64))


def _matrix_to_params(matrix: np.ndarray) -> np.ndarray:
    scale = max(1e-9, float(np.hypot(matrix[0, 0], matrix[1, 0])))
    theta = math.atan2(matrix[1, 0], matrix[0, 0])
    return np.array([math.log(scale), theta, matrix[0, 2], matrix[1, 2]], np.float64)


def _params_to_matrix(params: np.ndarray) -> np.ndarray:
    log_scale, theta, tx, ty = map(float, params)
    s = math.exp(log_scale)
    c, sn = math.cos(theta), math.sin(theta)
    return np.array([[s * c, -s * sn, tx], [s * sn, s * c, ty]], np.float64)


def _transform_points(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    return points @ matrix[:, :2].T + matrix[:, 2]


def initial_poses(indices: list[int], edges: list[MatchEdge], root: int) -> tuple[dict[int, np.ndarray], list[MatchEdge]]:
    allowed = set(indices)
    candidate = [e for e in edges if e.i in allowed and e.j in allowed]
    uf = UnionFind(indices)
    tree: list[MatchEdge] = []
    for edge in sorted(candidate, key=lambda e: -e.score):
        if uf.union(edge.i, edge.j):
            tree.append(edge)
    adjacency: dict[int, list[tuple[int, np.ndarray]]] = {i: [] for i in indices}
    for edge in tree:
        # M maps j -> i.  If pose(i) is known, pose(j) = pose(i) o M.
        adjacency[edge.i].append((edge.j, edge.matrix_j_to_i))
        adjacency[edge.j].append((edge.i, _invert(edge.matrix_j_to_i)))
    poses = {root: np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], np.float64)}
    queue = [root]
    while queue:
        current = queue.pop(0)
        for other, other_to_current in adjacency.get(current, []):
            if other in poses:
                continue
            poses[other] = _compose(poses[current], other_to_current)
            queue.append(other)
    return poses, tree


def _sample_correspondences(edge: MatchEdge, limit: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(edge.points_i)
    if n <= limit:
        return edge.points_i, edge.points_j
    # Spatially balanced grid sampling is more stable than taking the first points.
    pts = edge.points_i
    x_bins = np.linspace(pts[:, 0].min(), pts[:, 0].max() + 1e-6, 7)
    y_bins = np.linspace(pts[:, 1].min(), pts[:, 1].max() + 1e-6, 5)
    chosen: list[int] = []
    rng = np.random.default_rng(seed + edge.i * 997 + edge.j * 101)
    for xi in range(len(x_bins) - 1):
        for yi in range(len(y_bins) - 1):
            ids = np.where(
                (pts[:, 0] >= x_bins[xi]) & (pts[:, 0] < x_bins[xi + 1])
                & (pts[:, 1] >= y_bins[yi]) & (pts[:, 1] < y_bins[yi + 1])
            )[0]
            if len(ids):
                chosen.extend(rng.choice(ids, min(4, len(ids)), replace=False).tolist())
    chosen = list(dict.fromkeys(chosen))
    if len(chosen) < limit:
        remaining = np.setdiff1d(np.arange(n), np.asarray(chosen, int), assume_unique=False)
        extra = rng.choice(remaining, min(limit - len(chosen), len(remaining)), replace=False)
        chosen.extend(extra.tolist())
    chosen = chosen[:limit]
    return edge.points_i[chosen], edge.points_j[chosen]


def optimize_poses(
    indices: list[int],
    edges: list[MatchEdge],
    root: int | None = None,
    seed: int = 17,
) -> PoseSolution:
    if len(indices) == 1:
        idx = indices[0]
        identity = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], np.float64)
        return PoseSolution(indices, idx, {idx: identity}, [], [], 0.0)
    allowed = set(indices)
    available = [e for e in edges if e.i in allowed and e.j in allowed]
    if not available:
        raise RuntimeError("This objective group has no internal overlap edges.")
    if root is None:
        degree = {idx: 0.0 for idx in indices}
        for e in available:
            degree[e.i] += e.score
            degree[e.j] += e.score
        root = max(indices, key=lambda idx: degree[idx])
    initial, tree = initial_poses(indices, available, root)
    connected = sorted(initial)
    if len(connected) < len(indices):
        indices = connected
        allowed = set(indices)
        available = [e for e in available if e.i in allowed and e.j in allowed]

    variables = [idx for idx in indices if idx != root]
    offsets = {idx: 4 * k for k, idx in enumerate(variables)}
    x0 = np.concatenate([_matrix_to_params(initial[idx]) for idx in variables]) if variables else np.zeros(0)
    samples = {id(e): _sample_correspondences(e, 48, seed) for e in available}
    median_score = float(np.median([e.score for e in available])) or 1.0

    def matrix_for(x: np.ndarray, idx: int) -> np.ndarray:
        if idx == root:
            return np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], np.float64)
        off = offsets[idx]
        return _params_to_matrix(x[off:off + 4])

    def residual(x: np.ndarray, edge_list: list[MatchEdge]) -> np.ndarray:
        chunks: list[np.ndarray] = []
        for edge in edge_list:
            pi, pj = samples[id(edge)]
            gi = _transform_points(matrix_for(x, edge.i), pi)
            gj = _transform_points(matrix_for(x, edge.j), pj)
            weight = math.sqrt(float(np.clip(edge.score / median_score, 0.25, 4.0)))
            chunks.append((gi - gj).ravel() * weight)
        # Very light regularization prevents poorly constrained tiles from
        # drifting into shear-like scale/rotation extremes (model is similarity).
        if len(x0):
            reg = (x - x0).copy()
            for k in range(len(variables)):
                reg[4 * k + 2: 4 * k + 4] *= 0.0002
                reg[4 * k: 4 * k + 2] *= 0.03
            chunks.append(reg)
        return np.concatenate(chunks) if chunks else np.zeros(0)

    def jacobian_sparsity(edge_list: list[MatchEdge]):
        row_count = sum(2 * len(samples[id(e)][0]) for e in edge_list) + len(x0)
        pattern = lil_matrix((row_count, len(x0)), dtype=np.int8)
        row = 0
        for edge in edge_list:
            nrows = 2 * len(samples[id(edge)][0])
            for idx in (edge.i, edge.j):
                if idx != root:
                    off = offsets[idx]
                    pattern[row:row + nrows, off:off + 4] = 1
            row += nrows
        if len(x0):
            pattern[row:row + len(x0), :] = np.eye(len(x0), dtype=np.int8)
        return pattern.tocsr()

    result = least_squares(
        lambda x: residual(x, available),
        x0,
        jac_sparsity=jacobian_sparsity(available),
        loss="soft_l1",
        f_scale=2.0,
        max_nfev=90,
        verbose=0,
    )

    def edge_residuals(x: np.ndarray, edge_list: list[MatchEdge]) -> dict[int, float]:
        out = {}
        for edge in edge_list:
            pi, pj = samples[id(edge)]
            delta = _transform_points(matrix_for(x, edge.i), pi) - _transform_points(matrix_for(x, edge.j), pj)
            out[id(edge)] = float(np.median(np.linalg.norm(delta, axis=1)))
        return out

    residual_map = edge_residuals(result.x, available)
    values = np.array(list(residual_map.values()), np.float64)
    threshold = max(5.0, float(np.median(values) + 4.5 * (np.median(np.abs(values - np.median(values))) + 0.2)))
    kept = [e for e in available if residual_map[id(e)] <= threshold]
    rejected = [e for e in available if residual_map[id(e)] > threshold]
    if rejected and len(kept) >= len(indices) - 1:
        result = least_squares(
            lambda x: residual(x, kept), result.x,
            jac_sparsity=jacobian_sparsity(kept),
            loss="soft_l1", f_scale=1.8, max_nfev=60, verbose=0,
        )
    else:
        kept, rejected = available, []

    matrices = {root: np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], np.float64)}
    for idx in variables:
        matrices[idx] = matrix_for(result.x, idx)
    final_residuals = edge_residuals(result.x, kept) if kept else {}
    median_residual = float(np.median(list(final_residuals.values()))) if final_residuals else 0.0
    return PoseSolution(indices, root, matrices, kept, rejected, median_residual)

from .models import *

def _symmetric_matches(tile_i: Tile, tile_j: Tile, ratio: float) -> list[cv2.DMatch]:
    d1, d2 = tile_i.descriptors, tile_j.descriptors
    if d1 is None or d2 is None or len(d1) < 6 or len(d2) < 6:
        return []
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    try:
        raw12 = matcher.knnMatch(d1, d2, k=2)
        raw21 = matcher.knnMatch(d2, d1, k=2)
    except cv2.error:
        return []
    good12 = {
        pair[0].queryIdx: pair[0]
        for pair in raw12
        if len(pair) == 2 and pair[0].distance < ratio * pair[1].distance
    }
    good21 = {
        pair[0].queryIdx: pair[0]
        for pair in raw21
        if len(pair) == 2 and pair[0].distance < ratio * pair[1].distance
    }
    mutual: list[cv2.DMatch] = []
    for query, match in good12.items():
        reverse = good21.get(match.trainIdx)
        if reverse is not None and reverse.trainIdx == query:
            mutual.append(match)
    return mutual


def _mask_overlap_ratio(tile_i: Tile, tile_j: Tile, matrix_small: np.ndarray) -> float:
    hi, wi = tile_i.work_mask.shape
    warped = cv2.warpAffine(
        (tile_j.work_mask > 0).astype(np.uint8), matrix_small, (wi, hi),
        flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0,
    )
    mi = tile_i.work_mask > 0
    intersection = np.count_nonzero(mi & (warped > 0))
    denominator = max(1, min(np.count_nonzero(mi), np.count_nonzero(warped)))
    return float(intersection / denominator)


def match_pair(tile_i: Tile, tile_j: Tile, settings: StitchSettings) -> MatchEdge | None:
    matches = _symmetric_matches(tile_i, tile_j, settings.ratio_test)
    if len(matches) < max(8, settings.min_inliers // 2):
        return None
    points_i_small = np.float32([tile_i.keypoints[m.queryIdx].pt for m in matches])
    points_j_small = np.float32([tile_j.keypoints[m.trainIdx].pt for m in matches])
    matrix_small, inlier_mask = cv2.estimateAffinePartial2D(
        points_j_small,
        points_i_small,
        method=cv2.RANSAC,
        ransacReprojThreshold=settings.ransac_threshold,
        maxIters=7000,
        confidence=0.999,
        refineIters=30,
    )
    if matrix_small is None or inlier_mask is None:
        return None
    inliers = inlier_mask.ravel().astype(bool)
    inlier_count = int(np.count_nonzero(inliers))
    if inlier_count < settings.min_inliers:
        return None
    ratio = inlier_count / max(len(matches), 1)
    if ratio < settings.min_inlier_ratio:
        return None
    predicted = cv2.transform(points_j_small.reshape(-1, 1, 2), matrix_small).reshape(-1, 2)
    errors = np.linalg.norm(predicted - points_i_small, axis=1)
    median_error = float(np.median(errors[inliers]))
    if median_error > settings.max_pair_error:
        return None

    scale_small = float(np.hypot(matrix_small[0, 0], matrix_small[1, 0]))
    true_scale = scale_small * (tile_j.work_scale / tile_i.work_scale)
    if not (0.18 <= true_scale <= 5.5):
        return None
    rotation = math.degrees(math.atan2(matrix_small[1, 0], matrix_small[0, 0]))
    if abs(rotation) > 45.0:
        return None

    overlap = _mask_overlap_ratio(tile_i, tile_j, matrix_small)
    if overlap < 0.02:
        return None

    inlier_i = points_i_small[inliers]
    inlier_j = points_j_small[inliers]
    span = np.ptp(inlier_i, axis=0) if len(inlier_i) else np.array([0.0, 0.0])
    span_x = float(span[0] / max(tile_i.work_image.shape[1], 1))
    span_y = float(span[1] / max(tile_i.work_image.shape[0], 1))
    if min(span_x, span_y) < 0.035 and inlier_count < 80:
        return None

    # Convert matched points and transform to each cropped tile's full resolution.
    points_i = inlier_i / tile_i.work_scale
    points_j = inlier_j / tile_j.work_scale
    a = matrix_small[:, :2] * (tile_j.work_scale / tile_i.work_scale)
    t = matrix_small[:, 2:3] / tile_i.work_scale
    matrix = np.hstack((a, t)).astype(np.float64)

    spread = max(0.05, math.sqrt(max(span_x * span_y, 0.0)))
    score = (
        inlier_count
        * math.sqrt(max(ratio, 1e-6))
        * math.sqrt(max(overlap, 0.01))
        * spread
        / (0.6 + median_error)
    )
    return MatchEdge(
        i=tile_i.index,
        j=tile_j.index,
        matrix_j_to_i=matrix,
        points_i=points_i.astype(np.float64),
        points_j=points_j.astype(np.float64),
        inlier_count=inlier_count,
        match_count=len(matches),
        inlier_ratio=float(ratio),
        median_error=median_error,
        scale=true_scale,
        rotation_deg=rotation,
        overlap_ratio=overlap,
        span_x=span_x,
        span_y=span_y,
        score=float(score),
    )

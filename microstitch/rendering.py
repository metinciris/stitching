from .photometric import *
from .registration import _transform_points, _compose
from .models import _noop_progress

def _canvas_geometry(tiles: list[Tile], indices: list[int], poses: dict[int, np.ndarray]) -> tuple[np.ndarray, int, int, dict[int, np.ndarray]]:
    corners_all = []
    for idx in indices:
        h, w = tiles[idx].image.shape[:2]
        corners = np.array([[0.0, 0.0], [w, 0.0], [w, h], [0.0, h]], np.float64)
        corners_all.append(_transform_points(poses[idx], corners))
    combined = np.vstack(corners_all)
    min_xy = np.floor(combined.min(axis=0))
    max_xy = np.ceil(combined.max(axis=0))
    shift = np.array([[1.0, 0.0, -min_xy[0] + 2.0], [0.0, 1.0, -min_xy[1] + 2.0]], np.float64)
    width = int(max_xy[0] - min_xy[0] + 5)
    height = int(max_xy[1] - min_xy[1] + 5)
    shifted = {idx: _compose(shift, poses[idx]) for idx in indices}
    return shift, width, height, shifted


def _warp_bbox(image_shape: tuple[int, int], matrix: np.ndarray) -> tuple[int, int, int, int]:
    h, w = image_shape
    corners = np.array([[0.0, 0.0], [w, 0.0], [w, h], [0.0, h]], np.float64)
    q = _transform_points(matrix, corners)
    x0, y0 = np.floor(q.min(axis=0)).astype(int)
    x1, y1 = np.ceil(q.max(axis=0)).astype(int)
    return int(x0), int(y0), max(1, int(x1 - x0)), max(1, int(y1 - y0))


def _warp_local(source: np.ndarray, matrix: np.ndarray, bbox: tuple[int, int, int, int], interpolation: int, border_value) -> np.ndarray:
    x, y, w, h = bbox
    local = matrix.copy()
    local[:, 2] -= np.array([x, y])
    return cv2.warpAffine(
        source, local, (w, h), flags=interpolation,
        borderMode=cv2.BORDER_CONSTANT, borderValue=border_value,
    )


def _seam_masks(
    tiles: list[Tile],
    indices: list[int],
    transforms: dict[int, np.ndarray],
    canvas_w: int,
    canvas_h: int,
    settings: StitchSettings,
) -> tuple[dict[int, np.ndarray], dict[int, tuple[int, int, int, int]], float]:
    scale = min(1.0, settings.seam_max_dim / max(canvas_w, canvas_h))
    scaled_transforms: dict[int, np.ndarray] = {}
    seam_images: list[np.ndarray] = []
    seam_masks: list[np.ndarray] = []
    corners: list[tuple[int, int]] = []
    bboxes: dict[int, tuple[int, int, int, int]] = {}
    ordered = list(indices)

    for idx in ordered:
        matrix = transforms[idx].copy()
        matrix[:, :2] *= scale
        matrix[:, 2] *= scale
        scaled_transforms[idx] = matrix
        bbox = _warp_bbox(tiles[idx].image.shape[:2], matrix)
        bboxes[idx] = bbox
        source = tiles[idx].corrected if tiles[idx].corrected is not None else tiles[idx].image
        warped = _warp_local(source, matrix, bbox, cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR, (255, 255, 255))
        mask = _warp_local(tiles[idx].mask, matrix, bbox, cv2.INTER_NEAREST, 0)
        seam_images.append(warped.astype(np.float32))
        seam_masks.append(mask.astype(np.uint8))
        corners.append((bbox[0], bbox[1]))

    mode = settings.seam_mode.lower()
    if mode == "graphcut" and len(ordered) > 1:
        try:
            finder = cv2.detail_GraphCutSeamFinder("COST_COLOR_GRAD")
            found = finder.find(seam_images, corners, seam_masks)
            if found is not None:
                seam_masks = list(found)
        except cv2.error:
            mode = "voronoi"
    if mode == "voronoi" and len(ordered) > 1:
        try:
            finder = cv2.detail_VoronoiSeamFinder()
            found = finder.find(seam_images, corners, seam_masks)
            if found is not None:
                seam_masks = list(found)
        except cv2.error:
            mode = "crisp"
    if mode == "crisp":
        # Priority winner: field-centre distance * focus.  This is deterministic
        # and never averages two nuclei, even when graph-cut is unavailable.
        sw = max(1, int(math.ceil(canvas_w * scale)))
        sh = max(1, int(math.ceil(canvas_h * scale)))
        best = np.zeros((sh, sw), np.float32)
        labels = np.full((sh, sw), -1, np.int16)
        focus_values = np.array([tiles[i].focus_score for i in ordered], np.float64)
        focus_med = float(np.median(focus_values[focus_values > 0])) if np.any(focus_values > 0) else 1.0
        for label, idx in enumerate(ordered):
            bbox = bboxes[idx]
            mask = seam_masks[label]
            distance = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 5)
            quality = float(np.clip(tiles[idx].focus_score / max(focus_med, 1e-6), 0.65, 1.45))
            priority = distance * quality
            x, y, w, h = bbox
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(sw, x + w), min(sh, y + h)
            if x1 <= x0 or y1 <= y0:
                continue
            sx0, sy0 = x0 - x, y0 - y
            sx1, sy1 = sx0 + (x1 - x0), sy0 + (y1 - y0)
            region = priority[sy0:sy1, sx0:sx1]
            win = region > best[y0:y1, x0:x1]
            best[y0:y1, x0:x1][win] = region[win]
            labels[y0:y1, x0:x1][win] = label
        for label, idx in enumerate(ordered):
            x, y, w, h = bboxes[idx]
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(sw, x + w), min(sh, y + h)
            out = np.zeros((h, w), np.uint8)
            if x1 > x0 and y1 > y0:
                sx0, sy0 = x0 - x, y0 - y
                sx1, sy1 = sx0 + (x1 - x0), sy0 + (y1 - y0)
                out[sy0:sy1, sx0:sx1] = (labels[y0:y1, x0:x1] == label).astype(np.uint8) * 255
            seam_masks[label] = out

    return {idx: seam_masks[k] for k, idx in enumerate(ordered)}, bboxes, scale


def render_mosaic(
    tiles: list[Tile],
    solution: PoseSolution,
    settings: StitchSettings,
    progress: ProgressFn = _noop_progress,
) -> RenderedMosaic:
    indices = solution.tile_indices
    shift, width, height, transforms = _canvas_geometry(tiles, indices, solution.matrices)
    megapixels = width * height / 1_000_000.0
    if megapixels > settings.max_canvas_megapixels:
        raise MemoryError(
            f"Canvas would be {width}x{height} ({megapixels:.1f} MP), above the configured "
            f"{settings.max_canvas_megapixels:.1f} MP in-memory limit."
        )
    seam_masks, seam_bboxes, seam_scale = _seam_masks(tiles, indices, transforms, width, height, settings)

    try:
        blender = cv2.detail_MultiBandBlender()
        blender.setNumBands(max(1, settings.blend_bands))
        blender.prepare((0, 0, width, height))
        method = f"{settings.seam_mode}+multiband{settings.blend_bands}"
        for k, idx in enumerate(indices):
            matrix = transforms[idx]
            bbox = _warp_bbox(tiles[idx].image.shape[:2], matrix)
            source = tiles[idx].corrected if tiles[idx].corrected is not None else tiles[idx].image
            warped = _warp_local(source, matrix, bbox, cv2.INTER_LANCZOS4, (255, 255, 255))
            field = _warp_local(tiles[idx].mask, matrix, bbox, cv2.INTER_NEAREST, 0)
            seam = cv2.resize(seam_masks[idx], (bbox[2], bbox[3]), interpolation=cv2.INTER_NEAREST)
            mask = cv2.bitwise_and(field, seam)
            # A tiny dilation gives the pyramid blender a narrow transition zone;
            # unlike alpha feathering it does not average the entire overlap.
            mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))
            blender.feed(warped.astype(np.int16), mask, (bbox[0], bbox[1]))
            progress("render", (k + 1) / len(indices), f"Rendered tile {k + 1}/{len(indices)}")
        result, coverage = blender.blend(None, None)
        result = np.clip(result, 0, 255).astype(np.uint8)
        coverage = coverage.astype(np.uint8)
    except cv2.error:
        # Deterministic fallback: hard winner masks, no wide blending.
        method = "crisp-fallback"
        result = np.full((height, width, 3), 255, np.uint8)
        coverage = np.zeros((height, width), np.uint8)
        for k, idx in enumerate(indices):
            matrix = transforms[idx]
            bbox = _warp_bbox(tiles[idx].image.shape[:2], matrix)
            source = tiles[idx].corrected if tiles[idx].corrected is not None else tiles[idx].image
            warped = _warp_local(source, matrix, bbox, cv2.INTER_LANCZOS4, (255, 255, 255))
            field = _warp_local(tiles[idx].mask, matrix, bbox, cv2.INTER_NEAREST, 0)
            seam = cv2.resize(seam_masks[idx], (bbox[2], bbox[3]), interpolation=cv2.INTER_NEAREST)
            mask = (cv2.bitwise_and(field, seam) > 0)
            x, y, w, h = bbox
            result[y:y + h, x:x + w][mask] = warped[mask]
            coverage[y:y + h, x:x + w][mask] = 255
            progress("render", (k + 1) / len(indices), f"Rendered tile {k + 1}/{len(indices)}")

    result[coverage == 0] = 255
    points = cv2.findNonZero((coverage > 0).astype(np.uint8))
    if points is not None:
        x, y, w, h = cv2.boundingRect(points)
        result = result[y:y + h, x:x + w]
        coverage = coverage[y:y + h, x:x + w]
        crop_shift = np.array([[1.0, 0.0, -x], [0.0, 1.0, -y]], np.float64)
        transforms = {idx: _compose(crop_shift, matrix) for idx, matrix in transforms.items()}
        shift = _compose(crop_shift, shift)

    scales = [float(np.hypot(transforms[i][0, 0], transforms[i][1, 0])) for i in indices]
    native_scale = float(np.median(scales)) if scales else 1.0
    return RenderedMosaic(result, coverage, transforms, shift, list(indices), native_scale, method)

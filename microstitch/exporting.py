from .rendering import *
from .registration import _transform_points, _compose
from .matching import _symmetric_matches


def align_mosaic_to_mosaic(high: RenderedMosaic, low: RenderedMosaic, settings: StitchSettings) -> np.ndarray | None:
    """Return transform mapping low mosaic coordinates into high mosaic coordinates."""
    max_dim = settings.work_max_dim

    def prep(image, coverage):
        h, w = image.shape[:2]
        s = min(1.0, max_dim / max(h, w))
        size = (max(8, int(w * s)), max(8, int(h * s)))
        small = cv2.resize(image, size, interpolation=cv2.INTER_AREA) if s < 1 else image
        mask = cv2.resize(coverage, size, interpolation=cv2.INTER_NEAREST) if s < 1 else coverage
        lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB)
        det = cv2.createCLAHE(2.2, (8, 8)).apply(255 - lab[:, :, 0])
        return det, mask, s

    a, ma, sa = prep(high.image, high.coverage)
    b, mb, sb = prep(low.image, low.coverage)
    sift = cv2.SIFT_create(nfeatures=5000, contrastThreshold=0.012, edgeThreshold=18)
    kpa, da = sift.detectAndCompute(a, ma)
    kpb, db = sift.detectAndCompute(b, mb)
    if da is None or db is None:
        return None
    ta = Tile(0, "", "", high.image, high.coverage, (0, 0), high.image, high.coverage, a, ma, sa, 1, np.ones(3), kpa, da)
    tb = Tile(1, "", "", low.image, low.coverage, (0, 0), low.image, low.coverage, b, mb, sb, 1, np.ones(3), kpb, db)
    matches = _symmetric_matches(ta, tb, 0.80)
    if len(matches) < 20:
        return None
    pa = np.float32([kpa[m.queryIdx].pt for m in matches])
    pb = np.float32([kpb[m.trainIdx].pt for m in matches])
    matrix_small, inliers = cv2.estimateAffinePartial2D(
        pb,
        pa,
        method=cv2.RANSAC,
        ransacReprojThreshold=4.0,
        maxIters=10000,
        confidence=0.999,
    )
    if matrix_small is None or inliers is None or int(inliers.sum()) < 15:
        return None
    matrix = np.hstack((matrix_small[:, :2] * (sb / sa), matrix_small[:, 2:3] / sa)).astype(np.float64)
    return matrix


def make_hybrid(high: RenderedMosaic, low: RenderedMosaic, transform_low_to_high: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Place lower-resolution overview underneath high-resolution data.

    The native high-resolution pixels are never averaged over a broad overlap.
    A separate resolution map records where the overview had to fill gaps.
    """
    high_h, high_w = high.image.shape[:2]
    low_h, low_w = low.image.shape[:2]
    high_corners = np.array([[0, 0], [high_w, 0], [high_w, high_h], [0, high_h]], np.float64)
    low_corners = _transform_points(
        transform_low_to_high,
        np.array([[0, 0], [low_w, 0], [low_w, low_h], [0, low_h]], np.float64),
    )
    all_corners = np.vstack((high_corners, low_corners))
    min_xy = np.floor(all_corners.min(axis=0))
    max_xy = np.ceil(all_corners.max(axis=0))
    shift = np.array([[1.0, 0.0, -min_xy[0] + 2], [0.0, 1.0, -min_xy[1] + 2]], np.float64)
    width = int(max_xy[0] - min_xy[0] + 5)
    height = int(max_xy[1] - min_xy[1] + 5)
    low_matrix = _compose(shift, transform_low_to_high)
    high_matrix = shift
    low_warp = cv2.warpAffine(low.image, low_matrix, (width, height), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
    low_mask = cv2.warpAffine(low.coverage, low_matrix, (width, height), flags=cv2.INTER_NEAREST)
    high_warp = cv2.warpAffine(high.image, high_matrix, (width, height), flags=cv2.INTER_LANCZOS4, borderValue=(255, 255, 255))
    high_mask = cv2.warpAffine(high.coverage, high_matrix, (width, height), flags=cv2.INTER_NEAREST)

    output = low_warp.copy()
    output[low_mask == 0] = 255
    interior = cv2.erode(high_mask, np.ones((7, 7), np.uint8))
    edge = (high_mask > 0) & (interior == 0)
    output[interior > 0] = high_warp[interior > 0]
    if np.any(edge):
        dist = cv2.distanceTransform((high_mask > 0).astype(np.uint8), cv2.DIST_L2, 5)
        alpha = np.clip(dist / 5.0, 0.0, 1.0)[:, :, None]
        blended = high_warp.astype(np.float32) * alpha + output.astype(np.float32) * (1.0 - alpha)
        output[edge] = np.clip(blended[edge], 0, 255).astype(np.uint8)

    resolution_map = np.zeros((height, width), np.uint8)
    resolution_map[low_mask > 0] = 96
    resolution_map[high_mask > 0] = 255
    coverage = np.maximum(low_mask, high_mask)
    points = cv2.findNonZero((coverage > 0).astype(np.uint8))
    if points is not None:
        x, y, w, h = cv2.boundingRect(points)
        output = output[y:y + h, x:x + w]
        resolution_map = resolution_map[y:y + h, x:x + w]
    return output, resolution_map


def save_pyramidal_tiff(path: str, image_bgr: np.ndarray, tile_size: int = 512) -> None:
    if tifffile is None:
        raise RuntimeError("tifffile is required for pyramidal TIFF output.")
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    levels = [rgb]
    while min(levels[-1].shape[:2]) > 512:
        previous = levels[-1]
        next_level = cv2.resize(
            previous,
            (max(1, previous.shape[1] // 2), max(1, previous.shape[0] // 2)),
            interpolation=cv2.INTER_AREA,
        )
        levels.append(next_level)
    with tifffile.TiffWriter(path, bigtiff=True) as tif:
        tif.write(
            levels[0],
            photometric="rgb",
            tile=(tile_size, tile_size),
            compression="deflate",
            subifds=len(levels) - 1,
            metadata={"axes": "YXS"},
        )
        for level in levels[1:]:
            tif.write(level, photometric="rgb", tile=(tile_size, tile_size), compression="deflate", subfiletype=1)


def save_image_outputs(base_path: str, image: np.ndarray, settings: StitchSettings) -> dict[str, str]:
    base = Path(base_path)
    base.parent.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}
    if settings.save_png:
        png = str(base.with_suffix(".png"))
        cv2.imwrite(png, image, [cv2.IMWRITE_PNG_COMPRESSION, 3])
        outputs["png"] = png
    if settings.save_preview:
        h, w = image.shape[:2]
        scale = min(1.0, settings.preview_max_dim / max(h, w))
        preview = (
            cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
            if scale < 1
            else image
        )
        jpg = str(base) + "_preview.jpg"
        cv2.imwrite(jpg, preview, [cv2.IMWRITE_JPEG_QUALITY, 94])
        outputs["preview"] = jpg
    if settings.save_pyramidal_tiff:
        tif = str(base.with_suffix(".ome.tif"))
        save_pyramidal_tiff(tif, image)
        outputs["pyramidal_tiff"] = tif
    return outputs

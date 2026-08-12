from .registration import *

def _smoothstep(values: np.ndarray, low: float, high: float) -> np.ndarray:
    t = np.clip((values - low) / max(high - low, 1e-6), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _flatten_single_tile_background(image: np.ndarray, mask: np.ndarray, target_l: float = 251.0) -> np.ndarray:
    """Fit a low-order illumination surface from bright neutral background.

    Only luminance receives a spatial correction; chroma gets at most a small
    global neutralisation.  A final highlight-only soft white mapping removes
    visible eyepiece discs without erasing pale eosin/collagen.
    """
    lab = cv2.cvtColor(np.clip(image, 0, 255).astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
    lch = lab[:, :, 0]
    a = lab[:, :, 1] - 128.0
    b = lab[:, :, 2] - 128.0
    chroma = np.sqrt(a * a + b * b)
    valid = mask > 0
    if np.count_nonzero(valid) < 2000:
        out = np.clip(image, 0, 255).astype(np.uint8)
        out[~valid] = 255
        return out

    q = float(np.percentile(lch[valid], 66))
    background = valid & (lch >= q) & (chroma < 13.0)
    if np.count_nonzero(background) < 3500:
        q = float(np.percentile(lch[valid], 74))
        background = valid & (lch >= q) & (chroma < 21.0)
    yy, xx = np.nonzero(background)
    if len(xx) < 1000:
        out = np.clip(image, 0, 255).astype(np.uint8)
        out[~valid] = 255
        return out

    rng = np.random.default_rng(12345)
    if len(xx) > 50000:
        keep = rng.choice(len(xx), 50000, replace=False)
        xx, yy = xx[keep], yy[keep]
    h, w = lch.shape
    xn = (xx.astype(np.float64) / max(w - 1, 1)) * 2.0 - 1.0
    yn = (yy.astype(np.float64) / max(h - 1, 1)) * 2.0 - 1.0
    design = np.column_stack((np.ones_like(xn), xn, yn, xn * xn, xn * yn, yn * yn))
    values = lch[yy, xx].astype(np.float64)
    weights = np.ones(len(values), np.float64)
    coef = np.zeros(6, np.float64)
    for _ in range(4):
        root_w = np.sqrt(weights)
        coef, *_ = np.linalg.lstsq(design * root_w[:, None], values * root_w, rcond=None)
        residual = values - design @ coef
        mad = np.median(np.abs(residual - np.median(residual))) + 0.75
        weights = 1.0 / (1.0 + (residual / (2.5 * mad)) ** 2)

    grid_x = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
    grid_y = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
    surface = (
        coef[0] + coef[1] * grid_x + coef[2] * grid_y
        + coef[3] * grid_x * grid_x + coef[4] * grid_x * grid_y
        + coef[5] * grid_y * grid_y
    ).astype(np.float32)
    delta = np.clip(target_l - surface, -10.0, 28.0)
    lab[:, :, 0] = np.clip(lch + delta, 0, 255)

    # Small global white balance correction only; do not remap stain colours.
    bg_a = float(np.median(a[background]))
    bg_b = float(np.median(b[background]))
    lab[:, :, 1] = np.clip(lab[:, :, 1] - np.clip(bg_a, -7.0, 7.0), 0, 255)
    lab[:, :, 2] = np.clip(lab[:, :, 2] - np.clip(bg_b, -7.0, 7.0), 0, 255)
    corrected = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR).astype(np.float32)

    # Whiten only very bright, neutral and locally smooth pixels.  Tissue edges
    # and even pale collagen remain protected by chroma/gradient terms.
    lab2 = cv2.cvtColor(np.clip(corrected, 0, 255).astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
    l2 = lab2[:, :, 0]
    c2 = np.sqrt((lab2[:, :, 1] - 128.0) ** 2 + (lab2[:, :, 2] - 128.0) ** 2)
    gx = cv2.Sobel(l2, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(l2, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.GaussianBlur(np.sqrt(gx * gx + gy * gy), (0, 0), 1.2)
    whiten = (
        _smoothstep(l2, 244.0, 252.0)
        * (1.0 - _smoothstep(c2, 7.0, 19.0))
        * (1.0 - _smoothstep(grad, 4.0, 18.0))
        * valid.astype(np.float32)
    )
    whiten = cv2.GaussianBlur(whiten.astype(np.float32), (0, 0), 0.8)[:, :, None]
    corrected = corrected * (1.0 - whiten) + 255.0 * whiten
    corrected[~valid] = 255.0
    return np.clip(corrected, 0, 255).astype(np.uint8)


def normalize_group_colors(tiles: list[Tile], indices: list[int], settings: StitchSettings) -> None:
    """Gentle white-point + shared flat-field correction.

    A common spatial illumination profile is estimated from many stage positions,
    so tissue tends to move while the optical shading stays fixed.  Only a scalar
    spatial gain is used after channel white balancing, preserving H&E hue ratios.
    """
    target = float(settings.background_target)
    normalized: dict[int, np.ndarray] = {}
    standardized: list[np.ndarray] = []
    standardized_masks: list[np.ndarray] = []
    size = settings.flatfield_size

    for idx in indices:
        tile = tiles[idx]
        gains = np.clip(target / np.maximum(tile.white_point, 1.0), 0.88, 1.14)
        base = np.clip(tile.image.astype(np.float32) * gains[None, None, :], 0, 255)
        normalized[idx] = base
        small = cv2.resize(base, (size, size), interpolation=cv2.INTER_AREA)
        small_mask = cv2.resize(tile.mask, (size, size), interpolation=cv2.INTER_NEAREST) > 0
        arr = small.astype(np.float32)
        arr[~small_mask] = np.nan
        standardized.append(arr)
        standardized_masks.append(small_mask)

    stack = np.stack(standardized, axis=0)
    with np.errstate(all="ignore"):
        flat_rgb = np.nanpercentile(stack, settings.flatfield_percentile, axis=0)
    # Fill rare NaNs near truncated field boundaries.
    for c in range(3):
        channel = flat_rgb[:, :, c]
        valid = np.isfinite(channel)
        fill = float(np.nanmedian(channel)) if np.any(valid) else target
        channel[~valid] = fill
        channel = cv2.GaussianBlur(channel.astype(np.float32), (0, 0), sigmaX=size / 24.0)
        flat_rgb[:, :, c] = channel
    flat_luma = cv2.cvtColor(np.clip(flat_rgb, 0, 255).astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32)
    valid_flat = np.any(np.stack(standardized_masks, axis=0), axis=0)
    reference = float(np.percentile(flat_luma[valid_flat], 72)) if np.any(valid_flat) else target
    gain_map = np.clip(reference / np.maximum(flat_luma, 30.0), 0.86, 1.18)
    gain_map = 1.0 + settings.flatfield_strength * (gain_map - 1.0)

    for idx in indices:
        tile = tiles[idx]
        gain = cv2.resize(gain_map, (tile.image.shape[1], tile.image.shape[0]), interpolation=cv2.INTER_CUBIC)
        corrected = np.clip(normalized[idx] * gain[:, :, None], 0, 255)
        tile.corrected = _flatten_single_tile_background(corrected, tile.mask, target_l=251.0)

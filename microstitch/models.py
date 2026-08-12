from __future__ import annotations

import json
import math
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Iterable, Sequence

import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix

try:
    import tifffile
except Exception:  # optional until pyramidal TIFF is requested
    tifffile = None

ProgressFn = Callable[[str, float, str], None]


def _noop_progress(stage: str, fraction: float, message: str) -> None:
    return


@dataclass
class StitchSettings:
    work_max_dim: int = 750
    sift_features: int = 2600
    ratio_test: float = 0.78
    ransac_threshold: float = 3.0
    min_inliers: int = 16
    min_inlier_ratio: float = 0.22
    max_pair_error: float = 3.2
    all_pairs_limit: int = 30
    candidate_neighbors: int = 8
    objective_gap_ratio: float = 1.55
    same_objective_tolerance: float = 1.35
    background_target: int = 245
    flatfield_size: int = 384
    flatfield_percentile: float = 88.0
    flatfield_strength: float = 0.80
    seam_max_dim: int = 1500
    seam_mode: str = "graphcut"  # graphcut | voronoi | crisp
    blend_bands: int = 3
    max_canvas_megapixels: float = 220.0
    hybrid: bool = True
    save_png: bool = True
    save_pyramidal_tiff: bool = True
    save_preview: bool = True
    preview_max_dim: int = 2400
    deterministic_seed: int = 17


@dataclass
class Tile:
    index: int
    path: str
    name: str
    image: np.ndarray
    mask: np.ndarray
    crop_xy: tuple[int, int]
    work_image: np.ndarray
    work_mask: np.ndarray
    detect_image: np.ndarray
    feature_mask: np.ndarray
    work_scale: float
    focus_score: float
    white_point: np.ndarray
    keypoints: list = field(default_factory=list, repr=False)
    descriptors: np.ndarray | None = field(default=None, repr=False)
    corrected: np.ndarray | None = field(default=None, repr=False)


@dataclass
class MatchEdge:
    i: int
    j: int
    matrix_j_to_i: np.ndarray
    points_i: np.ndarray
    points_j: np.ndarray
    inlier_count: int
    match_count: int
    inlier_ratio: float
    median_error: float
    scale: float
    rotation_deg: float
    overlap_ratio: float
    span_x: float
    span_y: float
    score: float

    def to_json(self) -> dict:
        d = asdict(self)
        d["matrix_j_to_i"] = self.matrix_j_to_i.tolist()
        d["points_i"] = None
        d["points_j"] = None
        return d


@dataclass
class ObjectiveGroup:
    id: int
    tile_indices: list[int]
    relative_scale: float
    component_id: int


@dataclass
class PoseSolution:
    tile_indices: list[int]
    root: int
    matrices: dict[int, np.ndarray]
    used_edges: list[MatchEdge]
    rejected_edges: list[MatchEdge]
    median_residual: float


@dataclass
class RenderedMosaic:
    image: np.ndarray
    coverage: np.ndarray
    transforms: dict[int, np.ndarray]
    canvas_shift: np.ndarray
    source_indices: list[int]
    native_scale: float
    method: str


def filename_capture_key(path: str) -> tuple:
    name = os.path.basename(path)
    m = re.search(r"at\s+(\d+)\.(\d+)\.(\d+)(?:\s+\((\d+)\))?", name)
    if not m:
        return (name,)
    suffix = 0 if m.group(4) is None else int(m.group(4)) + 1
    return (*map(int, m.group(1, 2, 3)), suffix, name)


def _largest_component(binary: np.ndarray) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary.astype(np.uint8), 8)
    if n <= 1:
        return np.zeros(binary.shape, np.uint8)
    label = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return (labels == label).astype(np.uint8)


def detect_field_mask(image: np.ndarray) -> np.ndarray:
    """Detect the illuminated eyepiece field without filling exterior black arcs.

    The previous contour-fill pattern can turn a concave black eyepiece region into
    valid image data.  Here internal holes are filled only when they are not
    connected to *any* image border.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    center = gray[h // 4: 3 * h // 4, w // 4: 3 * w // 4]
    p90 = float(np.percentile(center, 90)) if center.size else 220.0
    threshold = float(np.clip(p90 * 0.32, 28, 90))
    bright = (gray > threshold).astype(np.uint8)

    k = max(5, int(min(h, w) * 0.008)) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, kernel)
    field = _largest_component(bright).astype(bool)
    if not np.any(field):
        return np.full((h, w), 255, np.uint8)

    inverse = (~field).astype(np.uint8)
    n, labels, _, _ = cv2.connectedComponentsWithStats(inverse, 8)
    border_labels = np.unique(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1])))
    external = np.isin(labels, border_labels)
    holes = (inverse > 0) & (~external)
    field |= holes

    erosion = max(5, int(min(h, w) * 0.015)) | 1
    field_u8 = field.astype(np.uint8) * 255
    field_u8 = cv2.erode(
        field_u8,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (erosion, erosion)),
    )
    return field_u8


def crop_to_field(image: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    points = cv2.findNonZero((mask > 0).astype(np.uint8))
    if points is None:
        return image.copy(), np.full(image.shape[:2], 255, np.uint8), (0, 0)
    x, y, w, h = cv2.boundingRect(points)
    return image[y:y + h, x:x + w].copy(), mask[y:y + h, x:x + w].copy(), (x, y)


def estimate_white_point(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    valid = mask > 0
    if not np.any(valid):
        return np.array([240.0, 240.0, 240.0], np.float32)
    gvals = gray[valid]
    q = float(np.percentile(gvals, 78))
    background = valid & (gray >= q) & (hsv[:, :, 1] < 55)
    if np.count_nonzero(background) < 1000:
        background = valid & (gray >= np.percentile(gvals, 88))
    vals = image[background]
    if vals.size == 0:
        vals = image[valid]
    return np.percentile(vals, 94, axis=0).astype(np.float32)


def make_feature_images(image: np.ndarray, mask: np.ndarray, max_dim: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
    h, w = image.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    size = (max(8, int(round(w * scale))), max(8, int(round(h * scale))))
    if scale < 1.0:
        work = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
        work_mask = cv2.resize(mask, size, interpolation=cv2.INTER_NEAREST)
    else:
        work, work_mask = image.copy(), mask.copy()

    lab = cv2.cvtColor(work, cv2.COLOR_BGR2LAB)
    inv_l = 255 - lab[:, :, 0]
    detect = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8)).apply(inv_l)

    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(work, cv2.COLOR_BGR2HSV)
    valid = work_mask > 0
    bg = float(np.percentile(gray[valid], 90)) if np.any(valid) else 235.0
    tissue = valid & ((gray < bg - 5.0) | (hsv[:, :, 1] > 12))
    tissue = cv2.morphologyEx(tissue.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    tissue = cv2.dilate(tissue, np.ones((5, 5), np.uint8))
    feature_mask = (tissue > 0).astype(np.uint8) * 255
    return work, work_mask, detect, feature_mask, scale


def focus_measure(image: np.ndarray, mask: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    valid = mask > 0
    if np.count_nonzero(valid) < 100:
        return 0.0
    lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
    values = lap[valid]
    # Robustly trim isolated JPEG ringing / dust peaks.
    limit = np.percentile(np.abs(values), 98)
    values = values[np.abs(values) <= limit]
    return float(np.var(values)) if values.size else 0.0


def load_tiles(paths: Sequence[str], settings: StitchSettings, progress: ProgressFn = _noop_progress) -> list[Tile]:
    tiles: list[Tile] = []
    for idx, path in enumerate(paths):
        image0 = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image0 is None:
            continue
        full_mask = detect_field_mask(image0)
        image, mask, crop_xy = crop_to_field(image0, full_mask)
        work, work_mask, detect, feature_mask, scale = make_feature_images(image, mask, settings.work_max_dim)
        tile = Tile(
            index=len(tiles),
            path=str(path),
            name=os.path.basename(str(path)),
            image=image,
            mask=mask,
            crop_xy=crop_xy,
            work_image=work,
            work_mask=work_mask,
            detect_image=detect,
            feature_mask=feature_mask,
            work_scale=scale,
            focus_score=focus_measure(work, feature_mask),
            white_point=estimate_white_point(image, mask),
        )
        tiles.append(tile)
        progress("load", (idx + 1) / max(len(paths), 1), f"Loaded {tile.name}")
    if len(tiles) < 2:
        raise ValueError("At least two readable images are required.")
    for new_idx, tile in enumerate(tiles):
        tile.index = new_idx
    return tiles


def extract_features(tiles: list[Tile], settings: StitchSettings, progress: ProgressFn = _noop_progress) -> None:
    cv2.setRNGSeed(settings.deterministic_seed)
    sift = cv2.SIFT_create(
        nfeatures=settings.sift_features,
        contrastThreshold=0.015,
        edgeThreshold=15,
        nOctaveLayers=4,
    )
    for k, tile in enumerate(tiles):
        kp, des = sift.detectAndCompute(tile.detect_image, tile.feature_mask)
        tile.keypoints = kp or []
        tile.descriptors = des
        progress("features", (k + 1) / len(tiles), f"Features: {tile.name} ({len(tile.keypoints)})")

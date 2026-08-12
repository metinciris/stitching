from .exporting import *
from .models import _noop_progress


def run_pipeline(
    paths: Sequence[str],
    output_dir: str,
    settings: StitchSettings | None = None,
    progress: ProgressFn = _noop_progress,
) -> dict:
    settings = settings or StitchSettings()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    ordered_paths = sorted([str(p) for p in paths], key=filename_capture_key)
    tiles = load_tiles(ordered_paths, settings, progress)
    extract_features(tiles, settings, progress)
    edges = find_pairwise_edges(tiles, settings, progress)
    groups, log_scales = detect_objective_groups(tiles, edges, settings)

    report: dict = {
        "settings": asdict(settings),
        "input_files": [t.path for t in tiles],
        "tiles": [
            {
                "index": t.index,
                "name": t.name,
                "shape": [int(x) for x in t.image.shape],
                "crop_xy": list(t.crop_xy),
                "focus_score": t.focus_score,
                "white_point_bgr": t.white_point.tolist(),
                "feature_count": len(t.keypoints),
                "estimated_log_scale": log_scales.get(t.index, 0.0),
            }
            for t in tiles
        ],
        "edges": [e.to_json() for e in edges],
        "groups": [],
        "outputs": {},
    }

    group_mosaics: list[tuple[ObjectiveGroup, RenderedMosaic]] = []
    for group_pos, group in enumerate(groups):
        indices = group.tile_indices
        normalize_group_colors(tiles, indices, settings)
        internal_edges = [e for e in edges if e.i in indices and e.j in indices]
        components = connected_components(indices, internal_edges)
        for component_pos, component in enumerate(components, start=1):
            if len(component) == 1:
                idx = component[0]
                identity = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], np.float64)
                solution = PoseSolution(component, idx, {idx: identity}, [], [], 0.0)
            else:
                solution = optimize_poses(component, internal_edges, seed=settings.deterministic_seed)
            mosaic = render_mosaic(tiles, solution, settings, progress)
            suffix = f"objective_{group.id}"
            if len(components) > 1:
                suffix += f"_component_{component_pos}"
            base = output / suffix
            outputs = save_image_outputs(str(base), mosaic.image, settings)
            group_mosaics.append((group, mosaic))
            report["groups"].append(
                {
                    "group_id": group.id,
                    "component": component_pos,
                    "relative_scale": group.relative_scale,
                    "tile_indices": component,
                    "tile_names": [tiles[i].name for i in component],
                    "pose_root": solution.root,
                    "median_registration_residual_px": solution.median_residual,
                    "used_edge_count": len(solution.used_edges),
                    "rejected_edge_count": len(solution.rejected_edges),
                    "render_method": mosaic.method,
                    "output_shape": list(mosaic.image.shape),
                    "outputs": outputs,
                }
            )
            report["outputs"][suffix] = outputs
        progress("groups", (group_pos + 1) / len(groups), f"Completed objective group {group.id}")

    # Hybrid rendering is intentionally optional. The highest-resolution group
    # keeps native pixels and the overview only fills uncovered regions.
    if settings.hybrid and len(group_mosaics) >= 2:
        sorted_mosaics = sorted(group_mosaics, key=lambda gm: gm[0].relative_scale)
        high_group, high = sorted_mosaics[0]
        low_group, low = max(sorted_mosaics[1:], key=lambda gm: gm[1].image.shape[0] * gm[1].image.shape[1])
        transform = align_mosaic_to_mosaic(high, low, settings)
        if transform is not None:
            hybrid, resolution_map = make_hybrid(high, low, transform)
            outputs = save_image_outputs(str(output / "hybrid_wsi"), hybrid, settings)
            map_path = str(output / "hybrid_resolution_map.png")
            cv2.imwrite(map_path, resolution_map)
            outputs["resolution_map"] = map_path
            report["outputs"]["hybrid_wsi"] = outputs
            report["hybrid"] = {
                "high_resolution_group": high_group.id,
                "overview_group": low_group.id,
                "overview_to_high_matrix": transform.tolist(),
                "outputs": outputs,
            }

    report_path = output / "stitch_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    report["report_path"] = str(report_path)
    progress("done", 1.0, "Stitching complete")
    return report

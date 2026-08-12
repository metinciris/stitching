# How MicroStitch Studio Evolved with AI Assistance

## A real-world case study in problem definition, failure analysis, and computational pathology engineering

MicroStitch Studio did not emerge from a single perfect prompt or a single algorithm. It evolved through repeated attempts on a real set of difficult smartphone-through-microscope H&E images, with the project author comparing outputs, identifying histologically important failures, and pushing several AI assistants to rethink the problem.

This document records that development journey because the process is as useful as the final code.

> **Important:** this is not a benchmark of ChatGPT, Claude, or Gemini. Different models were used with different prompts, context, iterations, and code states. The descriptions of the earlier attempts summarize the development sessions reported by the project author. The description of the final architecture is grounded in the code currently present in this repository.

---

## 1. The real problem was not “make a panorama”

The initial request sounded simple:

> Take many microscope photographs captured with a phone and combine them into one whole-slide-like image.

A generic image-stitching interpretation immediately suggests a conventional panorama pipeline: detect features, estimate transforms, warp one image toward another, and blend the overlaps.

That mental model is often good for landscapes. It is not automatically good for histopathology.

In microscope imaging:

- the optical system is largely fixed,
- the tissue slide moves,
- the field may have strong circular eyepiece borders,
- illumination and vignetting are tied to the optical system,
- repeated microscopic textures can produce convincing but wrong local matches,
- a registration error of only a few pixels can visibly duplicate nuclei,
- different objective magnifications may occur in the same folder,
- broad blending can create biologically implausible intermediate structures.

The decisive conceptual shift was therefore:

**Stop treating the task as a photographic panorama problem and treat it as a constrained 2D microscopy registration problem with photometric normalization and pathology-aware rendering.**

That reframing determined almost every successful architectural decision that followed.

---

## 2. The real dataset changed the engineering direction

The development process used a concrete set of overlapping H&E microscope photographs taken through an eyepiece with a smartphone.

This mattered enormously.

On synthetic examples, many algorithms can look convincing. On real histology, failure becomes obvious at the level that matters:

- one nucleus becomes two,
- a gland edge becomes blurred,
- the white slide background changes from field to field,
- a circular eyepiece shadow survives into the mosaic,
- color balance changes between neighboring tiles,
- the first and last tiles drift apart after many sequential registrations.

The project therefore evolved by testing **visible pathological failure modes**, not only by asking whether an algorithm completed without errors.

The included [`sample/`](../sample/) directory preserves this philosophy: source images and generated outputs are part of the repository so future changes can be judged against a real case.

---

# 3. Three AI-assisted approaches

## Gemini: useful local fixes, but initially a panorama-style architecture

The Gemini-assisted iterations were valuable because they attacked several immediately visible defects:

- black eyepiece borders,
- brightness inconsistency,
- color loss,
- visible seams,
- basic blending behavior.

The early approach relied on techniques such as masking, per-image color/white-balance correction, and alpha-feathering. These are reasonable tools, and several of them remain useful concepts in a mature pipeline.

The problem was not that these individual techniques were “bad.” The problem was that they were being asked to compensate for a deeper registration architecture that was still fundamentally sequential.

If image B is placed relative to A, C relative to B, D relative to C, and so on, small errors accumulate. Once the global geometry is wrong, adding a better feather, another brightness correction, or a more complicated mask cannot fully repair the underlying drift.

### What the Gemini iterations contributed

They helped make the failure modes concrete and visible:

- wide alpha blending is dangerous when nuclei are even slightly misregistered,
- per-image correction can create new between-image inconsistency,
- optical borders must be handled explicitly,
- a visually smooth seam is not necessarily a histologically correct seam.

That is an important engineering lesson: an unsuccessful implementation can still provide excellent diagnostic information about the problem.

---

## Claude: local registration was not enough; global consistency was the missing layer

In a later independent attempt, Claude used a more structured registration strategy, including a graph/tree style initial organization and local refinement. According to the project author's development discussion, this was still insufficient because there was no mechanism strong enough to make all tile relationships globally consistent at the same time.

After reviewing the completed repository, Claude correctly identified the architectural difference:

- a spanning-tree or sequential solution can initialize positions,
- but it cannot by itself remove cumulative drift,
- all reliable overlap constraints need to participate in a global optimization.

Claude also highlighted the importance of:

- mutual/symmetric feature matching,
- rejecting geometrically weak overlaps,
- global pose optimization,
- graph-cut seam selection,
- multiband blending,
- group-based photometric correction.

### What the Claude review contributed

Its strongest contribution was an **independent architectural audit** of the final system.

It recognized that the quality difference was not caused by a single magic OpenCV function. It was caused by the pipeline structure: local evidence is collected first, then globally reconciled, then rendered conservatively.

That independent convergence was useful validation of the final design.

---

## ChatGPT: iterative reframing from “stitch images” to a microscopy registration pipeline

The ChatGPT-assisted development path became successful after repeatedly using the real images to challenge the assumptions of the previous implementation.

The key change was not “use a more powerful stitcher.” It was to decompose the problem into separate layers and solve each layer according to the physics and pathology of the acquisition.

### Step 1 — Inspect the image set before forcing a model onto it

The image set was analyzed for:

- overlap structure,
- relative scale,
- possible objective changes,
- illumination variation,
- invalid eyepiece borders,
- resolution differences.

A crucial observation was that not every image necessarily belonged to the same magnification group.

That led to a rule that remains central to the project:

**Different objective magnifications should not be blindly blended into the same native-resolution layer.**

### Step 2 — Separate geometry from appearance

Several early implementations tried to solve alignment, color, and seam visibility at the same time.

The successful pipeline separates them:

1. determine which tiles genuinely overlap,
2. estimate constrained pairwise geometry,
3. solve the global layout,
4. normalize illumination/color within the group,
5. render once at full resolution,
6. choose seams and blend only where needed.

This separation made debugging much easier. If nuclei were doubled, the problem was registration or seam selection—not “color.” If the tissue geometry was correct but the background showed circles, the problem was photometric/background handling—not the pose graph.

### Step 3 — Constrain the transform model to the acquisition

The project favors a similarity / partial-affine style model:

- translation,
- rotation,
- uniform scale.

It does not default to unrestricted projective warping.

This matters because the microscope stage is not a free-moving handheld camera photographing a 3D scene. Aggressive homography can make a panorama look smoother while subtly deforming microscopic tissue.

### Step 4 — Build reliable pairwise evidence

The current [`microstitch/matching.py`](../microstitch/matching.py) performs symmetric feature matching and then validates candidate pairs using multiple signals, including:

- Lowe-style descriptor filtering,
- mutual agreement in both matching directions,
- RANSAC partial-affine estimation,
- minimum inlier count,
- inlier ratio,
- median registration error,
- scale limits,
- rotation limits,
- valid-mask overlap,
- spatial spread of inliers.

This is intentionally stricter than accepting a pair because it has “enough SIFT matches.”

In histology, many local structures look similar. A strong match should be supported across a meaningful area of the field.

### Step 5 — Use a tree only as an initialization, not as the final answer

The current [`microstitch/registration.py`](../microstitch/registration.py) uses high-quality edges to obtain an initial connected layout.

But that layout is only the starting point.

The final poses are optimized with `scipy.optimize.least_squares`, using all retained overlap constraints together. Each tile is represented by a constrained 2D pose, and the optimizer minimizes disagreement between matched points in global coordinates.

A robust loss is used, suspicious edges are detected from residuals, outliers can be removed, and the system is optimized again.

This is the core mechanism that prevents a long chain of small local errors from becoming a large global drift.

It is best described as **bundle-adjustment-like global 2D pose optimization** rather than classical photogrammetric bundle adjustment, because the system optimizes 2D tile poses and 2D correspondences rather than 3D scene structure and camera intrinsics.

### Step 6 — Model illumination as an optical-system property

The current [`microstitch/photometric.py`](../microstitch/photometric.py) does not aggressively “beautify” every tile independently.

Instead, tiles within an objective group contribute to a shared flat-field / illumination estimate.

This follows the acquisition physics:

- tissue content moves from field to field,
- optical shading tends to remain fixed relative to the microscope/phone system.

The correction is deliberately conservative. Spatial correction is mainly luminance-based, and chromatic changes are limited so H&E relationships are not unnecessarily remapped.

### Step 7 — Do not average two nuclei across a wide overlap

The current [`microstitch/rendering.py`](../microstitch/rendering.py) uses seam-based rendering rather than broad alpha averaging across the complete overlap.

The preferred path combines:

- `cv2.detail_GraphCutSeamFinder`,
- a narrow transition region,
- `cv2.detail_MultiBandBlender`,
- full-resolution Lanczos warping.

A deterministic crisp fallback is also available.

This matters because the goal is not merely to hide a seam from the eye. The goal is to avoid creating an artificial average of two slightly displaced nuclei.

### Step 8 — Make the engineering usable

A technically good core is not enough if a pathologist cannot use it easily.

The project therefore also evolved into a desktop workflow with:

- drag-and-drop,
- image/folder selection,
- quality presets,
- output directory selection,
- progress information,
- preview,
- PNG / OME-TIFF export,
- JSON quality reporting,
- readable defaults.

The main README now deliberately presents the workflow in three steps.

---

# 4. What actually survived into the successful architecture

| Problem | Early/local approach | What worked better in the final architecture |
|---|---|---|
| Sequential drift | chain tiles one after another | global pose optimization using many overlap constraints |
| False feature matches | descriptor count alone | symmetric matches + RANSAC + overlap + spatial-spread checks |
| Different magnifications | force into one panorama | detect/separate objective-scale groups |
| Uneven background | independent per-image white balance | shared group illumination model + conservative local background correction |
| Double nuclei in overlap | broad alpha feathering | graph-cut / crisp seam ownership + narrow multiband transition |
| Repeated resampling | grow and re-warp a canvas repeatedly | estimate poses first, render original tiles into final coordinates |
| Eyepiece artifacts | fixed circular crop/mask | valid-field masking tied to actual image content |
| “Looks smooth” but wrong | visual seam quality only | evaluate geometry at nuclear/tissue level and report registration residuals |
| Hard-to-debug pipeline | geometry, color, blending mixed together | explicit stages: matching → registration → photometric correction → rendering → export |

---

# 5. The problem-solving techniques that mattered most

## 5.1 Reframe the problem before optimizing the code

The biggest improvement came from changing the question.

Instead of:

> “How do we make a better panorama?”

we asked:

> “What physical transformations are actually plausible when a microscope field is moved under a mostly fixed optical system?”

That immediately reduced the model space and discouraged unnecessary geometric distortion.

## 5.2 Let real failures decide what to work on next

The project did not progress by adding features for their own sake.

Each iteration was judged against concrete failure modes:

- doubled nuclei,
- wrong overlap,
- drift,
- white-background discontinuity,
- color shift,
- visible eyepiece circles,
- loss of resolution.

This prevented premature optimization of parts that were not actually limiting result quality.

## 5.3 Fix upstream geometry before downstream cosmetics

A common mistake is to attack visible seams first.

But if the geometry is wrong, blending only hides the error.

The successful order was:

**matching → global geometry → photometry → seam selection → final appearance.**

## 5.4 Prefer global consistency over a sequence of locally good decisions

A pairwise transform can be excellent and the complete mosaic can still be wrong.

The pose graph makes every accepted overlap a constraint on the same global system. That changes the problem from “where should the next tile go?” to “what arrangement best satisfies the whole network?”

## 5.5 Use domain knowledge as an engineering constraint

The pathology context was not decoration; it changed the algorithms.

Examples:

- duplicated nuclei are unacceptable even if a blend looks smooth,
- H&E color ratios should not be casually remapped,
- pale collagen should not be mistaken for blank background,
- different objectives should not be casually mixed,
- non-rigid deformation should not be introduced without strong evidence.

## 5.6 Preserve a scientifically interpretable output

AI-based image enhancement can make a stitched image more attractive for presentation. The repository includes an optional example.

But the core stitch should remain separate and non-generative.

A scientific workflow should preserve the geometrically registered source-derived result so later enhancement cannot be confused with original microscopic information.

## 5.7 Make the result reproducible

The project exports a `stitch_report.json` containing processing settings and registration information.

This turns “the image looks better” into something that future contributors can inspect, compare, and debug.

---

# 6. Why “hundreds of photos in seconds” is not the primary roadmap

Gemini suggested GPU/CUDA or other acceleration for stitching hundreds of images very quickly.

That is a valid computer-vision optimization problem, but it is not currently the main product goal.

MicroStitch Studio is aimed at a realistic manual workflow: a pathologist, trainee, educator, or low-resource laboratory captures a **manageable set of overlapping fields** with a phone and microscope.

Human acquisition time matters more than theoretical algorithm throughput. Most users will not want to manually capture hundreds of fields for a single mosaic.

Therefore the present priority is:

1. correct geometry,
2. preserved histological appearance,
3. robust handling of ordinary real-world image sets,
4. simple three-step use,
5. transparent quality reporting.

Performance work is still welcome when it improves responsiveness, memory use, or practical batch size. But “stitch hundreds of manually captured images in seconds” is not a defining requirement for this project.

A future automated stage-scanning workflow would be a different use case and could justify a different performance architecture.

---

# 7. Human expertise was the control loop

It would be misleading to describe this project as an AI system autonomously discovering the final solution.

The most important control loop came from the project author:

1. provide real pathology images,
2. inspect the output at tissue and nuclear level,
3. reject apparently attractive results when they were microscopically wrong,
4. describe the exact failure,
5. force the implementation to address the cause rather than the appearance,
6. repeat.

The AI assistants contributed code, alternatives, explanations, and independent reviews. The human pathologist supplied the domain-specific acceptance criteria that made those iterations converge toward a useful tool.

This is a useful pattern for AI-assisted scientific software development:

> **AI can explore implementation space quickly; domain expertise must define what “correct” means.**

---

# 8. What future AI coding agents should learn from this history

Before proposing a major rewrite, an AI agent should read:

- [`README.md`](../README.md)
- [`AGENTS.md`](../AGENTS.md)
- this document
- the current modules under [`microstitch/`](../microstitch/)
- the sample dataset and report under [`sample/`](../sample/)

Then it should ask:

- Which existing failure mode is this change meant to solve?
- Does the change improve geometry or merely hide an error visually?
- Does it preserve H&E appearance?
- Does it introduce unnecessary projective or non-rigid distortion?
- How will it be compared with the included sample case?
- Can the change be measured in the JSON report?
- Does it keep the GUI understandable for a pathologist?

A new algorithm is not automatically an improvement because it is newer, neural, GPU-accelerated, or more complex.

For MicroStitch Studio, the best change is the one that produces a more faithful and more usable reconstruction of the captured tissue.

---

# 9. Final lesson

The final quality did not come from one magic model, one library call, or one prompt.

It came from a sequence of engineering decisions:

**real data → visible failure → correct problem definition → constrained matching → global optimization → group photometry → seam-aware rendering → practical GUI → reproducible outputs.**

Gemini's early iterations exposed the limitations of local fixes. Claude's later review independently recognized the importance of the global architecture. ChatGPT-assisted iteration helped turn those observations into a microscopy-specific pipeline. The project author's pathology expertise determined which results were actually acceptable.

That combination—domain expert judgment plus iterative AI-assisted engineering—is the real development story of MicroStitch Studio.

# Contributing to MicroStitch Studio

Thank you for considering a contribution.

MicroStitch Studio is not a generic panorama project: it works with microscopic pathology images where a small geometric or photometric error can create duplicated nuclei, blurred gland borders, false seams, or misleading color changes. Contributions are therefore evaluated first for image fidelity and reproducibility, then for speed or visual polish.

## Before you start

Please read:

1. `README.md`
2. `AGENTS.md`
3. `sample/README.md`

If you use an AI coding assistant, ask it to read `AGENTS.md` before changing registration, rendering, color handling, or objective grouping.

## Development setup

```bash
git clone https://github.com/metinciris/stitching.git
cd stitching
python -m venv .venv
```

Windows:

```bat
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Run the application:

```bash
python MicroStitch_Studio.py
```

## What makes a good contribution?

Useful areas include:

- feature matching robustness
- pose-graph optimization
- loop-closure detection
- automatic objective / magnification grouping
- focus and blur scoring
- duplicate-frame detection
- tissue-aware seam selection
- illumination and white-background correction
- memory-efficient rendering
- pyramidal TIFF / OpenSlide-compatible export
- automated tests and benchmark tooling
- GUI readability and accessibility
- documentation

## Image-integrity rules

Please preserve these project principles:

- Do not make unconstrained homography the default transform.
- Do not broadly average overlapping nuclei with 50/50 alpha blending.
- Do not force clearly different objective magnifications into one resolution layer.
- Do not use generative super-resolution or hallucinated microscopic detail in the default pipeline.
- Do not silently alter H&E stain appearance for cosmetic reasons.
- Keep an unenhanced geometrically stitched output available when adding optional appearance processing.
- Avoid repeated full-resolution resampling; ideally warp each source image once into the final coordinate system.

More detail is available in `AGENTS.md`.

## Using the sample dataset

The repository contains a regression/reference dataset:

```text
sample/
├─ sample_images/
└─ sample_MicroStitch_Output/
```

Before and after a change, compare:

- objective grouping
- median registration error
- rejected / accepted pair counts
- final canvas dimensions
- visible seams
- duplicated nuclear contours
- local blur
- H&E color consistency
- white-background consistency

The current output is not a permanent golden standard; it is a reference point. Improvements are welcome, but changes should be described and reproducible.

Do not overwrite the sample source images merely to make a new algorithm look better.

## Testing a registration change

At minimum, test:

1. A known synthetic translation/rotation/scale transform.
2. Two overlapping H&E crops from the same source image.
3. Exposure-mismatched overlapping images.
4. Images with a dark circular eyepiece border.
5. A mixed-magnification dataset.

Useful acceptance criteria include:

- low reprojection / registration error
- stable global geometry
- no obvious duplicated nuclei in overlaps
- no severe color step at seams
- no inclusion of black eyepiece borders
- no incorrect collapse of multiple magnification groups into one group

## Pull requests

Keep pull requests focused when possible.

A good PR description should include:

- **What changed**
- **Why it changed**
- **Root cause** if it fixes a bug
- **How it was tested**
- **Effect on the sample dataset**
- **Registration metrics before/after**, if relevant
- **Color or geometry impact**, if relevant
- screenshots / crops for visible GUI or stitching changes

Suggested commit messages:

```text
Improve graph matching robustness
Fix white background normalization
Improve GUI readability
Add objective grouping diagnostics
```

## Coding style

Prefer:

- Python 3.11+ compatibility
- type hints for new public helpers
- `pathlib` for filesystem work
- descriptive settings instead of scattered magic numbers
- progress callbacks for long-running tasks
- separation between UI and stitching engine where practical
- clear exception messages
- deterministic behavior where possible

Avoid adding large dependencies unless they provide a substantial benefit and install reliably on Windows.

## GUI contributions

The application may be used for long sessions in pathology workflows. Please prioritize:

- readable font size
- good foreground/background contrast
- clear status information
- visible progress
- understandable labels
- responsive worker-thread execution
- safe cancellation
- useful tooltips

## Reporting a bug

When reporting a stitching bug, include as much as possible:

- operating system
- Python version
- package versions
- number of source images
- whether more than one objective was used
- relevant `stitch_report.json`
- screenshot or cropped example of the artifact
- traceback / process log

Do not upload identifiable patient information or protected health information to public issues.

## Clinical / research caution

This is experimental open-source imaging software, not a validated medical device. Changes that appear visually better still require independent validation before diagnostic or regulated use.

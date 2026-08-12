# MicroStitch Studio

### 3 steps to a clean, high-resolution microscope stitch

**Add images → choose output folder → click `STITCH WHOLE SLIDE`.**

MicroStitch Studio is an open-source Python desktop application for combining overlapping smartphone-through-microscope photographs into a single whole-slide-style mosaic while preserving tissue geometry, H&E color balance, and nuclear detail as much as possible.

![MicroStitch Studio interface](screen.PNG)

## Quick download & run

### Easiest way on Windows

**1. Download the project**

[**Download repository as ZIP**](https://github.com/metinciris/stitching/archive/refs/heads/main.zip)

Extract the ZIP and open a terminal inside the extracted folder.

**2. Install the required Python packages once**

```bat
pip install -r requirements.txt
```

**3. Run MicroStitch Studio**

Double-click:

```text
Run_MicroStitch.bat
```

or run:

```bat
python MicroStitch_Studio.py
```

> `MicroStitch_Studio.py` is the main launcher. The current application also uses the included `microstitch/` package, so keep the downloaded repository files together.

[View the main Python launcher](MicroStitch_Studio.py) · [View requirements](requirements.txt) · [Sample images and outputs](sample/)

---

## Three-step workflow

### 1 — Add microscope images

Use **+ Add images**, **+ Add folder**, or drag-and-drop overlapping microscope photographs into the left panel.

### 2 — Choose the output folder

For most image sets, start with the default **Balanced + graphcut** settings.

### 3 — Stitch

Click **STITCH WHOLE SLIDE**.

MicroStitch Studio automatically performs feature matching, robust registration, global pose optimization, objective/scale grouping, illumination correction, seam selection, and full-resolution rendering.

The result can be exported as PNG, preview JPEG, pyramidal OME-TIFF, and a detailed JSON quality report.

---

## Why MicroStitch Studio?

Generic panorama software is designed for natural scenes. Histopathology is different: even a small alignment error can create duplicated nuclei, blurred gland borders, false-looking seams, background brightness steps, or color shifts.

MicroStitch Studio therefore emphasizes:

- SIFT-based feature detection and robust pairwise matching
- RANSAC similarity / partial-affine registration
- global pose-graph optimization to reduce cumulative drift
- automatic separation of substantially different objective magnifications
- black eyepiece / invalid-border masking
- illumination and white-background normalization
- H&E color preservation
- graph-cut, Voronoi, and crisp seam strategies
- full-resolution Lanczos rendering
- limited blending instead of broad alpha averaging across the entire overlap
- PNG, JPEG preview, JSON quality report, and pyramidal OME-TIFF export

---

## Example data

A complete test set is available in the repository:

- [`sample/sample_images/`](sample/sample_images/) — source microscope photographs
- [`sample/sample_MicroStitch_Output/`](sample/sample_MicroStitch_Output/) — generated outputs
- [`sample/README.md`](sample/README.md) — how to reproduce and compare the sample

The README intentionally does not display every objective-group output inline. Anyone who wants to inspect the full-resolution examples can open the sample folders directly.

---

## Optional AI image enhancement

Modern image-generation and image-enhancement systems can improve the **presentation** of an already stitched image—for example apparent sharpness, contrast, background cleanliness, or overall visual impact.

An experimental AI-enhanced example is shown below:

![AI-enhanced stitched microscopy result](sonuc_AI_ile.png)

This should be treated as an **optional post-processing example**, not as part of the core registration pipeline. For pathology or scientific use, the geometrically stitched original should always be retained separately because generative or AI-based enhancement may modify microscopic appearance or introduce details not present in the source images.

---

## Installation in a virtual environment

For users who prefer an isolated Python environment:

```bash
git clone https://github.com/metinciris/stitching.git
cd stitching
python -m venv .venv
```

Windows:

```bat
.venv\Scripts\activate
pip install -r requirements.txt
python MicroStitch_Studio.py
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python MicroStitch_Studio.py
```

### Requirements

- Python **3.11+** recommended
- Windows 10/11 is the primary desktop target
- OpenCV contrib
- NumPy
- SciPy
- tifffile
- PyQt5

---

## Recommended acquisition technique

Software cannot recover detail that was never captured. For best results:

- keep the same objective within one acquisition pass
- lock phone exposure, white balance, focus, and digital zoom when possible
- avoid digital zoom
- keep approximately **30–45% tissue overlap** between neighboring fields
- scan in a predictable row-by-row / serpentine pattern
- avoid motion blur and major focus changes
- keep the phone and eyepiece relationship stable
- capture a new pass when changing objective magnification

---

## Output files

Depending on the selected settings and detected magnification groups, MicroStitch may produce files such as:

```text
objective_1.png
objective_1_preview.jpg
objective_1.ome.tif
objective_2.png
objective_2_preview.jpg
objective_2.ome.tif
stitch_report.json
```

The JSON report records processing settings, detected tiles, pairwise matches, objective grouping, registration information, and output metadata. It is especially useful when testing future algorithm changes.

---

## How it works

```text
Microscope images
      ↓
valid-field / eyepiece masking
      ↓
illumination + white-point estimation
      ↓
tissue-relevant SIFT features
      ↓
pairwise matching + Lowe test + RANSAC
      ↓
pose graph
      ↓
global robust optimization
      ↓
objective / scale grouping
      ↓
full-resolution warp
      ↓
seam selection + limited blending
      ↓
PNG / OME-TIFF / preview / JSON report
```

Unlike simple sequential panorama approaches, MicroStitch does not repeatedly match each new image against an increasingly blended canvas. Pairwise relationships are estimated first and then solved globally, helping reduce cumulative registration drift.

---

## Project structure

```text
stitching/
├─ MicroStitch_Studio.py
├─ Run_MicroStitch.bat
├─ requirements.txt
├─ README.md
├─ AGENTS.md
├─ CONTRIBUTING.md
├─ LICENSE
├─ screen.PNG
├─ sonuc.png
├─ sonuc_AI_ile.png
├─ microstitch/
│  ├─ models.py
│  ├─ matching.py
│  ├─ graph.py
│  ├─ registration.py
│  ├─ photometric.py
│  ├─ rendering.py
│  ├─ exporting.py
│  ├─ pipeline.py
│  └─ gui.py
└─ sample/
   ├─ README.md
   ├─ sample_images/
   └─ sample_MicroStitch_Output/
```

---

## Contributing and AI-assisted development

Contributions are welcome.

- [`CONTRIBUTING.md`](CONTRIBUTING.md) explains development and testing expectations.
- [`AGENTS.md`](AGENTS.md) is written specifically for future developers and AI coding agents such as ChatGPT, Codex, Copilot, or similar systems.

Important project principles include preserving tissue geometry, avoiding duplicated nuclei, keeping H&E color changes conservative, separating different magnifications when appropriate, and validating registration changes against the included sample dataset.

Useful future directions include:

- improved automatic objective clustering
- faster sparse graph matching
- tissue-aware seam costs
- automatic focus / blur rejection
- duplicate-frame detection
- exposure quality warnings
- memory-efficient tiled rendering
- OpenSlide-compatible output
- automated regression testing
- easier packaging as a standalone Windows executable

---

## License

MicroStitch Studio is released under the [MIT License](LICENSE).

## Research / clinical-use notice

MicroStitch Studio is experimental open-source imaging software. It is **not a validated medical device or certified whole-slide scanner**. Validation, quality control, regulatory compliance, and suitability for diagnostic use remain the responsibility of the user and their institution.

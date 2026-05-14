# CycloCAD

CycloCAD is a practical cycloidal gear profile generator focused on CAD-ready output and fast iteration for robotics drivetrain work.

It provides:
- Strict analytic cycloidal tooth generation tied to a mating gear pair.
- Full gear outline generation by rotating the tooth profile.
- Direct export to CSV and DXF for downstream CAD workflows.
- Basic mesh sanity checks and lightweight geometry regression checks.
- SolidWorks VBA macro support for sketch creation from generated profiles.

## Why CycloCAD

CycloCAD is built for engineering workflows where you need geometry that is:
- Parameterized and reproducible.
- Easy to inspect numerically and visually.
- Portable into CAD tools without manual tracing.

## Repository Structure

- `phase1_cycloidal_math.py`: Early standalone cycloidal math prototype.
- `phase1_5_strict_conjugate.py`: Main strict analytic generator with CLI, exports, and checks.
- `CycloidalDriveMacro.bas`: SolidWorks macro for importing generated geometry.
- `strict_cycloidal_tooth_points.csv`: Example tooth polygon output.
- `strict_cycloidal_gear_outline_points.csv`: Example full-gear polygon output.
- `strict_cycloidal_tooth_points.dxf`: Example tooth DXF output.
- `strict_cycloidal_gear_outline_points.dxf`: Example full-gear DXF output.

## Requirements

- Python 3.10+
- NumPy
- Matplotlib (optional, only needed when plotting)

Install dependencies:

```bash
pip install numpy matplotlib
```

## Quick Start

Generate tooth + full-gear outputs with defaults:

```bash
python phase1_5_strict_conjugate.py --no-plot
```

Run built-in regression checks:

```bash
python phase1_5_strict_conjugate.py --run-regression-checks --no-plot
```

Generate mesh sanity report:

```bash
python phase1_5_strict_conjugate.py --report-mesh-sanity --no-plot
```

## CLI Reference

Core parameters:
- `--z-gear`: Primary gear tooth count.
- `--z-mate`: Mating gear tooth count.
- `--module`: Metric module (mm).
- `--samples`: Point budget for one tooth.

Outputs:
- `--tooth-csv`
- `--full-gear-csv`
- `--tooth-dxf`
- `--full-gear-dxf`
- `--no-dxf`
- `--no-plot`

Quality and diagnostics:
- `--run-regression-checks`
- `--report-mesh-sanity`

Example custom run:

```bash
python phase1_5_strict_conjugate.py \
  --z-gear 30 \
  --z-mate 12 \
  --module 1.5 \
  --samples 480 \
  --report-mesh-sanity \
  --no-plot
```

## CAD Workflow

1. Generate outputs from Python (`CSV` and/or `DXF`).
2. Place outputs in the same folder as `CycloidalDriveMacro.bas`.
3. Open SolidWorks and run the macro.
4. Macro import mode can be configured to prefer DXF or CSV fallback.

## Notes on Geometry Validation

CycloCAD includes conservative checks intended for fast screening:
- Profile closure and finite-point checks.
- Radius bounds relative to addendum/root circles.
- Pitch-join tangent mismatch monitoring.
- Pair-level mesh sanity metrics (clearance risk and contact-ratio estimate).

These checks are intentionally lightweight and are not a substitute for full contact simulation or manufacturing tolerance analysis.

## Development Status

Current focus:
- Reliable profile generation and CAD export.
- Practical integration into SolidWorks workflows.

Planned improvements:
- Expanded meshing/contact analysis.
- Additional CAD export formats and integration tooling.
- Broader automated test coverage across edge-case gear pairs.

## Contributing

Contributions are welcome. Useful contributions include:
- Better geometric validation methods.
- Additional CAD interoperability tooling.
- Tests and reproducible benchmark cases.
- Documentation and workflow improvements.

## License

This repository follows the licensing terms defined by the project owner. If you plan to reuse this code in another project, review and add the appropriate license file and notices first.

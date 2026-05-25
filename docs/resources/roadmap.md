# Roadmap

A public sketch of what's planned. Not a contract: priorities
shift with user feedback and what we learn while shipping.

## Short term (next ~3 months)

- **`QTableView`-style data grid component**. The most-requested
  missing piece for "I can move my Qt app". Virtualized rows,
  sortable columns, column resize, sticky headers.
- **Color management 2.0**. Fold in OCIO 2.4 for tighter HDR / ACES
  pipelines.
- **Hair System solver**. Many-strand hair built on the existing
  Verlet rope simulation.
- **Brush > Cryptomatte AOV**.
- **Designer > Skin Weights Editor**.
- **PySide6 interop helper**: embed an Elysium window inside a Qt
  app for staged migrations.

## Medium term (~6 months)

- **Mobile target** (Android first, iOS likely). The framework's
  GPU stack is portable; the main work is touch-event remapping
  and per-OS packaging.
- **Multi-bone IK solver** (Spine IK, Spline IK, FABRIK).
- **Volumetric / emissive material nodes** in Hypershade.
- **HumanIK / full skeleton template** for the Designer.
- **Designer offline AI mode** with bundled small models.

## Long term (~12 months)

- **Web target** via a wgpu-on-WebGPU compositor. The framework's
  rendering stack is already WebGPU-ready; the bigger work is the
  Python-runtime story (Pyodide or a server-rendered split).
- **VFX integration**: Nuke / After Effects bridges using the
  Designer's `.esk` as a hand-off format.
- **Marketplace v2**: per-skin telemetry opt-in, reviews, paid
  skins.

## What's not on the roadmap

- A QML-style imperative-declarative hybrid. The `.esk` JSON +
  Python signals model is what we are committing to.
- A bundled blockchain / Web3 anything.
- A built-in form-builder for enterprise CRUD apps. That is what
  PyQt6 / PySide6 are for; we are not chasing them in that domain.

## How to influence the roadmap

- File a feature proposal (see [Contributing](contributing.md)).
- Upvote existing proposals in GitHub Issues.
- Build the feature yourself and PR. The fastest path.

## Past phases

The internal phase plans (PHASE_0 through PHASE_2_5) drove
development through v0.1. Snapshots live in the repo's
`.docs-staging/project-history/` folder for archival, not in this
site.

## See also

- [Changelog](changelog.md)
- [Contributing](contributing.md)

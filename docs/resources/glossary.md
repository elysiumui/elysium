# Glossary

Concepts used throughout the docs, defined precisely.

## A

**Aether**: The in-app AI agent. A chat session backed by a model
(Anthropic / OpenAI / Ollama) with access to 123 framework tools.
See [Aether](../guides/aether.md).

**Animation clock**: Scheduler that ticks every active animation
on a thread of its own. `elysium.anim.AnimationClock`.

**App**: The top-level application object. One per process.
Owns the event loop and the GPU device.

**AOV**: Arbitrary Output Variable. A render pass that isolates
one component of the final image (diffuse, specular, depth, etc.).
See [Designer > AOVs](https://designer.elysiumui.com/rendering/aovs/).

## B

**Borderless window**: A window with no OS chrome (title bar,
borders, close buttons). Default for Elysium.

## C

**Canvas**: A GPU surface inside a placement; receives
DisplayLists.

**Computed**: Derived reactive value; re-evaluates lazily on
signal change. `elysium.reactive.computed`.

## D

**DisplayList**: Immutable list of draw commands published to a
Canvas each frame.

## E

**Effect**: Side-effecting callback that re-runs on signal
changes. `elysium.reactive.effect`.

**`.esk`**: Skin bundle folder format. Manifest + document +
optional textures, animations, shaders.

## H

**Hit-test path**: SVG path describing which pixels inside a
window's bounds receive input. Pixels outside the path pass
clicks through.

**Hook**: Named event on a placement. `save.click`,
`name_input.value`, `tabs.change`. Bound with `@window.on(...)`.

**HookProxy**: Python-side dotted accessor for skin placements.
`window.cover.text = "..."`.

**Hot reload**: Skin reload without restarting the process; or
process restart preserving window position for Python edits.

## P

**Path**: Vector path builder. Like SVG path data; used by
DisplayList and skin placements.

**Placement**: One item in a skin's document. Has an `id` and a
`kind`. Examples: `ellipse`, `label`, `button`, `mesh3d`.

## R

**Reactive**: `elysium.reactive`: signal / computed / effect.

## S

**Signal**: Mutable reactive cell. Read with `s()`, write with
`s.set(v)`.

**Skin**: A loaded `.esk` bundle. Source of visual truth.

**SkinDiff**: Result of `modify_skin` / `magic_polish`. List of
changes that can be inspected and applied to a skin.

**Snapshot**: Named restore point of scene state, used by Aether
to allow rollback.

**Spring**: Critically-damped natural motion. `elysium.anim.Spring`.

## T

**Theme**: Dataclass of design tokens (background, surface,
accent, motion). Five built-ins ship.

**Timeline**: Sequenced + parallel animation container.

**Tween**: Single-value interpolation over time.

## W

**Window**: An OS window. Borderless and shaped by default in
Elysium.

**wgpu**: The cross-platform GPU API the framework's compositor
uses. Implements WebGPU; rides on Vulkan / Metal / DX12 underneath.

## See also

- [Designer glossary](https://designer.elysiumui.com/glossary/)  
  Designer-specific terms.

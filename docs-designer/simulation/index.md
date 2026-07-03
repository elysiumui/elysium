# Simulation

Simulation (the FX menu set) produces motion algorithmically:
hair strand wave, cloth drape, rigidbody collision. Use when the
result is too organic or too contact-heavy to key by hand.

## What ships

| Solver | Menu | Used for |
|---|---|---|
| Hair / Verlet rope | `Simulation > Create Hair Strand` (short / long) | Hair, rope, hanging cables |
| nCloth | `Simulation > Create nCloth Patch` (small / large) | Flags, capes, cloth panels |
| Bullet | `Simulation > Bullet > Add Rigidbody` (default / bouncy) | Rigid object collision |

Three solvers in v1; more are roadmap (smoke, fluids, soft body).

## Sim vs animation

Pick simulation when:

- The motion is **secondary**: a flag attached to an animated pole;
  the pole is keyed, the flag is sim.
- The motion depends on **contact**: two rigidbodies that bounce
  off each other unpredictably.
- The motion needs **stochastic variation**: a hair strand whipping
  in the wind frame to frame.

Pick animation when:

- The motion needs to read **identically** every play. Sims have
  initial-condition sensitivity.
- The motion is the **primary** focus and you need full control
  (e.g. the butterfly wing flap; animate it, do not simulate it).

## Cache and bake

Simulations run live during scrub but are slow. For final
playback, cache or bake them:

- **Cache** (default after running): stores per-frame state in a
  binary cache file. Subsequent scrub is instant; re-running the
  sim invalidates the cache.
- **Bake to keys**: like `Time Editor > Bake`, this converts sim
  output into per-frame keyframes on the relevant channels. Bakes
  ship with the `.esk` bundle the same way as hand-keyed motion.

Cache or bake before exporting.

## Solver settings

Each solver has a tiny set of parameters in the Properties pane.
The dedicated pages cover them:

- [Cloth](cloth.md)
- [Hair](hair.md)
- [Rigidbody](rigidbody.md)

## Wind and forces

Forces are global per-project: `Simulation > Forces > Add Wind…`,
`Add Gravity…`, etc. Forces affect every solver that opts in via
the placement's **affects** property.

## Performance

| Solver | Performance budget |
|---|---|
| Hair (24 segments) | ~0.5 ms / frame |
| nCloth (8x10 grid) | ~3 ms / frame |
| nCloth (12x14 grid) | ~6 ms / frame |
| Bullet (10 bodies) | ~1 ms / frame |
| Bullet (50 bodies) | ~5 ms / frame |

These run on the CPU's solver thread (not the render thread), so
the View Panel stays smooth even during heavy sims.

## See also

- [Hair](hair.md), [Cloth](cloth.md), [Rigidbody](rigidbody.md)
- [Animation index](../animation/index.md): when hand-key wins
  over sim.

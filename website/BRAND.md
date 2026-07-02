# Elysium brand — mini design system (website)

Single source of truth for the site's look. Mirrors the framework's
`theme.studio_dark()` so the website looks like the product. Tokens live in
[`src/styles/global.css`](src/styles/global.css) (`@theme` block).

## Palette

| Token | Hex | Use |
| --- | --- | --- |
| iris | `#6C7CFF` | primary / CTA / links |
| accent | `#8A78FF` | gradient partner |
| morpho | `#4FC3F7` | iridescent sheen (sparingly) |
| surface | `#1B1E24` | page background |
| raised | `#2A2F39` | cards / panels |
| ink | `#E8EBF0` | text |
| muted | `#9AA3B2` | secondary text |
| hairline | `#2C323C` | borders |
| deep | `#0A0C10` | code chips / deepest layer |
| success / warning / danger | `#2DA847` / `#FF8C00` / `#E63946` | semantic only |

Signature gradient: iris → accent, with a Morpho cyan↔violet sweep for the
`.text-iridescent` headline treatment.

## Type

- **Inter Variable** — UI/body (self-hosted via `@fontsource-variable/inter`).
- **Plus Jakarta Sans Variable** — display headings, buttons.
- Tabular numerals (`.tnum`) on versions/stats.

## Geometry & elevation

8px grid · radii 8 / 14 / 22 px · 3-tier shadows (`--shadow-close/mid/far`).

## Assets (`public/brand/`)

| File | What |
| --- | --- |
| `logomark.svg` | monoline Blue Morpho glyph (draft), `currentColor` |
| `logomark-color.svg` | iridescent variant for hero/nav |
| `butterfly-hero.webp` (+`-sm`) | photoreal Morpho cutout, transparent bg |
| `og-image.png` | 1200×630 social card (draft) |
| `../favicon*` `apple-touch-icon` `icon-*.png` | favicon set from the app icon |

⚠️ **Provenance:** the photoreal butterfly derives from a third-party asset in
`examples/butterfly/` — verify license before public launch, or replace with
the commissioned model (`examples/butterfly/BLUE_MORPHO_INTRO_SPEC.md`).
The logomark SVGs are original drafts; a commissioned vector identity should
follow the spec in the project plan ("Logo & brand-asset requirements").

## Voice

Tagline: **“Python desktop UI without the rectangles.”**
Tone: confident, concrete, a little lyrical about the butterfly — never
"templatey" marketing filler. Screenshots must be *real framework output*.

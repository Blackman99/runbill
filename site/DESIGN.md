# runbill landing page: design brief (v2, 2026-10-10)

Replaces the v1 taxi-meter design. Written before implementation; checked against
`/workspace/oss-factory/playbook.md` (2026-10-09 / 2026-10-10 rules) and
`/workspace/oss-factory/design/registry.md`.

## Direction: an isometric brick city of Actions minutes
Every **workflow is a building**. Every chunk of a job's **billed minutes is a brick**. A brick's height is
what those minutes **cost**, so the runner type decides how tall a brick is:

| 50 billed minutes on | price | brick height |
|---|---|---|
| Linux 2-core | $0.30 | 1 unit (a thin slab) |
| Windows 2-core | $0.50 | 1.67 units |
| macOS | $3.10 | 10.3 units (a tower block) |

A building's height is its cost; the **rooftop elevation is the dollar amount**. A few macOS jobs build a
skyscraper next to a sprawling but low Linux block, which is exactly the lesson runbill teaches.

## Palette (hex)
- Concrete (page) `#c9ccd1`, concrete plaza top `#b9bdc3`, plaza sides `#a5aab1` / `#8e939b`
- Ink `#16181d` (type, code blocks)
- Linux brick, three flat faces: top `#f7f6f2`, left `#dcdcd8`, right `#bcbdbd`
- Windows brick: top `#7a8693`, left `#626d79`, right `#4c5560`
- macOS brick and every dollar figure: cobalt top `#1d3fbf`, left `#17329a`, right `#112676`
Every face is a single flat fill. No gradients, no glow, no shadows except the faces themselves.
No yellow, no red, nothing warm.

## Type (self-hosted, OFL, subset to Latin)
- **Unbounded** (static 700 and 800 instances): wide geometric display for headings and the big numbers.
- **Red Hat Text** (400, 700): body copy.
- **Red Hat Mono** (400, 700): minutes, dollars, commands, CLI output.

## Texture and rendering
Isometric 3D blocks drawn as SVG polygons from a tiny projection helper (`iso.js`, ~2 KB, no framework):
`screen = ((x - y)·cos30°, (x + y)·sin30° - z)`. Three faces per box, painter's order back-to-front,
bottom-to-top. No paper, no grain, no skeuomorphic objects, no outlines.

## Layout
1. **Full-bleed city hero.** The wide Unbounded headline sits in the "sky" across the full width; the city
   plaza fills the lower part of the viewport edge to edge. Not a centred object, not left-copy/right-card.
2. **Survey (scroll tour).** The city stays pinned while the camera pans building to building; beside the scene
   a legend block per building (swatch cube + workflow, jobs, minutes, $) replaces tables and cards.
3. **Brick conversion chart.** One isometric drawing: the same 50 billed minutes as a Linux, Windows and macOS
   stack, plus the round-up rule (a 40-second job still lays a whole minute).
4. **How it is measured**, as storeys: an ordered list numbered L1-L5 from the ground floor up.
5. **Install** blocks (ink code blocks), links, footer plaza strip.

## Motion (meaningful)
- Bricks drop from the sky, stack, and settle with a small bounce; each building rises job by job while its
  rooftop dollar counter ticks in step with the bricks that have landed.
- "Pour another city" knocks the buildings down (bricks fall through the plaza) and restacks a different
  workflow mix.
- Scroll tour: the camera glides (CSS transform transition on the scene) to the building being described.
- `prefers-reduced-motion: reduce`: the city is drawn already built, counters show final values, camera jumps
  without transition, the rebuild swaps instantly.

## Logo
Three isometric cubes in layers: a Linux cube and a Windows cube on the ground, a cobalt macOS cube on top.
Three flat faces each, transparent background, no rounded app-icon tile, no outline. Same drawing is the
favicon, the 512 px PNG, the docs logo and the mark in the OG / social preview.

## OG image and social preview
Concrete field, an isometric skyline across the bottom built from the same helper, the Unbounded `runbill`
wordmark with the logo, and the line "Who ran up the Actions bill?". 1200×630 (`og-image.png`) and 1280×640
(`social-preview.png`, `og-social-preview.png`).

## Marketplace branding
`action.yml`: icon `box` (Feather's isometric cube), color `blue` (nearest allowed colour to cobalt).

## Self-check against the bans
Playbook (2026-10-09):
- dark background with cyan/purple gradients: **no**, mid-light cool concrete, no gradients anywhere
- gradient text: **no**, solid ink and solid cobalt
- glow / glowing strokes: **no**
- glassmorphism: **no**, no blur, no translucency
- left-copy/right-animated-card hero: **no**, full-width headline over a full-bleed scene
- three-column feature cards: **no**, legend blocks in a scroll tour, a single conversion drawing, a storey list
- generic SaaS / dev-tool template: **no**, the page is the city
- Inter + monospace default pair: **no**, Unbounded + Red Hat Text + Red Hat Mono

Cross-project bans (2026-10-10; paper aesthetic belongs to toolsmoke only):
- beige / kraft / manila paper ground: **no**, cool grey `#c9ccd1`
- paper texture: **no**, flat fills only
- red-ink circling, stamps, red crosses: **no**, no red at all
- typewriter fonts: **no**
- line-by-line receipt printing / typing animation: **no**, the v1 receipt is gone; motion is gravity and stacking
- centred skeuomorphic object over a stack of hard-shadow paper slips: **no**
- rounded-square app-icon logo with heavy-outline cartoon object: **no**, a free-standing cube stack
- taxi meter, taxi yellow, checker band, seven-segment digits, receipts (runbill v1): **all removed**

Against the registry, axis by axis:
- background lightness: toolsmoke light warm paper; agentckpt mid yellow-green LCD; certfan near-black;
  linelore pure white; runbill **mid cool grey**, distinct.
- colours: no hex shared with any project; the only blue in the factory.
- fonts: Unbounded / Red Hat Text / Red Hat Mono appear in no other project.
- texture: the only 3D project (three-face flat shading); others are paper, pixels, thin vector lines, flat type.
- rendering: isometric projection; others are skeuomorphic print, pixel art, generative dataviz, kinetic type.
- layout: full-bleed scene with a camera pan; others are report page, game HUD, 12-col data plate, Swiss grid.
- motion: gravity (drop, stack, bounce); others are typing/stamping, `steps()` frames, line tracing, letter
  splitting.

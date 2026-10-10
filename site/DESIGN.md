# runbill landing page: design brief

## Reference object
A **mechanical taxi meter** bolted to a cab dashboard (Halda / Argo style): a squat enamel box with a
chrome "FOR HIRE" flag on top, red seven-segment fare digits, little rate-tariff windows (TARIFF 1/2/3),
plus the **door rate card** decal and the **paper fare receipt** the meter prints at the end of the ride.

| Taxi | runbill |
|---|---|
| flag dropped from FOR HIRE to HIRED | a workflow run starts |
| fare digits ticking up | billed minutes / dollars accumulating |
| tariff window (1/2/3) | runner SKU: Linux / Windows / macOS rate |
| "every started minute is charged" | each job rounded up to a whole minute |
| door rate card | the default $/min table |
| printed receipt | the CLI report |

## Palette (from the object)
- Cab yellow `#f2c230` (page), checker black `#1d1a16`
- Meter case enamel `#2a2622` (only on the meter object, never page background), chrome `#c9c6bd`
- Segment red `#e8341c`, unlit segment `#4a2420`
- Receipt paper `#fbf7ec`, receipt ink `#3a352d`

## Type
- **Big Shoulders Display 800**: the condensed lettering stencilled on cab doors.
- **Barlow Condensed 500/700**: rate-card and receipt type, tabular figures. No monospace; digits on the meter
  are drawn as SVG seven-segment glyphs.

## Layout
Checker band across the top; door-lettering headline centred; the meter as one centred object; below it a
door-style rate card (table), a numbered "how the fare is computed" list on the yellow door, the receipt as a
narrow centred paper strip, an install ticket, footer checker band. Single column, no cards grid.

## Motion (meaningful)
1. The flag drops from FOR HIRE to HIRED, then the fare digits tick up, tariff window switching as each
   workflow's jobs are billed (Linux → macOS jumps visibly faster: the product's core lesson).
2. "Another ride" re-runs the meter with a different workflow mix.
3. The receipt prints line by line when scrolled into view and tears off.
`prefers-reduced-motion`: final totals shown, flag already down, receipt fully printed.

## Banned-list self-check
dark bg + cyan/purple gradients: no (yellow page, no gradients) · gradient text: no · glow: no (segments flat,
no shadows) · glassmorphism: no · left-copy/right-card hero: no (centred object) · three-column feature cards:
no (table + numbered list) · SaaS template: no · Inter + monospace: no (Big Shoulders + Barlow Condensed, SVG
digits). Differs from toolsmoke (paper inspection report), agentckpt, certfan (pegboard/brass), linelore (card
catalog).

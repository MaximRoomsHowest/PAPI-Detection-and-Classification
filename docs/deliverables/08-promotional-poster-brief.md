---
title: "Promotional Poster — Design Brief (A3)"
subtitle: "Howest Industry Project · 2026"
mainfont: "Calibri"
fontsize: 10pt
geometry: "a4paper, margin=2cm"
---

# Promotional Poster — A3 Design Brief

> Brief for the final-deliverable **A3 promotional poster** (PDF,
> portrait orientation). The team executes this in Figma or Canva
> using the design tokens below and exports to PDF for Leho upload.
>
> **Rubric constraints (verbatim from the deliverables spec):**
>
> - **Format**: A3, PDF.
> - **Must include**: team-member names, "Industry Project" mention,
>   MCT or **CTAI** logo, the project shown as a **single image**.
> - **Must NOT include**: technology mentions (no "YOLO", "FastAPI",
>   "React", "Python", "Docker", etc.).
> - **Goal**: promotional events. The audience is prospective
>   students and visitors — not jury graders. Lead with the *story*,
>   not the engineering.

## 1. Specs

| Property | Value |
| --- | --- |
| Format | PDF, A3 portrait (297 × 420 mm) |
| Bleed | 3 mm on every edge (308 × 426 mm total artwork area) |
| Safe zone | 10 mm inside the trim line |
| Colour mode | CMYK for print, RGB acceptable for screen |
| Resolution | 300 dpi for raster elements; vector everywhere else |
| Typography | Poppins (matches the app — see `01-design-document.md §4.2`) |
| Primary colour | Intersoft navy `#00426e` (HEX) / `100 75 0 50` (CMYK approx.) |
| Accent | Amber `#f0a500` — use sparingly (single accent element) |
| Background | White or very light neutral `#f6f7fa` |

## 2. Layout sketch

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   [CTAI logo, top-left, ~40 mm wide]                          │
│                                                              │
│           ─────────  HERO IMAGE  ─────────                    │
│           ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                    │
│           ▓                              ▓                    │
│           ▓     A drone in flight at     ▓                    │
│           ▓     dusk, four PAPI lights   ▓                    │
│           ▓     glowing on the runway    ▓                    │
│           ▓     threshold below.         ▓                    │
│           ▓                              ▓                    │
│           ▓     Subtle glidepath line    ▓                    │
│           ▓     overlay (gold thin line) ▓                    │
│           ▓                              ▓                    │
│           ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                    │
│                                                              │
│                                                              │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━           │
│                                                              │
│        PAPI VISION                                            │
│        Safer landings, seen from the sky.                    │
│                                                              │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━           │
│                                                              │
│                                                              │
│   Sousa Rodrigo · Chekhun Maksym                              │
│   Kattan Hamzzah · Rooms Maxim                                │
│                                                              │
│   Howest · Industry Project · 2026                            │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

Vertical zones (top to bottom):

1. **Top band (0 – 60 mm)** — CTAI logo top-left, generous whitespace.
2. **Hero image (60 – 290 mm)** — single dominant photograph or
   render. Full-width, no caption. See §3.
3. **Title band (290 – 330 mm)** — project title + tagline. See §4.
4. **Footer (330 – 420 mm)** — team names + "Howest · Industry
   Project · 2026". Small, balanced.

The rubric demands *one* image. Avoid the impulse to add screenshots
of the app or supporting illustrations.

## 3. Hero image — direction

The image is the poster. Three concrete options ranked by
emotional pull:

### Option A (recommended) — Drone-at-dusk

A photograph or photorealistic render of:

- A small drone hovering in the foreground, motion-blur on the
  rotors so it reads as in-flight.
- The four PAPI lights glowing on the runway threshold in the
  middle distance, two red two white (visibly "Correct glidepath").
- Sky transitioning from deep blue at top to amber at the horizon
  — sunset / dusk.
- Subtle thin gold line indicating the 3° glidepath, descending
  from upper-right to the lights.

**Mood**: calm, precise, almost cinematic. "This is a real thing in
the real sky."

**Sourcing**: a Howest-licensed stock photograph composited with a
rendered drone, OR a Midjourney / Stable Diffusion render with
careful checking that the PAPI configuration is plausible (4 lights
in a row, not a runway-lighting cluster).

### Option B — Cockpit-view abstraction

The same scene from inside a cockpit on final approach — instrument
panel softly out-of-focus in the foreground, runway threshold + PAPI
in centre frame through the windscreen.

**Mood**: insider, "this is what pilots see." Risk: implies the
tool is *for pilots*, which it isn't.

### Option C — Lamps macro

A close-up of a single PAPI lamp at night with the red/white
boundary visible across the lens.

**Mood**: technical, jewel-like. Risk: loses the aviation context
entirely; reads as "a stage light."

**Recommendation:** Option A. It's the strongest read at A3 from 2 m
distance, which is where promotional posters live.

## 4. Copy

### Title

```
PAPI VISION
```

Set in Poppins SemiBold, large (≈80 pt), Intersoft navy.
Letter-spacing tight (-1% to -2%) so it reads as one mark.

### Tagline (recommended)

```
Safer landings, seen from the sky.
```

Eight words. Says *what* (safer landings), *how* (seen — i.e. visual
inspection from above), and *who* the user is implicitly (anyone
overseeing approach safety). No tech jargon, no acronyms.

### Tagline alternatives (pick one)

- "Approach-light verification, from a drone." — more literal, less
  evocative.
- "An eye on the glidepath." — short and confident.
- "Glidepath integrity, from above." — formal.
- "Drone-assisted approach safety." — clear but flat.

Avoid: anything that mentions AI, ML, computer vision, real-time, or
specific airports. Those are jury-deck words, not poster words.

### Footer copy

```
Sousa Rodrigo · Chekhun Maksym · Kattan Hamzzah · Rooms Maxim

Howest · Industry Project · 2026
```

Two lines, centred. Names in Poppins Regular 18 pt; programme line
in Poppins Medium 14 pt with Intersoft-navy underline accent.

The phrase "Industry Project" is **required** by the rubric.

## 5. What to leave off

- **No screenshots of the application.** Posters are for evocation,
  not product demo. The screenshot work belongs in the deck.
- **No QR code.** Audiences at promotional events rarely scan; if
  the event is graduation, a printed URL works better.
- **No partner / sponsor logos** other than CTAI. Intersoft branding
  belongs in the client-facing handover materials, not the
  recruitment poster.
- **No bulleted feature lists.** A poster with bullets is a slide.
- **No body copy beyond title + tagline + footer.** If it doesn't
  fit in those three blocks, it doesn't belong on the poster.

## 6. Production checklist

Before exporting and uploading to Leho:

- [ ] Image is at least 300 dpi at A3 size (3500 × 4960 px minimum).
- [ ] All text is real text, not flattened to the image (so the PDF
      stays searchable and scalable).
- [ ] Fonts are embedded in the PDF export (Figma: "Outline text"
      OFF; Canva: PDF Print preset).
- [ ] Colour profile is set explicitly — CMYK Coated FOGRA39 for
      print, sRGB for screen-only delivery.
- [ ] Bleed and trim marks are included if the poster will be
      printed.
- [ ] Filename: `papi-vision-poster-A3.pdf`.
- [ ] Final approval: at least two team members signed off in
      Trello before upload.

## 7. Open decisions

**<!-- TEAM: capture these decisions in a quick sprint check
before the final-week design pass. -->**

1. Image source: licensed photograph, AI render, or composite?
2. Tagline: which of the four options (or another)?
3. Design tool: Figma or Canva?
4. Print run: digital-only for Leho, or also printed for the demo
   day / promotional table?
5. Does the team want a sub-tagline in Dutch and / or French for
   the bilingual promotional version?

## 8. Sources

- Design system tokens: `01-design-document.md §4`.
- Rubric constraints: BigBrain
  `02-courses/industry-project/industry-project-deliverables-summary.md`.
- Application screenshots (for inspiration only, *not* for the
  poster): `docs/qa-screenshots/`.

# The interface, rebuilt

**Date:** 2026-08-06
**Ask:** a materially better interface than the reference product, keeping the existing
light and dark themes but raising them; and fix the statement table, which overflowed its
panel and cut the newest column in half.

---

## The design position

The reference product is uniformly 13px. Every element — company name, share price, a single
cell in a fifteen-column table — is set at the same size. There is no hierarchy, so the eye
has nowhere to land, and the tables give you numbers while leaving you to work out the shape
in your head.

Three decisions follow from that.

### Colour comes from the rupee note series

The previous palette was the framework default indigo. The primary is now drawn from the ₹100
note's lavender-indigo — close enough to keep continuity, specific enough to belong to this
market rather than to any product built on the same starter.

Dark mode moved from neutral grey to **ink-navy**, because the subject is a printed ledger.
Gains and losses are a deep teal-green and a brick red rather than neon: these are read for
hours at a time.

### Three typefaces, all from the system

- **Serif** for company names and section titles. A financial document has authority, and
  every competing screener is sans throughout.
- **Sans** for prose.
- **Mono** for every number, every column head, every unit note.

All system stacks, deliberately. The production content security policy sets
`font-src 'self'`, so a webfont host would be blocked — and a self-hosted tool should not need
the network to draw a number.

The mono micro-label is the recurring device: uppercase, widely tracked, used for every
eyebrow and column head. Structural text is instantly distinguishable from content text.

### The risk: extreme scale contrast

The share price is set at 64px in serif. Immediately below it sits a grid of 13px mono
readouts, and below that a dense table. The reference product has no scale contrast at all;
this is the opposite bet, and it is justified — the price and the name are what someone came
for, the tables are what they stay to study.

---

## The signature: a trend rail

Every top-level statement row carries a small sparkline beside its label, drawn from **every**
period rather than only the visible ones.

Scanning the label column now tells you the trajectory of the whole business at a glance:
sales climbing, margins flat, tax rate dipping in one quarter, other income spiking once. The
reference product gives you the figures and leaves the shape to you.

It is deliberately unlabelled and unscaled. It answers "which direction" and nothing more —
the exact numbers are in the same row. A series that crosses zero gets a dashed baseline,
because "went negative" is the most important thing a financial line can do.

---

## Fixing the table

The reported problem: sixteen quarters forced a horizontal scrollbar inside the panel and the
newest column was sliced in half. It read as broken.

The reference product solves this by scrolling sideways. That is worse than it looks: the
newest quarter — the one everybody wants — is the one off-screen.

**What it does now.** The most recent periods are shown, and the count adapts to the width:

| Width | Periods shown |
| --- | --- |
| Small phone | 3 |
| Large phone | 4 |
| Tablet | 6–8 |
| Laptop | 10–12 |
| Wide desktop | 14 |

A control in the corner reveals all of them, which is when — and only when — the box scrolls
internally. The page itself never scrolls sideways at any width.

### Two attempts, and why the first was wrong

The first version measured the container with a `ResizeObserver` and computed how many columns
fit. It did not work, twice over:

1. **The measured element was the table's own container**, and the cells are set not to wrap.
   The table widened its container, so the container always reported that everything fitted.
   Fixed with a zero-height probe element that cannot be pushed by content.
2. Even with a correct measurement the column count never changed on screen. Rather than keep
   debugging observer timing, I replaced the whole approach with **CSS breakpoints**. Columns
   carry a visibility class indexed from the newest period backwards.

The second approach is better on the merits, not just easier: it needs no JavaScript, no
re-render, and no layout pass. Columns cannot pop in after the page has drawn.

Measured on the running page: 3 columns on a small phone through 14 on a wide desktop, page
never scrolling sideways at any of six widths.

### A related fault it exposed

At 480px and below, the **page** scrolled sideways rather than the table scrolling inside its
box. A flex or grid child defaults to a minimum size of its content, so a wide table pushes
every ancestor. Adding `min-w-0` down the chain — shell, main, container, panel — makes the
overflow land where it belongs.

---

## The theme switcher

Reduced from a three-item dropdown to a single button. The operating system preference still
chooses the theme on a first visit, but once someone has chosen, the app stops following the
OS — a machine that switches to dark at sunset should not override a deliberate choice of
light. The icon shows what you will get, not what you have.

A stored `"system"` from the old switcher is ignored rather than treated as a theme name.

---

## Statements in the URL

`/company/RELIANCE` is standalone and `/company/RELIANCE/consolidated` is consolidated,
matching the reference, so either view can be linked and shared. The toggle became two links.

The API already falls back when the requested set does not exist — only 2,510 of 5,630
companies file consolidated statements — so the caption states what is actually on screen and
why, rather than what was asked for.

---

## How I checked it

| Check | Result |
| --- | --- |
| Frontend tests | 61 pass |
| TypeScript and build | clean |
| Statement table, 6 widths | 3 to 14 columns, no page-level sideways scroll |
| Trend rails | render and read correctly against real Reliance data |
| Scale contrast | price at 64px against 13px data |

Two tests failed and both were correct to: the missing-value glyph changed from a hyphen to an
em dash, and the row-cap message became a link.

---

## What is left

The mobile navigation drawer and the narrow-width layouts are built but were verified by
measurement rather than by eye — the browser tooling here resizes the window without changing
the page viewport, so a real phone-width screenshot was not possible. Worth a look on an
actual device.

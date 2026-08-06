# Phase 0 - Frontend scaffold and theme switcher

**Date:** 2026-08-06
**Roadmap item:** [Phase 0 - Foundation](../prd/08-roadmap.md), the remaining half
**Result:** Done. Phase 0 is now complete. 23 frontend tests pass, 50 backend tests pass.

---

## What I set out to do

Get a React app on screen that talks to the backend, with the light/dark theme switcher
working properly. No screener, no company pages - just proof that the whole stack connects
end to end.

---

## What got built, in plain terms

### 1. The app skeleton
React with TypeScript, built by Vite. Tailwind for styling, set up the way shadcn/ui expects:
all colours are defined once as variables, and every component refers to those variables
rather than naming a colour directly. That is what makes one switch flip the entire app
between light and dark.

During development the frontend runs on port 5173 and quietly forwards anything starting
with `/api` to the backend on port 8000, so there is no cross-origin fuss.

### 2. The theme switcher
Three choices: Light, Dark, and System. System follows whatever the operating system is set
to, and keeps following it - if you change your OS to dark mode at sunset, the app changes
with it. Pick Light or Dark explicitly and it stops following and stays where you put it.

The choice is remembered between visits.

**The flash problem.** If a returning dark-mode user loads the page and React decides the
theme after the page has already drawn, they get a white flash first. To avoid that, a tiny
script in the page header reads the saved choice and applies it *before* anything is drawn.
Verified: reloading on light mode showed no flash.

### 3. Colours chosen for both themes
Financial screens live and die on red and green. Two decisions here:

- The gain and loss colours are defined separately for light and dark, because a green that
  reads well on white is muddy on near-black
- **Colour is never the only signal.** Every status indicator pairs a coloured dot with an
  actual word - "ok", "yes", "completed". Someone who cannot distinguish red from green
  reads exactly the same information

Also added a `tabular` style for numbers, so digits occupy equal width and figures line up
in columns. Without it, financial tables look ragged.

### 4. A status page
Not the real product, but a genuine end-to-end test. It shows:

- Whether the backend is alive, and whether it can reach FinEdge
- How much data we have stored and when it was last fetched
- The recent download runs, with how many requests each made

Every timestamp is shown in Indian Standard Time, and every large number uses Indian digit
grouping - 17,91,661 rather than 1,791,661.

---

## What went wrong

Nothing broke in the app, but **one test was written wrong and one check misled me.**

### The ambiguous test query
A test clicked a button labelled "light" - but the same test also displayed the current
theme as text, which also read "light". The test framework found two matches and refused to
guess. Fixed by asking for the button specifically rather than for any element with that
text.

Worth keeping: the framework was right to refuse. A test that silently picks one of two
matching elements is a test that will break mysteriously later.

### A browser click that appeared to prove a bug
I opened the app in a real browser, clicked "Light" in the theme menu, and the theme stayed
dark. The saved value read "dark" - as if clicking Light had selected Dark.

I checked the menu positions from the page itself, then triggered the Light option directly.
It worked correctly: theme switched, class changed, saved value became "light", background
turned pale.

So the app was fine. The automated click had landed a couple of rows off because the
screenshot I measured from is scaled differently to the actual page. Worth recording because
the false alarm looked exactly like a real bug, and the fix for a real bug would have made
the working code worse.

---

## How I checked it works

| Check | Result |
| --- | --- |
| TypeScript compile | clean |
| Frontend tests | 23 pass |
| Production build | succeeds, 302 KB of JavaScript, 98 KB compressed |
| Built files serve correctly | page, script and stylesheet all load |
| Dev server reaches the backend | yes, reports the 60 stored responses |
| Real browser, dark mode | renders correctly, live data shown |
| Real browser, light mode | renders correctly, icon changes to a sun |
| Theme menu | all three options shown, current one ticked |
| Choice survives a reload | yes, no flash of the wrong theme |
| Backend tests still pass | 50 pass |

Screenshots of both themes were taken during the check.

---

## Phase 0 is complete

Both halves are done. The backend can fetch and store a company; the frontend can display
what has been stored and switch themes.

## What's next

Phase 1, the big one. Everything so far stores FinEdge's responses exactly as they arrive.
Phase 1 turns them into proper tables that can be queried - which means confronting the fact
that banks report entirely different figures from ordinary companies, and there is probably
a third shape for insurers. Rather than assuming which companies use which shape, the plan
is to group companies by the fields they actually return and let the data decide.

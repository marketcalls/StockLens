# Phase 0 - Backend foundation

**Date:** 2026-08-06
**Roadmap item:** [Phase 0 - Foundation](../prd/08-roadmap.md)
**Result:** Done and working. 50 tests pass. A live fetch of Reliance stored 59 responses.

---

## What I set out to do

Build the skeleton of the backend. Nothing user-facing yet. The goal was simply:
**can we ask FinEdge for a company's data, and can we keep what comes back?**

Everything after this depends on that working, so it goes first.

---

## What got built, in plain terms

### 1. A settings file that reads the API key
The app needs the FinEdge key to do anything. It reads it from the `.env` file at
startup. The key is wrapped in a "secret" type, which means if anyone accidentally
prints the settings, they see `**********` instead of the actual key.

### 2. A client that talks to FinEdge
This is the piece that actually makes the web requests. It does four things beyond
just fetching:

- **Waits its turn.** FinEdge has never told us how fast we're allowed to ask for
  things, so the client deliberately paces itself to 5 requests a second. Better to
  be slow than to get the key blocked.
- **Retries when it makes sense.** If FinEdge is temporarily down (a "503"), the
  client waits and tries again, waiting longer each time. But if FinEdge says "you
  asked for that wrong" (a "400"), retrying is pointless, so it gives up immediately
  and moves on.
- **Never prints the key.** More on this below, because this is where things went wrong.
- **Counts what it used.** Tracks calls made and bytes downloaded, so we can see the
  cost of a run.

### 3. A list of every request needed for one company
FinEdge doesn't have a single "give me everything about Reliance" endpoint. You have
to ask for the profit and loss statement separately from the balance sheet, separately
from the ratios, and separately for standalone versus consolidated figures, and
separately for annual versus quarterly.

I wrote out that full list. It comes to **59 requests per company**.

Two combinations are deliberately left out because the API rejects them:
- Asking for a "year to date" period - the docs say it's allowed, the API says it isn't
- Asking for "trailing twelve months" on a balance sheet or cash flow - only the
  profit and loss statement supports it

Finding these out now means the big download later won't waste thousands of requests
on combinations that can never work.

### 4. A database that stores the raw answers
Every response from FinEdge is saved exactly as it arrived, before any interpretation.
Three reasons:

- If I later discover I misread a field, I can fix the reading without re-downloading
- If a user says "this number looks wrong", I can show exactly what FinEdge sent
- The Super Admin console needs to display raw responses anyway

The responses are **compressed** before storing, roughly 5x smaller, and they live in
their own separate database file so the main app database stays small and fast.

There's also a **duplicate check**: each response gets a fingerprint, and if we fetch
the same thing again and it hasn't changed, we don't store a second copy. Confirmed
working - the second Reliance fetch stored 0 new rows and recognised all 59 as unchanged.

### 5. A job tracker
Every download run is recorded: when it started, how many requests it made, how much
data it moved, and whether it finished. Each individual request within a run is also
tracked, so if a big download crashes halfway, it can pick up where it left off rather
than starting over.

### 6. A command to run it
```
python -m app.ingest.worker fetch RELIANCE     # download one company
python -m app.ingest.worker plan RELIANCE      # show what it would do, without doing it
python -m app.ingest.worker universe           # download the market-wide data
```

### 7. Two web endpoints
- `/api/meta/health` - is the app alive, and can it reach FinEdge?
- `/api/meta/freshness` - what data do we hold, and when did we last fetch it?

---

## What went wrong

**The API key was printed in the logs, in full, 59 times.**

I had written a redaction function and used it carefully in my own logging. But the
HTTP library, httpx, does its own logging - it prints every request URL it makes. The
key travels *in* the URL. So the very first live run produced 59 log lines each
containing the complete credential.

If that had been running on a server writing to a log file, the key would have been
sitting in plaintext on disk.

### The fix, and why it took two attempts

**First attempt:** attach a filter to the logging system that scrubs any text matching
`token=...` from every log message, no matter which library produced it. Applied to the
root of the logging system so nothing escapes it.

That worked for normal mode. But in verbose mode, **the key still leaked.**

**Why:** httpx doesn't log the URL as text. It passes a `URL` *object*. My filter was
checking "is this a string? then scrub it" - and a URL object isn't a string, so it
sailed straight through and only got converted to text later, during printing.

**Second attempt:** the filter now converts non-string values to text, checks whether
that text contains a token, and substitutes the scrubbed version when it does. Numbers
are left alone so that log formatting still works.

Verified against the live API: 59 requests logged, 59 redacted, zero occurrences of the
real key across 126 lines of output.

### A test that was lying

While fixing this, I found the first test I wrote for it **passed even though the leak
was real.** The test used pytest's log capture, but my logging setup deliberately
removes existing log handlers - including the one pytest was using to capture. So the
test was inspecting an empty list and cheerfully reporting success.

Rewrote it to attach its own handler and, importantly, to first assert that httpx
actually logged something. A test that can pass when the thing it tests never ran is
worse than no test.

### A second bug the fix uncovered
Verbose mode is supposed to show the httpx request lines. But once anything had quieted
that logger, it stayed quiet - the setup function only ever turned logging *down*, never
back up. So `-v` silently did nothing. Now it sets the level explicitly in both
directions.

---

## How I checked it works

| Check | Result |
| --- | --- |
| Automated tests | 50 pass |
| Code style (ruff) | clean |
| Fetch Reliance from the live API | 59 requested, 59 stored, 0 failed |
| Fetch it a second time | 59 recognised as unchanged, 0 stored again |
| Search all log output for the real key | not found |
| Search verbose log output for the real key | not found, all 59 redacted |
| `/api/meta/freshness` | reports 60 stored responses, 1 company, correct timestamp |
| `/api/meta/health` | reports FinEdge reachable, key configured, key not disclosed |

---

## One correction to the plan

The PRD estimated **63 requests per company**. The real number is **59**, because four
of the combinations it assumed were valid are rejected by the API (the year-to-date and
trailing-twelve-month cases described above).

This makes the eventual full download slightly cheaper than budgeted: roughly
**332,000 requests** for all 5,630 companies rather than 355,000.

---

## What's next

The frontend scaffold - React with the light/dark theme switcher - is the remaining
part of Phase 0. After that, Phase 1 is the big one: turning these raw stored responses
into properly structured tables, which is where the awkward reality that banks report
completely different figures from ordinary companies has to be dealt with.

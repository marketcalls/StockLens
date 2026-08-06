# The service layer

**What was asked:** keep the API and services modular so an AI agent can be
built on top of them later, and write the API and service docs.

---

## The problem with where it was

Every capability lived inside a FastAPI route. To ask "what is Reliance's P/E",
something had to make an HTTP request — even code running inside the same
process. An agent built on that would be talking to itself over the network:
serialising a question, sending it to localhost, deserialising the answer.

It also meant the rules were in the wrong place. Ownership checks on saved
screens lived in the route, so they only applied to browsers. Anything calling
the code another way got no such guarantee.

## What changed

Every capability is now a plain Python function in `app/services`. The routes
still exist and behave exactly as before, but each is a few lines that unpack the
request, call a function, and return what it gets.

```python
from app.services import company, screener

company.profile("RELIANCE")
screener.run("Price to Earning < 20 AND Return on equity > 12")
```

Six modules: `company`, `index`, `screener`, `ingest`, `workspace`, and the
errors they raise.

Four rules hold across all of them:

- **Plain data in, plain data out.** Strings and numbers go in; dicts and lists
  come out. Nothing that needs FastAPI to interpret.
- **Domain errors, not status codes.** A service raises `NotFound`. One module at
  the edge turns that into a 404. A non-HTTP caller gets a real Python exception
  instead of a number it has to look up.
- **Permission checks live in the service.** Asking for someone else's saved
  screen fails the same way no matter who is asking.
- **The database can be swapped in.** Every function takes an optional engine, so
  tests point at a temporary one without patching anything.

Two new route groups came out of this: `/api/indices` for index pages, and
`/api/superadmin` for ingestion control. Both were services first.

## Three things this turned up

Writing the docs meant checking every claim against the running app, and three
of them were false.

**An index claimed every constituent had fundamentals.** The Nifty 50 page
reported 50 of 50 loaded when only 7 companies had actually been downloaded. The
check asked whether the company had a market cap — but market cap comes from the
daily price quote, which every listed company has. It says nothing about whether
the financial statements were fetched. It now checks net profit, which only
exists after a download. Nifty 50 now honestly reports 7 of 50.

**The health check never looked at the database.** It reported "ok" based on
whether FinEdge answered. So if SQLite became unreachable — the failure that
breaks every single page — the health check would still say the app was fine, and
a container runtime would keep sending it traffic. It now checks the database and
returns 503 when that fails.

The same endpoint also called out to FinEdge on every hit. A container polling
health every ten seconds would have made 8,640 requests a day to a third party
for no benefit, and FinEdge being down doesn't stop us serving data we already
hold. That check is now opt-in with `?finedge=true`.

**Errors dropped the useful part.** A service raising `NotFound` attached the
symbol that was missing, but the HTTP layer threw it away and sent only the
sentence. A program handling the error had to parse the symbol back out of
English. The context now travels alongside the message.

## Testing

366 tests pass, up from 359.

The health tests are written so they cannot pass by accident. The test that
FinEdge is not called by default doesn't just check the response looks right — it
arms the mock to fail loudly if touched, and asserts zero calls. Its companion
asserts exactly one call when the flag is passed, which proves the mock is wired
up and the first test's silence means something.

There is also a test pinning the shape of query errors. That one is unusual: it
exists to stop a future tidy-up from flattening the response, because the query
editor reads the nested `position` field to underline the offending character.
Flattening it would break the underline quietly, with every test still green.

## Documents

- [API.md](../API.md) — the 49 HTTP endpoints, who can call what, and the units
- [SERVICES.md](../SERVICES.md) — the Python functions, written for an agent

Both cover what a schema can't: that money is in Rs. Crore, that percentages are
plain numbers, that a missing value is not zero, and that asking for consolidated
statements may get standalone ones because only 2,510 of 5,630 companies file
them.

## What this doesn't do

There is no agent yet. This is the surface one would be built against — nothing
here calls a model or decides anything.

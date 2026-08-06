# The Super Admin console

**What was asked:** working controls for the super administrator to trigger and
monitor the manual download — and proof the controls actually work.

---

## The page

`/admin`, visible only to a super administrator. The link does not appear in the
navigation for anyone else.

Four controls, each with its cost stated before you press it:

| Control | Cost |
| --- | --- |
| Sync the universe | 4 calls, seconds |
| Refresh prices | 1 call, seconds |
| Rebuild the screener table | no calls, under a minute |
| Backfill financial statements | 59 calls per company |

The backfill takes a company count and shows what it will cost before you commit
— 500 companies reads "29,500 calls · about 98 min". A live run gets its own
panel with a progress bar, and every control is disabled while it runs.

Below that, the last ten runs with status, calls, rows, bytes and time.

## Four faults found by using it

**The lock only worked inside one process.** "One job at a time" was a Python
dictionary in memory. A backfill started from the command line was completely
invisible to the web server, so the console would cheerfully have started a
second one — two downloads fighting over a database that takes a single writer,
at double the request rate against FinEdge.

The lock now asks the database, which is the only thing both processes can see.
Verified against a real running job: with a backfill going in a separate process,
the console refused to start another and named the one in the way.

A database lock brings its own problem: a process killed mid-run leaves a row
saying "running" forever, and nothing would ever start again. Two answers. A run
older than 24 hours is treated as abandoned — longer than the eighteen hours a
full backfill legitimately takes, so it can never cut in on a live job. And there
is a **Clear if dead** button for an operator who already knows the job died. It
says plainly that it does not stop a live job, because it can't.

**The progress bar always read 100%.** It showed "6,185 / 6,185" on a run that
was a fifth of the way through. Task rows are written as the run reaches each
company, so the denominator was only ever "tasks recorded so far" — done over
done, permanently full. It now counts companies, which the run knows up front:
"113 / 500 companies".

**The setup instructions created an account that could not sign in.** Running
`create-super-admin admin@stocklens.local` succeeded. Logging in with it returned
a validation error: `.local` is a reserved domain that the strict address check
refuses. The command line and the login endpoint had separate ideas of what an
address is, so an operator could follow the documented setup and be locked out of
the account they had just made, with nothing explaining why.

There is now one rule, used by both. It is deliberately permissive about the
domain: StockLens is self-hosted, the address is a login identifier rather than
somewhere mail is ever sent, and a deliverability check would reject exactly the
addresses an operator is most likely to choose. Nonsense is still rejected.

**A missing page wrapper.** The new pages ran edge to edge because they lacked
the container every other page uses.

## Proving the controls work

Claiming a button works because it returns 200 is not proof. So the whole
verification ran through the actual page:

1. A backfill was running in a separate process. The console showed it and
   refused to start another — **409, naming the blocking run**.
2. That process was killed, leaving a genuinely orphaned run still marked
   "running" and still blocking. Not a simulated one.
3. **Clear if dead** → "Run ec4a19e2 cleared. A new job can start." The history
   shows it as failed, with the reason.
4. **Sync the universe** → "Universe synced: 5,630 companies, 239 indices,
   23,367 memberships."
5. **Start backfill** with 500 → a new run appeared and climbed 1 → 5 → 8
   companies while being watched.

Every control did real work against the live API.

## Testing

384 backend tests and 78 front-end tests, up from 371 and 72.

Nine cover the lock, including the two cases that decide whether it is any use: a
job started elsewhere blocks a new one, and a job abandoned a day ago does not.
There is also a test that a seventeen-hour-old run still blocks, so nobody
"tidies" the staleness threshold down to something that would kill a live
backfill.

Six cover the progress bar, pinning the exact bug: given the run that read
6,185 / 6,185, it must report 113 / 500 and a 23% bar.

The email test is end to end on purpose — create through the same service the CLI
uses, then sign in over HTTP. Testing the validator alone would have missed it,
because each half was perfectly consistent with itself. The two halves disagreeing
was the whole bug.

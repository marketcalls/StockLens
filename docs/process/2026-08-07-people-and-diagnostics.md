# People and diagnostics

**What was asked:** a comprehensive, well-thought user management module, and
centralized logs with traceback capture and diagnostic pages.

These were asked for after the four-ask loop was set up, so the loop never
reached them. Neither existed: accounts could only be managed by a CLI on the
server, and a failure left no record anyone could get at.

---

## People

`/admin/people`, for administrators and above. Search and filter, what each
account owns, a detail view with its audit trail, role changes, suspend and
restore, and invitations.

The listing and the buttons are the easy part. The substance is four rules that
stop an administrator removing everyone's access — including their own:

- **You cannot lower your own role, or deactivate yourself.** Demoting yourself
  mid-task is the ordinary way to lose the console.
- **You cannot grant a role above your own.**
- **An administrator cannot act on a super administrator.** Without this an
  admin could promote themselves, and the two roles become one role.
- **The last active super administrator cannot be demoted or suspended.**

They live in the service, not in the routes, so a script or an agent cannot go
around them. The page mirrors them only to disable the control and say why —
"Locked: the last active super administrator, promote another first" reads as a
rule, where a live control that then errors reads as a fault. The server is still
the boundary; seven tests pin the page's copy of the rules against the service's,
because mirrored logic drifts.

### Two decisions worth stating

**Accounts are suspended, never deleted.** The audit log refers to them by id,
and deleting an account makes its own history unreadable — you would be left with
entries naming someone nobody can look up.

**An invitation returns a one-time password.** A self-hosted install has no mail
server, so there is nothing to send an invitation with. The password is shown
once, in a panel that says it cannot be shown again, and stored only as a hash.

## Diagnostics

`/admin/diagnostics`. Warnings and errors go to the database as well as standard
output, because a self-hosted install is usually a container nobody is watching —
a failure that only reaches stdout may as well not have been recorded.

Unhandled exceptions are captured with their traceback. The caller gets a 500
saying an administrator can find the detail; the traceback stays on the server,
because it names internal paths and can carry values from the failing call.

Records from a request carry their method, path and status. Everything else is
marked "background", which is the difference between *a user hit this* and *it
happened on its own* — usually the first thing worth knowing.

The table keeps the most recent 2,000 records, trimmed as new ones arrive, so it
cannot grow without bound on a long-running instance.

## What building it found

Writing the leak tests first turned up two ways the FinEdge key could still have
been logged. **Both were older than the feature**, and both affected what was
already being printed to standard output:

**Redaction ran on the template and the arguments separately.** So
`log("...token=%s", key)` had no `token=` anywhere for the filter to match — the
two halves are only joined when the record is formatted, and nothing redacted the
result.

**A traceback never passes through a filter at all.** It is rendered inside the
formatter, and it carries the URL of the call that failed, which is exactly where
the token lives.

Both are fixed by redacting the finished string, in a formatter now used by the
console handler too.

A third fault appeared on the way. The filter rewrote `"...token=%s"` into
`"...token=REDACTED"`, which destroyed the placeholder — so formatting then
failed and the record was **dropped with a logging error instead of written**. A
redaction rule that silently discards the log entry it was protecting is worse
than the leak it prevents. The template is now only rewritten when there is
nothing to interpolate into it.

## Verifying it

Against the live database, with a failure carrying a credential in its message
exactly as a real FinEdge error would:

| | |
| --- | --- |
| Key present anywhere in stored logs | **no** |
| `token=REDACTED` present | **yes** |
| Traceback captured | yes |
| Info-level chatter stored | no |

The second row matters as much as the first. An assertion that a secret is absent
passes trivially when nothing was stored at all; checking that the marker *is*
there proves redaction ran rather than the write having quietly failed.

That run also confirmed the property the handler was designed around, by
accident. The `log_record` table did not exist yet on the running instance, so
every write failed — and the process carried straight on to the next statement
rather than crashing. A logging handler that can turn a warning into an outage is
worse than no handler.

## What is not here

No log streaming, no alerting, no retention policy beyond the row cap, and no
export. An operator who needs those has a container log driver.

Passwords cannot be reset from the page. Someone locked out needs a new
invitation, or the CLI on the server.

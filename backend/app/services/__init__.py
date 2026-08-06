"""Service layer.

Every capability StockLens has is a plain Python function here, taking and
returning plain data. HTTP routes are thin wrappers; nothing in this package
imports FastAPI, knows about requests, or raises HTTP errors.

That split exists so a future agent can call these directly:

    from app.services import company, screener

    company.profile("RELIANCE")
    screener.run("Price to Earning < 20 AND Return on equity > 12")

rather than talking to itself over HTTP. It also makes every rule testable
without a client.

Errors are domain errors (`NotFound`, `InvalidQuery`), translated to status
codes at the edge in app/api.
"""

from app.services import company, index, ingest, screener, workspace
from app.services.errors import Forbidden, InvalidQuery, NotFound, ServiceError

__all__ = [
    "Forbidden",
    "InvalidQuery",
    "NotFound",
    "ServiceError",
    "company",
    "index",
    "ingest",
    "screener",
    "workspace",
]

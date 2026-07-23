"""Test-process defaults that prevent local credentials from changing fixtures."""

import os


# Completion fixtures exercise deterministic fallback routing. A developer's
# local .env must not turn those tests into live Amap route lookups.
os.environ["AMAP_API_KEY"] = ""

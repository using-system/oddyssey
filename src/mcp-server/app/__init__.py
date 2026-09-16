"""oddyssey MCP server package."""

import time

# The instant this package was first imported - the earliest point the
# process can stamp itself: the `oddyssey.server.start` span begins
# here and ends when the server starts serving (observation finding F3:
# the one-shot lifecycle was invisible to the telemetry).
IMPORTED_AT_NS = time.time_ns()

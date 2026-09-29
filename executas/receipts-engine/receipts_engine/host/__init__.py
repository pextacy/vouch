"""Anna host plumbing: stdio frames, invoke context, progress, sampling.

These four modules are the only place that knows the Executa wire protocol.
They are a dependency-free reimplementation of the three frames Vouch needs,
verified against the live host docs; the reference ``executa-sdk``
package is not published on PyPI, so vendoring or depending on it was not an
option.
"""

from .context import InvokeContext, bind_invoke, current_invoke_id
from .frames import MAX_STDIO_MESSAGE_BYTES, write_frame
from .progress import emit_progress
from .sampling import SamplingClient, SamplingError

__all__ = [
    "MAX_STDIO_MESSAGE_BYTES",
    "InvokeContext",
    "SamplingClient",
    "SamplingError",
    "bind_invoke",
    "current_invoke_id",
    "emit_progress",
    "write_frame",
]

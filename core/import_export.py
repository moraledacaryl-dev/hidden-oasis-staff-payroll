from __future__ import annotations

"""Compatibility stub for the retired spreadsheet import/export module.

The previous implementation depended on pandas, which is intentionally not part of the
production API requirements. Keep this module importable for older references, but fail
closed if a removed spreadsheet import/export path is invoked.
"""


def unavailable(*_args, **_kwargs):
    raise RuntimeError(
        "Spreadsheet import/export has been retired from this production build. "
        "Use supported API workflows or restore a maintained implementation with declared dependencies."
    )


import_data = unavailable
export_data = unavailable

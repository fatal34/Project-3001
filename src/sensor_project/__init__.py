"""Offline gap reconstruction and validation for MMA3001 Dataset 2.

Public functions validate real finite one-dimensional inputs and reject
extrapolation. Values retain the supplied sensor units, and time is in seconds.
"""

from .interpolation import integrate_linear, mask_block, reconstruct, scalar_linear
from .metrics import error_metrics
from .data import load_environment, prepare_sources

__all__ = ["reconstruct", "scalar_linear", "mask_block", "integrate_linear", "error_metrics",
           "load_environment", "prepare_sources"]

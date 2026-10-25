"""Finite, unit-aware error summaries for held-out recorded sensor values."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from .interpolation import _finite_vector


def error_metrics(y_true: ArrayLike, y_pred: ArrayLike) -> dict[str, float]:
    """Summarise reconstruction residuals against withheld recorded values.

    Parameters
    ----------
    y_true : array_like, shape (n,)
        At least one finite withheld recorded value. These are recorded targets,
        not independently calibrated physical ground truth.
    y_pred : array_like, shape (n,)
        Matching finite reconstructed values in the same unit as ``y_true``.

    Returns
    -------
    dict[str, float]
        ``mae`` (mean absolute error), ``rmse`` (root mean squared error),
        ``max_abs_error`` (largest absolute residual), and ``bias`` (mean of
        prediction minus target). All quantities preserve the original unit.

    Raises
    ------
    ValueError
        If inputs are empty, non-finite, complex, non-vector, mismatched, or
        produce residuals or metrics outside finite floating-point range.

    Examples
    --------
    >>> error_metrics([400, 410, 420], [401, 408, 420])
    {'mae': 1.0, 'rmse': 1.2909944487358056, 'max_abs_error': 2.0, 'bias': -0.3333333333333333}

    Notes
    -----
    The square root of the mean squared error uses scaled residuals to avoid
    an unnecessary overflow when finite sensor residuals are large. A positive
    bias means that reconstruction overestimates the withheld measurements.
    """
    target = _finite_vector(y_true, "y_true", minimum=1)
    prediction = _finite_vector(y_pred, "y_pred", minimum=1)
    if target.size != prediction.size:
        raise ValueError("y_true and y_pred must have the same length")
    with np.errstate(over="ignore", invalid="ignore"):
        residual = prediction - target
    if not np.all(np.isfinite(residual)):
        raise ValueError("residuals must remain within finite floating-point range")
    scale = float(np.max(np.abs(residual)))
    if scale == 0.0:
        return {"mae": 0.0, "rmse": 0.0, "max_abs_error": 0.0, "bias": 0.0}
    # Scaling also keeps mean reductions finite when the sum itself is huge.
    scaled = residual / scale
    result = {
        "mae": float(scale * np.mean(np.abs(scaled))),
        "rmse": float(scale * np.sqrt(np.mean(scaled * scaled))),
        "max_abs_error": scale,
        "bias": float(scale * np.mean(scaled)),
    }
    if not all(np.isfinite(number) for number in result.values()):
        raise ValueError("error metrics must remain within finite floating-point range")
    return result

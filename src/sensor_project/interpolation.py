"""Guarded offline interpolation for gaps in a one-dimensional sensor series.

The functions use timestamps in seconds and keep the supplied value unit.  Gap
reconstruction uses observations on both sides and is therefore an offline task,
not a forecast or an online missing-data alarm.
"""

from __future__ import annotations

from bisect import bisect_right
from numbers import Integral

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.interpolate import PchipInterpolator


def _finite_vector(values: ArrayLike, name: str, *, minimum: int = 0) -> NDArray[np.float64]:
    """Return a real finite one-dimensional array with a useful error message."""
    original = np.asarray(values)
    if np.iscomplexobj(original):
        raise ValueError(f"{name} must contain real numbers")
    try:
        array = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain real numbers") from exc
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if array.size < minimum:
        raise ValueError(f"{name} must contain at least {minimum} values")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite numbers")
    return array


def _series(time_s: ArrayLike, values: ArrayLike) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Validate matching observations without silently sorting or deduplicating."""
    time = _finite_vector(time_s, "time_s", minimum=2)
    value = _finite_vector(values, "values", minimum=2)
    if time.size != value.size:
        raise ValueError("time_s and values must have the same length")
    if np.any(time[1:] <= time[:-1]):
        raise ValueError("time_s must be strictly increasing without duplicates")
    return time, value


def _queries(t_known_s: NDArray[np.float64], t_query_s: ArrayLike) -> NDArray[np.float64]:
    """Validate queries while preserving their requested order."""
    query = _finite_vector(t_query_s, "t_query_s")
    if np.any(query < t_known_s[0]) or np.any(query > t_known_s[-1]):
        raise ValueError("query times must lie within the known time range; extrapolation is disabled")
    return query


def reconstruct(
    t_known_s: ArrayLike,
    y_known: ArrayLike,
    t_query_s: ArrayLike,
    method: str = "linear",
) -> NDArray[np.float64]:
    """Reconstruct an offline sensor gap from retained observations.

    Parameters
    ----------
    t_known_s : array_like, shape (n,)
        At least two finite, strictly increasing observation times in seconds.
    y_known : array_like, shape (n,)
        Finite observed values. Their unit is preserved in the predictions.
    t_query_s : array_like, shape (m,)
        Finite times in the closed observed interval. Order is preserved and an
        empty query returns an empty array.
    method : {"previous", "linear", "pchip"}, default "linear"
        Previous-observation hold is the simple baseline. Linear interpolation
        joins adjacent observations. PCHIP uses local shape-preserving cubic
        segments; it is fitted only to the supplied retained observations.

    Returns
    -------
    numpy.ndarray, shape (m,)
        Reconstructed values, including exact supplied values at known knots.

    Raises
    ------
    ValueError
        If inputs are non-finite, complex, non-vector, mismatched, unsorted or
        duplicated; if queries require extrapolation; or if method is unknown.

    Examples
    --------
    >>> reconstruct([0, 2, 5], [400, 420, 450], [1, 3]).tolist()
    [410.0, 430.0]
    >>> reconstruct([0, 2], [400, 420], [1], method="previous").tolist()
    [400.0]

    Notes
    -----
    A withheld measurement must never be passed in ``y_known``. The
    :func:`mask_block` helper builds disjoint context and truth arrays. Using
    right-hand observations makes this an offline reconstruction experiment.
    """
    if not isinstance(method, str) or method not in {"previous", "linear", "pchip"}:
        raise ValueError("method must be 'previous', 'linear', or 'pchip'")
    time, values = _series(t_known_s, y_known)
    query = _queries(time, t_query_s)
    if query.size == 0:
        return np.empty(0, dtype=np.float64)
    if method == "previous":
        # side='right' makes a query at a known knot return that observation.
        index = np.searchsorted(time, query, side="right") - 1
        return values[index].copy()
    if method == "linear":
        # NumPy performs the same segment search and blend as scalar_linear in
        # compiled code, avoiding a Python iteration for every query.
        return np.interp(query, time, values)
    interpolator = PchipInterpolator(time, values, extrapolate=False)
    return np.asarray(interpolator(query), dtype=np.float64)


def scalar_linear(
    t_known_s: ArrayLike, y_known: ArrayLike, t_query_s: ArrayLike
) -> NDArray[np.float64]:
    """Evaluate piecewise-linear interpolation with a readable Python loop.

    Parameters
    ----------
    t_known_s : array_like, shape (n,)
        Finite, strictly increasing known times in seconds, with ``n >= 2``.
    y_known : array_like, shape (n,)
        Finite retained observations in the sensor's value unit.
    t_query_s : array_like, shape (m,)
        Finite query times in the closed known interval, in any order.

    Returns
    -------
    numpy.ndarray, shape (m,)
        Piecewise-linear predictions in query order and the original value unit.

    Raises
    ------
    ValueError
        If observations or queries violate the same guards as :func:`reconstruct`.

    Examples
    --------
    >>> scalar_linear([0, 2, 5], [400, 420, 450], [1, 3]).tolist()
    [410.0, 430.0]

    Notes
    -----
    This is a genuine scalar implementation of the same interpolation
    algorithm, using binary segment search rather than a deliberately wasteful
    scan. Comparing it with the vectorised implementation measures the cost of
    Python-level iteration, not a different scientific method.
    """
    time, values = _series(t_known_s, y_known)
    query = _queries(time, t_query_s)
    time_list = time.tolist()
    value_list = values.tolist()
    prediction = np.empty(query.size, dtype=np.float64)
    for index, requested_time in enumerate(query):
        right = bisect_right(time_list, float(requested_time))
        left = min(right - 1, len(time_list) - 2)
        fraction = (requested_time - time_list[left]) / (time_list[left + 1] - time_list[left])
        prediction[index] = value_list[left] + fraction * (value_list[left + 1] - value_list[left])
    return prediction


def mask_block(
    t_s: ArrayLike,
    y: ArrayLike,
    start: int,
    count: int,
    context_points: int = 4,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Remove one contiguous block and return only its neighbouring context.

    Parameters
    ----------
    t_s : array_like, shape (n,)
        Finite, strictly increasing full observation times in seconds.
    y : array_like, shape (n,)
        Matching finite sensor values in their original unit.
    start : int
        Zero-based index of the first held-out observation.
    count : int
        Positive number of consecutive observations to withhold.
    context_points : int, default 4
        Number of retained observations on each side. At least two are required
        so a cubic method can estimate local slopes from neighbouring intervals.

    Returns
    -------
    known_t_s : numpy.ndarray, shape (2 * context_points,)
        Left then right retained times, strictly excluding the withheld block.
    known_y : numpy.ndarray, shape (2 * context_points,)
        Retained values corresponding to ``known_t_s``.
    query_t_s : numpy.ndarray, shape (count,)
        Times of the withheld observations, used as reconstruction queries.
    truth : numpy.ndarray, shape (count,)
        Withheld recorded values for scoring only, never an interpolator input.

    Raises
    ------
    ValueError
        If the full series is invalid, an index or count is not an integer, the
        count is non-positive, fewer than two context points are requested per
        side, or the block has insufficient neighbouring observations.

    Examples
    --------
    >>> known_t, known_y, query_t, truth = mask_block(
    ...     np.arange(10), 400 + np.arange(10), start=4, count=2, context_points=2
    ... )
    >>> known_t.tolist(), query_t.tolist(), truth.tolist()
    ([2.0, 3.0, 6.0, 7.0], [4.0, 5.0], [404.0, 405.0])

    Notes
    -----
    All outputs are copies. No withheld value is used to select or construct
    context. The caller must select block locations and method settings without
    consulting held-out reconstruction errors.
    """
    time, values = _series(t_s, y)
    for name, number in (("start", start), ("count", count), ("context_points", context_points)):
        if isinstance(number, (bool, np.bool_)) or not isinstance(number, Integral):
            raise ValueError(f"{name} must be an integer")
    if count < 1:
        raise ValueError("count must be positive")
    if context_points < 2:
        raise ValueError("context_points must be at least two per side")
    stop = start + count
    if start < context_points or stop + context_points > time.size:
        raise ValueError("the held-out block must have enough context observations on both sides")
    known_time = np.concatenate((time[start - context_points:start], time[stop:stop + context_points]))
    known_values = np.concatenate((values[start - context_points:start], values[stop:stop + context_points]))
    return known_time, known_values, time[start:stop].copy(), values[start:stop].copy()


def integrate_linear(time_s: ArrayLike, value: ArrayLike) -> float:
    """Integrate a piecewise-linear observed signal with trapezoidal segments.

    Parameters
    ----------
    time_s : array_like, shape (n,)
        Finite, strictly increasing times in seconds, with ``n >= 2``.
    value : array_like, shape (n,)
        Matching finite signal values. Non-uniform time spacing is supported.

    Returns
    -------
    float
        Signed area under the piecewise-linear curve in value-unit seconds.

    Raises
    ------
    ValueError
        If arrays are invalid, non-finite, mismatched or not strictly ordered.

    Examples
    --------
    >>> integrate_linear([0, 1, 3], [2, 4, 6])
    13.0

    Notes
    -----
    Trapezoidal integration is exact for the chosen piecewise-linear
    representation. This does not establish an exact physical integral of the
    unknown signal between measurements. The time coordinate must be seconds;
    a datetime index must be converted explicitly by the caller.
    """
    time, values = _series(time_s, value)
    return float(np.trapezoid(values, x=time))

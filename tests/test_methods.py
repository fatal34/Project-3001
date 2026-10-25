"""Independent mathematical checks and input contracts for reconstruction."""

import numpy as np
import pytest

from sensor_project import error_metrics, integrate_linear, mask_block, reconstruct, scalar_linear


@pytest.mark.parametrize("method", ["linear", "pchip"])
def test_affine_signal_exact_on_irregular_grid(method):
    time = np.array([0.0, 0.7, 2.4, 6.1, 8.0])
    query = np.array([8.0, 0.0, 1.2, 7.3, 0.3, 6.1])
    observed = 405.0 + 3.7 * time
    expected = 405.0 + 3.7 * query
    np.testing.assert_allclose(reconstruct(time, observed, query, method), expected, rtol=0, atol=1e-12)


@pytest.mark.parametrize("method", ["previous", "linear", "pchip"])
def test_knots_and_constant_signal_are_preserved(method):
    time = [0.0, 2.0, 3.0, 7.0]
    values = [425.0, 470.0, 450.0, 490.0]
    np.testing.assert_allclose(reconstruct(time, values, time, method), values, rtol=0, atol=1e-12)
    np.testing.assert_allclose(reconstruct(time, [420.0] * 4, [0.4, 2.5, 5.2], method), 420.0)


def test_linear_matches_hand_computed_irregular_segments():
    # At 0.5 s: 400 + (0.5/2)*40 = 410; at 3 s: 440 + (1/3)*(-60) = 420.
    actual = reconstruct([0, 2, 5], [400, 440, 380], [0.5, 3.0])
    np.testing.assert_array_equal(actual, [410.0, 420.0])


def test_previous_is_left_hold_and_exact_at_knots():
    actual = reconstruct([0, 2, 5], [400, 440, 380], [0, 1.9, 2, 4.9, 5], "previous")
    np.testing.assert_array_equal(actual, [400, 400, 440, 440, 380])


def test_pchip_stays_within_each_monotone_bracket():
    time = np.array([0.0, 1.5, 2.0, 7.0, 9.0])
    values = np.array([400.0, 400.5, 415.0, 418.0, 450.0])
    for index in range(len(time) - 1):
        query = np.linspace(time[index], time[index + 1], 101)
        prediction = reconstruct(time, values, query, "pchip")
        assert np.min(prediction) >= values[index] - 1e-12
        assert np.max(prediction) <= values[index + 1] + 1e-12
        assert np.min(np.diff(prediction)) >= -1e-12


def test_pchip_turning_point_has_no_local_overshoot():
    time = [0.0, 1.0, 3.0, 4.0]
    values = [400.0, 450.0, 410.0, 430.0]
    query = np.linspace(0.0, 4.0, 1001)
    prediction = reconstruct(time, values, query, "pchip")
    assert np.min(prediction) >= 400.0
    assert np.max(prediction) <= 450.0


def test_pchip_matches_independent_three_point_hermite_calculation():
    # For y=[0,1,4] and equal spacing, secants are 1 and 3. The PCHIP
    # harmonic-mean interior slope is 1.5, with endpoint slopes 0 and 4.
    # At each segment midpoint, Hermite coefficients are .5,.125,.5,-.125.
    expected_left = 0.5 * 0 + 0.125 * 0 + 0.5 * 1 - 0.125 * 1.5
    expected_right = 0.5 * 1 + 0.125 * 1.5 + 0.5 * 4 - 0.125 * 4
    actual = reconstruct([0, 1, 2], [0, 1, 4], [0.5, 1.5], "pchip")
    np.testing.assert_allclose(actual, [expected_left, expected_right], rtol=0, atol=1e-14)


@pytest.mark.parametrize("method", ["previous", "linear", "pchip"])
@pytest.mark.parametrize("query", [[-0.001], [2.001], [0.5, 3.0]])
def test_extrapolation_is_rejected(method, query):
    with pytest.raises(ValueError, match="extrapolation"):
        reconstruct([0, 1, 2], [400, 410, 420], query, method)


@pytest.mark.parametrize(
    "time,values,query",
    [
        ([0], [400], [0]),
        ([0, 1], [400], [0.5]),
        ([1, 0], [400, 410], [0.5]),
        ([0, 0, 1], [400, 405, 410], [0.5]),
        ([0, np.nan], [400, 410], [0.5]),
        ([0, np.inf], [400, 410], [0.5]),
        ([0, 1], [400, np.nan], [0.5]),
        ([0, 1], [400, np.inf], [0.5]),
        ([[0, 1]], [400, 410], [0.5]),
        ([0, 1], [[400, 410]], [0.5]),
        ([0, 1], [400, 410], [[0.5]]),
        ([0, 1], [400, 410], [np.nan]),
        ([0, 1], [400, 410], [np.inf]),
        ([0, 1], [400 + 1j, 410], [0.5]),
    ],
)
def test_invalid_series_and_queries_are_rejected(time, values, query):
    with pytest.raises(ValueError):
        reconstruct(time, values, query)


@pytest.mark.parametrize("method", ["cubic", "LINEAR", None, 3, []])
def test_unknown_method_rejected(method):
    with pytest.raises(ValueError, match="method"):
        reconstruct([0, 1], [400, 410], [0.5], method)


@pytest.mark.parametrize("method", ["previous", "linear", "pchip"])
def test_empty_queries_return_empty_float_vector(method):
    result = reconstruct([0, 1], [400, 410], [], method)
    assert result.shape == (0,)
    assert result.dtype == np.float64


def test_mask_block_excludes_every_held_out_value_and_uses_requested_context():
    time = np.array([0, 1, 3, 4, 7, 8, 10, 11, 15, 18, 20, 21], dtype=float)
    values = 400 + np.arange(time.size, dtype=float)
    known_t, known_y, query_t, truth = mask_block(time, values, start=4, count=3, context_points=3)
    np.testing.assert_array_equal(known_t, time[[1, 2, 3, 7, 8, 9]])
    np.testing.assert_array_equal(known_y, values[[1, 2, 3, 7, 8, 9]])
    np.testing.assert_array_equal(query_t, time[4:7])
    np.testing.assert_array_equal(truth, values[4:7])
    assert not np.intersect1d(known_t, query_t).size
    assert not np.intersect1d(known_y, truth).size
    # Extreme replacement of only the withheld values cannot alter model input.
    changed = values.copy()
    changed[4:7] = [10000, -10000, 50000]
    changed_t, changed_y, _, _ = mask_block(time, changed, 4, 3, 3)
    np.testing.assert_array_equal(changed_t, known_t)
    np.testing.assert_array_equal(changed_y, known_y)


def test_mask_outputs_are_copies_and_input_is_not_mutated():
    time = np.arange(12, dtype=float)
    values = 400.0 + time
    before = values.copy()
    arrays = mask_block(time, values, 4, 3)
    for array in arrays:
        assert not np.shares_memory(array, time)
        assert not np.shares_memory(array, values)
    arrays[-1][0] = -1.0
    np.testing.assert_array_equal(values, before)


@pytest.mark.parametrize(
    "start,count,context",
    [(0, 2, 2), (3, 0, 2), (3, -1, 2), (8, 3, 2), (4, 1, 1), (4.0, 1, 2), (4, 1.5, 2), (4, 1, 2.0), (True, 1, 2)],
)
def test_mask_invalid_counts_and_edge_blocks_rejected(start, count, context):
    with pytest.raises(ValueError):
        mask_block(np.arange(12), np.arange(12) + 400, start, count, context)


def test_default_mask_context_is_four_observations_per_side():
    known_t, _, query_t, _ = mask_block(np.arange(12), np.arange(12) + 400, 4, 4)
    assert known_t.size == 8
    np.testing.assert_array_equal(query_t, [4, 5, 6, 7])


def test_scalar_and_vector_linear_match_for_irregular_unordered_queries():
    rng = np.random.default_rng(148)
    time = np.cumsum(rng.uniform(0.1, 4.0, 251))
    values = 450 + rng.normal(0, 25, time.size).cumsum()
    query = rng.uniform(time[0], time[-1], 2001)
    query[:2] = time[[0, -1]]
    np.testing.assert_allclose(scalar_linear(time, values, query), reconstruct(time, values, query), rtol=0, atol=2e-13)


def test_scalar_linear_independently_matches_manual_result():
    np.testing.assert_allclose(scalar_linear([0, 2, 5], [400, 440, 380], [0.5, 3]), [410, 420])
    with pytest.raises(ValueError, match="extrapolation"):
        scalar_linear([0, 2], [400, 440], [3])


def test_error_metrics_match_manual_residual_calculation():
    result = error_metrics([400, 410, 420, 430], [401, 408, 420, 433])
    assert result["mae"] == pytest.approx(1.5)
    assert result["rmse"] == pytest.approx(np.sqrt(14.0 / 4.0))
    assert result["max_abs_error"] == 3.0
    assert result["bias"] == pytest.approx(0.5)


def test_identical_predictions_have_zero_metrics():
    assert error_metrics([400, 410], [400, 410]) == {
        "mae": 0.0, "rmse": 0.0, "max_abs_error": 0.0, "bias": 0.0
    }


def test_scaled_rmse_handles_large_finite_residuals():
    result = error_metrics([0, 0], [1e200, -1e200])
    assert result["mae"] == 1e200
    assert result["rmse"] == 1e200
    assert result["bias"] == 0.0


@pytest.mark.parametrize(
    "truth,prediction",
    [([], []), ([400], [400, 410]), ([400, np.nan], [400, 410]), ([400], [np.inf]), ([[400]], [[400]]), ([1e308], [-1e308])],
)
def test_invalid_metrics_rejected(truth, prediction):
    with pytest.raises(ValueError):
        error_metrics(truth, prediction)


def test_irregular_trapezoidal_integral_matches_manual_areas():
    # Areas: (2+4)/2 * 1 = 3 and (4+6)/2 * 2 = 10.
    assert integrate_linear([0, 1, 3], [2, 4, 6]) == 13.0


def test_linear_integral_exact_for_affine_signal_and_shifted_time_origin():
    time = np.array([10.0, 10.3, 12.5, 14.0])
    values = 2.0 * time + 3.0
    # Integral of 2t + 3 is t^2 + 3t.
    expected = (14.0**2 + 3 * 14.0) - (10.0**2 + 3 * 10.0)
    assert integrate_linear(time, values) == pytest.approx(expected)
    assert integrate_linear(time - time[0], values) == pytest.approx(expected)


@pytest.mark.parametrize("time,values", [([0], [2]), ([0, 0], [2, 4]), ([1, 0], [2, 4]), ([0, 1], [2, np.nan])])
def test_invalid_integration_input_rejected(time, values):
    with pytest.raises(ValueError):
        integrate_linear(time, values)

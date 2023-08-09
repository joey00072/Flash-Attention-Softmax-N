from math import exp

from pytest import mark
from torch import float16, randn_like, ones, Tensor
from torch.testing import assert_close

from src.functional import slow_attention, slow_attention_redux
from src.flash_attn_triton_softmax1 import attention
from tests.common import get_query_key_value, device_name


@mark.parametrize("dtype", [float16])
@mark.parametrize("is_causal", [False, True])
@mark.parametrize("scale", [None, 0.3])
def test_attention(device_name, dtype, is_causal, scale):
    batch_size = (32, 32)
    max_sequence_len = 1024
    embed_dimension = 32

    atol = 1e-2 if is_causal else 1e-3
    rtol = 0.

    # Test forward step,
    query, key, value = get_query_key_value(batch_size, max_sequence_len, embed_dimension, device=device_name, dtype=dtype)
    actual = attention(query, key, value, is_causal, scale)
    expected = slow_attention(query, key, value, is_causal=is_causal, scale=scale, use_softmax1=True)
    assert_close(actual, expected, atol=atol, rtol=rtol)

    # and backward step.
    doutput = randn_like(actual)
    actual.backward(doutput)
    actual_dvalue, value.grad = value.grad.clone(), None
    actual_dkey, key.grad = key.grad.clone(), None
    actual_dquery, query.grad = query.grad.clone(), None
    expected.backward(doutput)
    expected_dvalue, value.grad = value.grad.clone(), None
    expected_dkey, key.grad = key.grad.clone(), None
    expected_dquery, query.grad = query.grad.clone(), None
    assert_close(actual_dvalue, expected_dvalue, atol=atol, rtol=rtol)
    assert_close(actual_dkey, expected_dkey, atol=atol, rtol=rtol)
    assert_close(actual_dquery, expected_dquery, atol=atol, rtol=rtol)


@mark.parametrize("dtype", [float16])
@mark.parametrize("is_causal", [False, True])
@mark.parametrize("scale", [None, 0.4])
def test_attention_redux(device_name, dtype, is_causal, scale):
    batch_size = (32, 8)
    max_sequence_len = 1024
    embed_dimension = 64

    atol = 1e-2 if is_causal else 1e-3
    rtol = 0.

    # Test forward step,
    query, key, value = get_query_key_value(batch_size, max_sequence_len, embed_dimension, device=device_name, dtype=dtype)
    actual = attention(query, key, value, is_causal, scale)
    expected = slow_attention_redux(query, key, value, is_causal=is_causal, scale=scale, use_softmax1=True)
    assert_close(actual, expected, atol=atol, rtol=rtol)

    # and backward step.
    doutput = randn_like(actual)
    actual.backward(doutput)
    actual_dvalue, value.grad = value.grad.clone(), None
    actual_dkey, key.grad = key.grad.clone(), None
    actual_dquery, query.grad = query.grad.clone(), None
    expected.backward(doutput)
    expected_dvalue, value.grad = value.grad.clone(), None
    expected_dkey, key.grad = key.grad.clone(), None
    expected_dquery, query.grad = query.grad.clone(), None
    assert_close(actual_dvalue, expected_dvalue, atol=atol, rtol=rtol)
    assert_close(actual_dkey, expected_dkey, atol=atol, rtol=rtol)
    assert_close(actual_dquery, expected_dquery, atol=atol, rtol=rtol)


def test_simple_case(device_name):
    N = 6
    L = 1024
    S = 1024 + 128
    E = 64
    Ev = 64
    scale = 0.3
    weight = 0.1

    query = weight * ones((N, 1, L, E), device=device_name, dtype=float16)
    key = weight * ones((N, 1, S, E), device=device_name, dtype=float16)
    value = weight * ones((N, 1, S, Ev), device=device_name, dtype=float16)

    output_0a = slow_attention(query, key, value, scale=scale, use_softmax1=True)
    output_1a = attention(query, key, value, False, scale)

    expected_a_shape = weight * ones((N, 1, L, Ev), device=device_name, dtype=float16)
    expected_a_factor = S * exp(weight**2 * E * scale) / (1 + S * exp(weight**2 * E * scale))
    expected_a = expected_a_shape * expected_a_factor

    assert_close(output_0a, expected_a)
    assert_close(output_1a, expected_a)

    output_0b = slow_attention(query, key, value, scale=scale, is_causal=True, use_softmax1=True)
    output_1b = attention(query, key, value, True, scale)

    expected_b_factors = [(l + S - L) * exp(weight**2 * E * scale) / (1 + (l + S - L) * exp(weight**2 * E * scale)) for l in range(1, L + 1)]
    expected_b = N * Ev * weight * Tensor([expected_b_factors]).to(device=device_name, dtype=float16)

    assert_close(output_0b.sum(dim=0).sum(dim=-1), expected_b)
    assert_close(output_1b.sum(dim=0).sum(dim=-1), expected_b)

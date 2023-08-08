from math import sqrt

from pytest import mark
from torch import float16, randn_like, bfloat16
from torch.testing import assert_close

from src.functional import slow_attention
from src.flash_attn_triton_og import attention
from tests.common import get_query_key_value, device_name


@mark.parametrize("dtype", [float16])
@mark.parametrize("is_causal", [False, True])
def test_attention(device_name, dtype, is_causal):
    batch_size = (32, 32)
    max_sequence_len = 1024
    embed_dimension = 32

    atol = 1e-2 if is_causal else 1e-3
    rtol = 0.

    # Test forward step,
    query, key, value = get_query_key_value(batch_size, max_sequence_len, embed_dimension, device=device_name, dtype=dtype)
    actual = attention(query, key, value, is_causal, 1 / sqrt(query.size(-1)))
    expected = slow_attention(query, key, value, is_causal=is_causal)
    assert_close(actual, expected, atol=atol, rtol=rtol)

    # and backward step.
    doutput = randn_like(query)
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

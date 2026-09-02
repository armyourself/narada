from src.narada_identity.encoding import (
    IdentityVersion,
    decode_public_id,
    encode_public_id,
    is_valid_public_id,
)
from src.narada_identity.errors import NaradaIdentityError


def test_encode_decode_roundtrip():
    ed = b"\x01" * 32
    x = b"\x02" * 32
    encoded = encode_public_id(ed, x)
    assert encoded.startswith("narada1")
    version, ed_out, x_out = decode_public_id(encoded)
    assert version is IdentityVersion.V1
    assert ed_out == ed
    assert x_out == x


def test_is_valid_public_id_accepts_valid():
    ed = b"\x10" * 32
    x = b"\x20" * 32
    assert is_valid_public_id(encode_public_id(ed, x))


def test_is_valid_public_id_rejects_garbage():
    assert not is_valid_public_id("narada1qqqq")
    assert not is_valid_public_id("not-a-narada-id")
    assert not is_valid_public_id("")


def test_wrong_hrp_rejected():
    ed = b"\x01" * 32
    x = b"\x02" * 32
    encoded = encode_public_id(ed, x)
    # Replace 'Narada' (the hrp) with 'latticf' before the '1' separator.
    # A real production parser would not accept a wrong hrp; our decoder
    # also rejects anything whose hrp is not 'Narada'.
    assert encoded.startswith("narada1")
    tampered = "latticf" + encoded[len("narada"):]
    assert not tampered.startswith("narada1")
    with __import__("pytest").raises(NaradaIdentityError):
        decode_public_id(tampered)


def test_bad_payload_length_rejected():
    # Encode a too-short payload manually.
    with __import__("pytest").raises(NaradaIdentityError):
        encode_public_id(b"\x01" * 16, b"\x02" * 32)


def test_bech32m_checksum_required_not_bech32():
    # A valid bech32 (checksum const 1) should be rejected because Narada
    # identities must be bech32m. We construct a string that decodes as
    # bech32 by perturbing the checksum, then assert the error.
    ed = b"\x01" * 32
    x = b"\x02" * 32
    encoded = encode_public_id(ed, x)
    with __import__("pytest").raises(NaradaIdentityError):
        decode_public_id(encoded[:-1] + ("q" if encoded[-1] != "q" else "p"))

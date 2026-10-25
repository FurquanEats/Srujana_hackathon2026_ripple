from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from ripple_core import signing
from ripple_core.clock import IST, FixedClock, SimClock
from ripple_core.messages import (
    AccountRef,
    AccountType,
    Exit,
    ExitMode,
    Notice,
    NoticeResponse,
    OnwardHop,
    Payment,
    Rail,
)
from ripple_core.money import rupees
from ripple_core.signing import Keyring, MemoryReplayGuard, SigningKey, open_sealed, seal

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=IST)


@pytest.fixture
def bank_b() -> SigningKey:
    return SigningKey.generate("bank-b-1", "bank-b")


@pytest.fixture
def keyring(bank_b: SigningKey) -> Keyring:
    ring = Keyring()
    ring.add(bank_b.kid, bank_b.owner, bank_b.public_pem())
    return ring


def open_(
    envelope: str,
    keyring: Keyring,
    clock: FixedClock,
    guard: MemoryReplayGuard | None = None,
    recipient: str = "cfcfrms",
) -> signing.Opened:
    return open_sealed(
        envelope, keyring=keyring, recipient=recipient, clock=clock, replay=guard or MemoryReplayGuard()
    )


def test_a_sealed_message_opens_once(bank_b: SigningKey, keyring: Keyring) -> None:
    clock = FixedClock(T0)
    guard = MemoryReplayGuard()
    envelope = seal({"hello": "world"}, key=bank_b, recipient="cfcfrms", clock=clock, idempotency_key="k1")

    opened = open_(envelope, keyring, clock, guard)

    assert opened.sender == "bank-b"
    assert opened.payload == {"hello": "world"}
    assert opened.idempotency_key == "k1"
    with pytest.raises(signing.ReplayedEnvelopeError):
        open_(envelope, keyring, clock, guard)


def test_tampered_payload_fails(bank_b: SigningKey, keyring: Keyring) -> None:
    clock = FixedClock(T0)
    header, _, sig = seal({"amount": 1}, key=bank_b, recipient="cfcfrms", clock=clock).split(".")
    forged_body = signing._b64(signing._canonical({"amount": 1_000_000}))
    with pytest.raises(signing.BadSignatureError):
        open_(f"{header}.{forged_body}.{sig}", keyring, clock)


def test_a_key_cannot_sign_for_another_institution(keyring: Keyring) -> None:
    clock = FixedClock(T0)
    impostor = SigningKey("bank-b-1", "bank-c", SigningKey.generate("x", "y").private)
    with pytest.raises(signing.UnknownKeyError):
        open_(seal({}, key=impostor, recipient="cfcfrms", clock=clock), keyring, clock)
    with pytest.raises(ValueError, match="already bound"):
        keyring.add("bank-b-1", "bank-c", impostor.public_pem())


def test_wrong_recipient_stale_and_unknown_key(bank_b: SigningKey, keyring: Keyring) -> None:
    clock = FixedClock(T0)
    envelope = seal({}, key=bank_b, recipient="dpip", clock=clock)
    with pytest.raises(signing.WrongRecipientError):
        open_(envelope, keyring, clock)
    old = seal({}, key=bank_b, recipient="cfcfrms", clock=clock)
    clock.advance(timedelta(minutes=5))
    with pytest.raises(signing.StaleEnvelopeError):
        open_(old, keyring, clock)
    stranger = SigningKey.generate("unknown", "bank-z")
    with pytest.raises(signing.UnknownKeyError):
        open_(seal({}, key=stranger, recipient="cfcfrms", clock=clock), keyring, clock)


@pytest.mark.parametrize("envelope", ["", "a.b", "a.b.c.d", "!!!.e30.e30", "e30.e30.e30", "W10.e30.e30"])
def test_malformed_envelopes_are_rejected(envelope: str, keyring: Keyring) -> None:
    with pytest.raises(signing.MalformedEnvelopeError):
        open_(envelope, keyring, FixedClock(T0))


def test_none_algorithm_is_rejected(bank_b: SigningKey, keyring: Keyring) -> None:
    header = signing._b64(
        signing._canonical(
            {
                "alg": "none",
                "typ": signing.TYPE,
                "kid": bank_b.kid,
                "iss": "bank-b",
                "aud": "cfcfrms",
                "iat": int(T0.timestamp()),
                "nonce": "n",
                "idem": "i",
            }
        )
    )
    with pytest.raises(signing.MalformedEnvelopeError, match="algorithm"):
        open_(f"{header}.e30.AAAA", keyring, FixedClock(T0))


def test_keys_round_trip_through_pem(bank_b: SigningKey) -> None:
    again = SigningKey.from_pem(bank_b.kid, bank_b.owner, bank_b.private_pem())
    assert again.public_pem() == bank_b.public_pem()


def test_sim_clock_runs_fast_and_only_forward() -> None:
    clock = SimClock(T0, speed=1000)
    assert clock.now() >= T0
    jumped = clock.advance(timedelta(days=30))
    assert jumped >= T0 + timedelta(days=30)
    clock.set_speed(1)
    assert clock.now() >= jumped
    with pytest.raises(ValueError, match="forward"):
        clock.advance(timedelta(0))
    with pytest.raises(ValueError, match="timezone"):
        SimClock(datetime(2026, 1, 1))  # noqa: DTZ001 - checking that naive times are refused


def payment(rail: Rail, ref: str, amount: int = rupees(250_000)) -> Payment:
    return Payment(rail=rail, reference=ref, amount=amount, at=T0)


def test_payment_references_match_their_rail() -> None:
    payment(Rail.UPI, "123456789012")
    payment(Rail.RTGS, "SBINR12345678901234567")
    with pytest.raises(ValidationError, match="not a valid UPI reference"):
        payment(Rail.UPI, "SBINN12345678901")


def test_notice_and_response_rules() -> None:
    mule = AccountRef(ifsc="HDFC0001234", account_number="50100123456789")
    notice = Notice(
        notice_id="n-0000001",
        ack_number="31234567890123",
        layer=1,
        credit=payment(Rail.RTGS, "SBINR12345678901234567", rupees(800_000)),
        beneficiary=mule,
        traced_amount=rupees(800_000),
        issued_at=T0,
    )
    assert notice.layer == 1
    with pytest.raises(ValidationError, match="cannot exceed"):
        notice.model_copy(update={"traced_amount": rupees(900_000)}).model_validate(
            notice.model_dump() | {"traced_amount": rupees(900_000)}
        )

    hop = OnwardHop(
        payment=payment(Rail.IMPS, "123456789012", rupees(300_000)),
        to=AccountRef(vpa="m2@okicici"),
        traced_amount=rupees(300_000),
    )
    cash = Exit(
        mode=ExitMode.ATM,
        reference="ATM-1",
        at=T0,
        amount=rupees(200_000),
        traced_amount=rupees(200_000),
        identifier="S1AW001234",
        location="Hyderabad",
    )
    ok = NoticeResponse(
        notice_id="n-0000001",
        status="matched",
        traced_in=rupees(600_000),
        account_type=AccountType.REGULAR,
        held_amount=rupees(100_000),
        lien_id="L1",
        onward=(hop,),
        exits=(cash,),
        responded_at=T0,
    )
    assert ok.held_amount == rupees(100_000)

    with pytest.raises(ValidationError, match="must equal the traced amount"):
        NoticeResponse.model_validate(ok.model_dump() | {"traced_in": rupees(700_000)})
    with pytest.raises(ValidationError, match="lien ID"):
        NoticeResponse.model_validate(ok.model_dump() | {"lien_id": None})
    with pytest.raises(ValidationError, match="must say why"):
        NoticeResponse(notice_id="n", status="not_found", responded_at=T0)
    with pytest.raises(ValidationError, match="Extra inputs"):
        NoticeResponse.model_validate(ok.model_dump() | {"note": "hi"})


def test_account_refs_need_a_real_identifier() -> None:
    with pytest.raises(ValidationError, match="needs its IFSC"):
        AccountRef(account_number="50100123456789")
    with pytest.raises(ValidationError, match="not an IFSC"):
        AccountRef(ifsc="BAD", account_number="50100123456789")
    with pytest.raises(ValidationError, match="UPI ID"):
        AccountRef()

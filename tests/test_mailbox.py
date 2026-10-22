import json
import random

import pytest

from liverecall.mailbox import Mailbox


def wire(segment, revision, final):
    return json.dumps(
        {
            "type": "CAPTION_UPDATE",
            "segment": segment,
            "revision": revision,
            "final": final,
            "text": f"s{segment}r{revision}",
        },
        separators=(",", ":"),
    )


def drain(mb):
    out = []
    while (msg := mb.pop()) is not None:
        out.append(json.loads(msg))
    return out


def test_fast_client_receives_every_revision_in_order():
    mb = Mailbox()
    sent = []
    for seg in (1, 2):
        for rev, final in ((1, False), (2, False), (3, True)):
            mb.push(seg, final, wire(seg, rev, final))
            sent.extend(drain(mb))  # client keeps up: drains after each push
    assert [(m["segment"], m["revision"]) for m in sent] == [
        (1, 1),
        (1, 2),
        (1, 3),
        (2, 1),
        (2, 2),
        (2, 3),
    ]
    assert mb.coalesced == 0


def test_pending_provisional_is_overwritten_by_newer_revision():
    mb = Mailbox()
    mb.push(7, False, wire(7, 1, False))
    mb.push(7, False, wire(7, 2, False))
    assert [(m["segment"], m["revision"]) for m in drain(mb)] == [(7, 2)]
    assert mb.coalesced == 1


def test_final_supersedes_pending_provisional_and_blocks_later_ones():
    mb = Mailbox()
    mb.push(3, False, wire(3, 1, False))
    mb.push(3, True, wire(3, 2, True))
    mb.push(3, False, wire(3, 1, False))  # obsolete after the final
    assert [(m["revision"], m["final"]) for m in drain(mb)] == [(2, True)]
    mb.push(3, False, wire(3, 1, False))  # still obsolete after the final was sent
    assert drain(mb) == []


def test_finals_are_sent_before_provisionals_of_later_segments():
    mb = Mailbox()
    mb.push(1, True, wire(1, 3, True))
    mb.push(2, False, wire(2, 1, False))
    mb.push(2, True, wire(2, 3, True))
    mb.push(3, False, wire(3, 1, False))
    got = [(m["segment"], m["final"]) for m in drain(mb)]
    assert got == [(1, True), (2, True), (3, False)]


def test_pop_finals_takes_all_pending_finals_in_order():
    mb = Mailbox()
    for seg in (1, 2, 3):
        mb.push(seg, True, wire(seg, 1, True))
    mb.push(4, False, wire(4, 1, False))
    assert [json.loads(w)["segment"] for w in mb.pop_finals()] == [1, 2, 3]
    assert mb.pop_finals() == [] and mb.has_provisional


def test_overflow_discards_and_rejects_until_resynchronised():
    mb = Mailbox(finals_cap=3)
    for seg in range(1, 4):
        assert mb.push(seg, True, wire(seg, 1, True))
    assert not mb.push(4, True, wire(4, 1, True))
    assert mb.overflowed and len(mb) == 0
    assert not mb.push(5, False, wire(5, 1, False))


def test_finalized_memory_is_bounded():
    mb = Mailbox(finals_cap=4)
    for seg in range(1, 100):
        mb.push(seg, True, wire(seg, 1, True))
        mb.pop()
    assert len(mb._finalized) == 4


def test_invalid_cap():
    with pytest.raises(ValueError):
        Mailbox(finals_cap=0)


@pytest.mark.parametrize("seed", range(200))
def test_random_interleavings_preserve_invariants(seed):
    """Any push/pop interleaving: all finals once and in order, no stale or
    duplicate revision, and the newest provisional is never lost."""
    rng = random.Random(seed)
    mb = Mailbox(finals_cap=10_000)
    segments = rng.randint(1, 15)
    received = []

    def maybe_drain():
        for _ in range(rng.randint(0, 3)):
            msg = mb.pop()
            if msg is None:
                break
            received.append(json.loads(msg))

    for seg in range(1, segments + 1):
        revisions = rng.randint(1, 6)
        for rev in range(1, revisions + 1):
            mb.push(seg, rev == revisions, wire(seg, rev, rev == revisions))
            maybe_drain()
    received.extend(drain(mb))

    finals = [m["segment"] for m in received if m["final"]]
    assert finals == list(range(1, segments + 1))
    highest = {}
    for m in received:
        seg, rev = m["segment"], m["revision"]
        assert rev > highest.get(seg, 0), "stale or duplicate revision"
        highest[seg] = rev
        if m["final"]:
            highest[seg] = float("inf")  # nothing may follow a final

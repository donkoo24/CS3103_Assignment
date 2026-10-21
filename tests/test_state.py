import random

from liverecall.protocol import Caption
from liverecall.state import CaptionState

def test_state_rules():
    state = CaptionState()
    
    c1 = Caption(1, 1, 100.0, False, "TCP", "wire")
    c2 = Caption(1, 2, 101.0, True, "TCP is reliable", "wire")
    c3 = Caption(1, 3, 102.0, False, "TCP is reliable.", "wire")
    c_stale = Caption(1, 1, 100.0, False, "TCP", "wire")

    # 1. New segment accepted
    assert state.apply(c1) is True
    
    # 2. Duplicate/older revision rejected
    assert state.apply(c_stale) is False
    
    # 3. Newer revision accepted, locks in final=True
    assert state.apply(c2) is True
    
    # 4. Finalized caption is durable; newer revision rejected
    assert state.apply(c3) is False

def test_state_randomised_order():
    # A sequence of revisions for the same segment
    updates = [
        Caption(5, 1, 100.0, False, "Packet", "wire1"),
        Caption(5, 2, 101.0, False, "Packet loss", "wire2"),
        Caption(5, 3, 102.0, False, "Packet loss may", "wire3"),
        Caption(5, 4, 103.0, True, "Packet loss may increase delay.", "wire4")
    ]
    
    # Run the test multiple times with different shuffled orders
    for _ in range(10):
        state = CaptionState()
        shuffled = list(updates)
        random.shuffle(shuffled)
        
        for update in shuffled:
            state.apply(update)
            
        # The final state must ALWAYS lock in as revision 4, final=True
        # regardless of the order they arrived.
        assert state.latest[5] == (4, True)
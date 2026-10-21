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
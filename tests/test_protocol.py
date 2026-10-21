from liverecall.protocol import parse, caption_from

def test_parse_bad_input():
    # Must never crash on bad input
    assert parse("{malformed") is None
    assert parse(b"Not JSON at all") is None

def test_caption_from_valid():
    msg = {
        "type": "CAPTION_UPDATE", "segment": 1, "revision": 2, 
        "source_ts": 100.0, "final": False, "text": "TCP"
    }
    cap = caption_from(msg)
    assert cap.segment == 1
    assert cap.revision == 2
    # Verify the encode-once compact format
    assert " " not in cap.wire

def test_caption_from_extra_fields():
    msg = {
        "type": "CAPTION_UPDATE", 
        "segment": 1, 
        "revision": 2, 
        "source_ts": 100.0, 
        "final": False, 
        "text": "TCP",
        "extra_junk": "ignore me", 
        "test_phase": "beta"
    }
    cap = caption_from(msg)
    
    assert cap is not None
    assert cap.segment == 1
    # Verify the extra fields are stripped out of the final encoded string
    assert "extra_junk" not in cap.wire
    assert "test_phase" not in cap.wire
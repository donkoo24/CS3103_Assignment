from .protocol import Caption

class CaptionState:
    def __init__(self):
        # Maps segment -> (revision, final_status)
        self.latest: dict[int, tuple[int, bool]] = {}

    def apply(self, c: Caption) -> bool:
        """
        Evaluates a caption. Returns True if accepted, False if stale/duplicate.
        """
        if c.segment not in self.latest:
            self.latest[c.segment] = (c.revision, c.final)
            return True
            
        stored_rev, stored_final = self.latest[c.segment]
        
        # A finalized segment is durable state; older/newer revisions cannot overwrite it.
        if stored_final:
            return False
            
        # Accept if it's a strictly newer revision
        # Assignment alr guarantees that there they will not intentionally send a newer revision after a final caption for that segment so dont have to worry about this edge case
        if c.revision > stored_rev:
            self.latest[c.segment] = (c.revision, c.final)
            return True
            
        return False

    def prune(self, min_segment: int):
        """Removes segments that fall completely out of the history window."""
        stale_segments = [seg for seg in self.latest if seg < min_segment]
        for seg in stale_segments:
            del self.latest[seg]

    def reset(self):
        """qol: Clears the state when a new SOURCE_HELLO is received so that we don't have to clear the caption log on each new run of caption_from"""
        self.latest.clear()
class Session:
    def __init__(self, ws):
        self.ws = ws

class Hub:
    def register(self, ws, client_id: int, first_messages: list[str]) -> Session:
        """Stub: Will register the client and send first_messages."""
        return Session(ws)
        
    def unregister(self, session: Session) -> None:
        """Stub: Will cleanly remove the client."""
        pass
        
    def publish(self, caption) -> None:
        """Stub: Will synchronously push the caption to all client mailboxes."""
        pass
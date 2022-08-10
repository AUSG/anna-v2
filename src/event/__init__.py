class EmojiAddedEvent:
    """
    data class
    """
    def __init__(self, reaction: str, ts: str, channel: str, slack_unique_id: str):
        self.reaction = reaction
        self.ts = ts
        self.channel = channel
        self.slack_unique_id = slack_unique_id

class MessageSentEvent:
    """
    data class
    """
    def __init__(self, message: str, ts: str):
        self.message = message
        self.ts = ts

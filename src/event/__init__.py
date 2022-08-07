class EmojiAddedEvent:
    """
    data class
    """

    def __init__(self, reaction: str, ts: str, channel: str, slack_unique_id: str):
        self.reaction = reaction
        self.ts = ts
        self.channel = channel
        self.slack_unique_id = slack_unique_id

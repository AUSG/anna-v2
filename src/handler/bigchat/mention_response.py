class MentionResponse:
    def __init__(self, mention_handlers, fallback_handler):
        self.mention_handlers = mention_handlers
        self.fallback_handler = fallback_handler

    def run(self):
        for handler in self.mention_handlers:
            if handler.can_handle():
                return handler.handle_mention()
        return self.fallback_handler.handle_mention()

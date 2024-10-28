from abc import ABC


class MentionHandler(ABC):
    def handle_mention(self):
        pass

    def can_handle(self):
        pass

from abc import ABC, abstractmethod


class MentionHandler(ABC):
    @abstractmethod
    def handle_mention(self):
        pass

    @abstractmethod
    def can_handle(self):
        pass

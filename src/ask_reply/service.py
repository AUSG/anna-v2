from slack_bolt import Say

from event import MessageSentEvent


class ArService:
    def __init__(self, say: Say, event: MessageSentEvent):
        self.say = say
        self.event = event
        self.dictionary = {}
        self._init_dictionary()

    def _is_target(self):
        return "!" in self.event.message

    def reply(self):
        if not self._is_target():
            return

        reply = self._find_reply_message()

        if reply is None:
            return
        else:
            self.say(text=reply, thread_ts=self.event.ts)

    # TODO [seonghyeok] DB 화 (CRUD, alias 추가/제거 가능하게)
    def _init_dictionary(self):
        self.dictionary["wifi"] = "센터필드의 와이파이를 알려줄게. 이름은 'Guest', 비밀번호는 'BrokenWires@@2019'야!"
        pass

    def _find_keyword(self):
        for token in self.event.message:
            if token.startswith("!") and len(token) > 2:
                return token[1:]

    def _find_reply_message(self):
        keyword = self._find_keyword()
        return self.dictionary.get(keyword, None)

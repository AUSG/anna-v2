class MockSlackClient:
    def __init__(self):
        self.is_tell_called = False

    def tell(self, text, thread_ts):
        print(f"reply is called: text={text}, thread_ts={thread_ts}")
        self.is_tell_called = True


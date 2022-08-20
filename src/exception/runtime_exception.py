class RuntimeException(Exception):
    def __init__(self, message: str, thread_ts: str = None):
        super()
        self.message = message
        self.thread_ts = thread_ts

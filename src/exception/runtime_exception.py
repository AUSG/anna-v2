class RuntimeException(Exception):
    def __init__(self, message: str, target_ts: str = None):
        super()
        self.message = message
        self.target_ts = target_ts

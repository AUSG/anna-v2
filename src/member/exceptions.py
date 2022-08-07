class MemberInfoNotPerfectException(Exception):
    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def __str__(self):
        return f"[{self.__class__.__name__}] {self.message}"

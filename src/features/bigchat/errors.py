"""Expected Bigchat storage failures, independent of the Sheets SDK."""


class BigchatError(RuntimeError):
    pass


class BigchatNameConflict(BigchatError):
    pass


class BigchatAlreadyCreated(BigchatError):
    pass


class BigchatSheetMissing(BigchatError):
    pass


class BigchatIntegrityError(BigchatError):
    pass


class BigchatStorageError(BigchatError):
    pass

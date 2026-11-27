class Stop(Exception):
    """A stop: the run ends with exit 2, saying why, and naming the table when there is one."""

    def __init__(self, reason: str, table: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.table = table


def printable(text: str) -> str:
    """Text from the copy or the migrations, with control characters shown as escapes, not acted on."""
    return "".join(
        c if c in "\n\t" or (c.isprintable() and c not in "\x1b\x9b") else repr(c)[1:-1]
        for c in text
    )

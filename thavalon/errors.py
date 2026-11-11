"""Errors the engine raises when a request can't be carried out."""


class RuleError(Exception):
    """The requested change is not allowed by the rules right now."""


class NotAllowed(RuleError):
    """This player may not do that right now."""

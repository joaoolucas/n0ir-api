"""Exception classes for SDK pools module."""


class PoolNotFoundError(Exception):
    """Raised when a pool cannot be found."""
    pass


class RPCError(Exception):
    """Raised when there's an RPC connection error."""
    pass
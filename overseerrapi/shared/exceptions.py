"""
Overseerr-related exceptions
"""

class UnauthorizedException(Exception):
    """
    Raised when the provided user fails to authenticate.
    """
    pass
class ForbiddenException(Exception):
    """
    Raised when the provided user does not have permission to perform an action.
    """
    pass
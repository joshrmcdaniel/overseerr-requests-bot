"""
Overseerr-related exceptions
"""

class UnauthorizedException(Exception):
    """
    Raised when the provided user fails to authenticate.
    """
    pass
class ForbiddenException(Exception)

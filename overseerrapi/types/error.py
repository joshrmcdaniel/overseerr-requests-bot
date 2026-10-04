import jsonobject


class OverseerrError(jsonobject.JsonObject):
    path = jsonobject.StringProperty(name="path")
    message = jsonobject.StringProperty(name="message")


class ErrorResponse(jsonobject.JsonObject):
    message = jsonobject.StringProperty(name="message")
    errors = jsonobject.ListProperty(lambda: OverseerrError, name="errors")


class RequestAssignmentError(ErrorResponse):
    """Creation succeeded, so retrying must not create another request."""

    request_id = jsonobject.IntegerProperty(name="requestId")

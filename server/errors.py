"""
The single error shape the API speaks.

Every failure leaves as:

    {"error": {"code": "validation_failed",
               "message": "Check the highlighted fields.",
               "fields": {"amount": "Must be greater than 0."}}}

The `fields` map is the part that matters. The old UI could only report a
problem as a banner at the top of the page, which leaves the reader to work
out which input it meant. Keyed by field name, the client can put the message
against the control that caused it.
"""


class ApiError(Exception):
    """A failure that should reach the client as a structured JSON error.

    Raised anywhere in a request and turned into a response by the handler
    registered in server.app, so a route never has to build an error body.
    """

    status = 400
    code = "bad_request"

    def __init__(self, message, *, code=None, status=None, fields=None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status
        self.fields = fields or {}

    def to_dict(self):
        """Return the JSON body for this error."""
        body = {"code": self.code, "message": self.message}
        if self.fields:
            body["fields"] = self.fields
        return {"error": body}


class ValidationError(ApiError):
    """One or more submitted fields are unusable."""

    status = 422
    code = "validation_failed"

    def __init__(self, fields, message="Check the highlighted fields."):
        super().__init__(message, fields=fields)


class NotSignedIn(ApiError):
    status = 401
    code = "not_signed_in"

    def __init__(self, message="Sign in to continue."):
        super().__init__(message)


class NotFound(ApiError):
    """The record does not exist, or does not belong to this user.

    Deliberately the same answer in both cases. Distinguishing them would
    confirm that some other account owns a given id, which is a small leak
    but a free one to avoid.
    """

    status = 404
    code = "not_found"

    def __init__(self, message="Not found."):
        super().__init__(message)


class Conflict(ApiError):
    """The request is well formed but clashes with what is already stored."""

    status = 409
    code = "conflict"

    def __init__(self, message, *, code=None, fields=None):
        super().__init__(message, code=code or "conflict", fields=fields)


class DemoReadOnly(ApiError):
    """The demo account may not perform this action."""

    status = 403
    code = "demo_readonly"

    def __init__(self, message="Not available in the demo. Create an account to use this."):
        super().__init__(message)


class DatabaseUnavailable(ApiError):
    """The query could not run at all.

    Separate from a 500 so the client can say "try again" rather than
    "something is broken", which is usually the truth: the pooled connection
    limit was reached, or the database was briefly unreachable.
    """

    status = 503
    code = "database_unavailable"

    def __init__(self, message="The database is unavailable. Try again in a moment."):
        super().__init__(message)

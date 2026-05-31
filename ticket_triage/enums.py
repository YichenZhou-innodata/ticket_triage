"""enums.py

StrEnum definitions for every predefined list in
`access_issue_state_machine.md`: triage states, events, recommended action
types, entity fields, primary categories, and approval statuses.

Values are exact, lower_snake_case strings taken from the spec. Member names
are upper-cased per Python convention; the string value is what's used on
the wire and in JSON rule book files.
"""

from enum import StrEnum


class State(StrEnum):
    """Triage states for an access-request ticket.

    Source: access_issue_state_machine.md, "Predefined Enums for Access
    Tickets > States" table.
    """

    NEW = "new"
    INTAKE = "intake"
    MISSING_INFO = "missing_info"
    DUPLICATE_REVIEW = "duplicate_review"
    READY_FOR_ACCESS_REVIEW = "ready_for_access_review"
    APPROVER_REVIEW = "approver_review"
    ACCESS_PROVISIONING = "access_provisioning"
    VERIFICATION = "verification"
    RESOLVED = "resolved"
    CLOSED = "closed"
    DENIED = "denied"
    STALE_WAITING_FOR_USER = "stale_waiting_for_user"
    HUMAN_REVIEW = "human_review"


class Event(StrEnum):
    """Events that may drive a state transition.

    Source: access_issue_state_machine.md, "Predefined Enums for Access
    Tickets > Events" block.
    """

    TICKET_CREATED = "ticket_created"
    REQUIRED_FIELDS_EXTRACTED = "required_fields_extracted"
    MISSING_REQUIRED_FIELDS_DETECTED = "missing_required_fields_detected"
    REPORTER_PROVIDED_MISSING_INFO = "reporter_provided_missing_info"
    DUPLICATE_CANDIDATE_FOUND = "duplicate_candidate_found"
    DUPLICATE_CONFIRMED = "duplicate_confirmed"
    DUPLICATE_REJECTED = "duplicate_rejected"
    APPROVER_IDENTIFIED = "approver_identified"
    APPROVER_MISSING = "approver_missing"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    ACCESS_PROVISIONED = "access_provisioned"
    ACCESS_FAILED = "access_failed"
    USER_CONFIRMED_ACCESS = "user_confirmed_access"
    USER_REPORTS_ACCESS_NOT_WORKING = "user_reports_access_not_working"
    NO_USER_RESPONSE = "no_user_response"
    HUMAN_OVERRIDE = "human_override"
    TICKET_REOPENED = "ticket_reopened"


class RecommendedActionType(StrEnum):
    """Action types the agent may recommend to a human reviewer.

    Source: access_issue_state_machine.md, "Predefined Enums for Access
    Tickets > Recommended Action Types" block.

    Note: the ABP-1007 example in the spec (line 176) uses ``ask_for_info``,
    which is NOT in the canonical list. This enum uses the canonical
    ``ask_for_missing_info``; the spec inconsistency is flagged in the PR
    description for Yichen.
    """

    EXTRACT_FIELDS = "extract_fields"
    ASK_FOR_MISSING_INFO = "ask_for_missing_info"
    SUGGEST_DUPLICATE_REVIEW = "suggest_duplicate_review"
    REQUEST_APPROVAL = "request_approval"
    RECOMMEND_ROUTE_TO_ACCESS_ADMIN = "recommend_route_to_access_admin"
    ASK_USER_TO_VERIFY = "ask_user_to_verify"
    DRAFT_RESOLUTION_COMMENT = "draft_resolution_comment"
    DRAFT_DENIAL_COMMENT = "draft_denial_comment"
    SEND_FOLLOW_UP_REMINDER = "send_follow_up_reminder"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    RECOMMEND_CLOSE_TICKET = "recommend_close_ticket"


class EntityField(StrEnum):
    """Named entity fields the agent extracts from a ticket.

    Source: access_issue_state_machine.md, "Predefined Enums for Access
    Tickets > Entity Schema" block.
    """

    NAME = "name"
    EMPLOYEE_ID = "employee_id"
    PORTFOLIO = "portfolio"
    REGION = "region"
    USER_ROLE = "user_role"
    PROJECT_TYPE = "project_type"
    LEADS = "leads"
    ADDITIONAL_CONTEXT = "additional_context"


class PrimaryCategory(StrEnum):
    """Top-level ticket categories.

    Only ``access_request`` is defined by the current spec. Additional
    categories (e.g. ``application_issue``) appear in the project readme but
    are out of scope for this PR and will be added when their rule books are
    written.
    """

    ACCESS_REQUEST = "access_request"


class ApprovalStatus(StrEnum):
    """Status of an approval workflow for a ticket.

    Inferred from the event names ``approval_requested``, ``approval_granted``,
    and ``approval_denied`` in the spec. The spec does not enumerate this
    list explicitly; ``not_requested`` is the only status that appears
    literally (in the ABP-1007 example). Flag for Yichen review.
    """

    NOT_REQUESTED = "not_requested"
    REQUESTED = "requested"
    GRANTED = "granted"
    DENIED = "denied"

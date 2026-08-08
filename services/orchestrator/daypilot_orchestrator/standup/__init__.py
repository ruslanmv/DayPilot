"""Daily Standup Copilot.

Watches the workday, drafts the standup update before the user leaves, takes
one review, and replies inside the right Slack thread. The rule the whole
module is built around: **never claim work that was not observed, and never
post text a human did not approve.**
"""
from .policy import ApprovalRequired, DraftLocked, StandupError, ThreadNotFound

__all__ = ["ApprovalRequired", "DraftLocked", "StandupError", "ThreadNotFound"]

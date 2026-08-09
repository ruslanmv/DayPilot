"""Slack as a communication workspace, not just another notification source.

The promise is *stay on top of Slack without living in Slack*, and the whole
package is arranged around one sentence:

    **AI always drafts. The user always decides what gets sent.**

Layering, in the order a message travels:

``transport``
    How an inbound event arrives (Socket Mode or a signed HTTP endpoint) and how
    it is proven authentic before anything else looks at it.
``classify``
    What kind of message this is, and — more importantly — whether it deserves a
    draft at all. Model-free and deliberately quiet.
``context``
    What a draft may *read* (the workspace's allow-list) and, separately, what
    this recipient may *hear*. The second filter runs before generation.
``compose``
    Facts to a message someone would actually send, in the register the
    destination deserves.
``settings``
    The stored intent behind all of the above, served to the UI rather than
    duplicated in it.
``service``
    The pipeline that ties them together — and which cannot send. Delivery goes
    through :func:`daypilot_orchestrator.integrations.slack.request_send`, i.e.
    the Integration Gateway's write path, i.e. an approval.

This package deliberately adds nothing to the existing Slack *integration*: the
provider adapter, credential handling, audit trail, injection guard and approval
semantics are the ones already in ``integrations/``. What is new is the surface
on top of them.
"""
from __future__ import annotations

from . import classify, compose, context, service, settings, transport

__all__ = ["classify", "compose", "context", "service", "settings", "transport"]

"""The Slack workspace's UI contract.

These read the shipped TypeScript rather than running a browser, in the same
spirit as the rest of DayPilot's UI contracts: the claims worth pinning are
structural, and a structural claim that only a screenshot can check is a claim
that quietly stops being true.

What is pinned here is exactly what the feature promises:

* it is optional, on both sides,
* the browser cannot reach Slack,
* the assistant proposes rather than replaces,
* and "never automatically send" is a statement, not a toggle.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
UI = REPO / "packages" / "ui-bridge" / "src"
SLACK = UI / "slack"


def read(*parts: str) -> str:
    return (SLACK.joinpath(*parts)).read_text(encoding="utf-8")


def code(source: str) -> str:
    """The source with comments removed.

    These files explain themselves at length, and several comments name the very
    thing the test is asserting is absent ("there is no ``chat.postMessage``
    here"). Scanning prose for forbidden identifiers finds the promise instead of
    a violation of it.
    """
    without_block = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"//[^\n]*", "", without_block)


# --- optional on both sides ---------------------------------------------------


def test_the_tab_needs_both_flags() -> None:
    env = (UI / "env.ts").read_text(encoding="utf-8")
    assert "VITE_DAYPILOT_SLACK_WORKSPACE_ENABLED" in env
    main = (REPO / "apps" / "operator-web" / "src" / "main.tsx").read_text(encoding="utf-8")
    assert "slackEnabled={slackEnabled}" in main
    example = (REPO / ".env.example").read_text(encoding="utf-8")
    assert "DAYPILOT_SLACK_WORKSPACE_ENABLED=false" in example
    assert "VITE_DAYPILOT_SLACK_WORKSPACE_ENABLED=false" in example


def test_slack_is_a_route_and_a_nav_item() -> None:
    route = (UI / "shell" / "route.ts").read_text(encoding="utf-8")
    assert "'slack'" in route
    portal = (UI / "minimalPortal.tsx").read_text(encoding="utf-8")
    assert "SLACK_NAV" in portal
    assert "<SlackWorkspace" in portal


def test_slack_sits_before_documents_even_when_email_is_off() -> None:
    """The nav order is Home … Email, Slack, Documents, Agents.

    Slack keeps its slot whether or not Email is enabled — a tab that slides
    around depending on someone else's feature flag is a tab people stop being
    able to find.
    """
    portal = (UI / "minimalPortal.tsx").read_text(encoding="utf-8")
    block = portal.split("function navViews", 1)[1].split("\n}", 1)[0]
    assert "docsIndex" in block
    # Email first, then Slack, then everything from Documents onward.
    assert block.index("EMAIL_NAV") < block.index("SLACK_NAV")


def test_settings_has_its_own_slack_section() -> None:
    panel = (UI / "shell" / "SettingsPanel.tsx").read_text(encoding="utf-8")
    order = code(panel).split("SECTION_ORDER: SettingsSectionId[] = [", 1)[1].split("]", 1)[0]
    ids = [chunk.strip().strip("',") for chunk in order.split(",") if "'" in chunk]
    assert ids == [
        "profile", "integrations", "calendar", "mail", "slack", "providers",
        "sources", "homepilot", "appearance", "permissions", "shortcuts",
    ]
    assert "<SlackPanel />" in panel


# --- the browser cannot reach Slack -------------------------------------------


def test_the_client_never_talks_to_slack_directly() -> None:
    """Every Slack call goes through DayPilot's gateway, which is approval-gated.

    A second HTTP client in the browser would be a second policy, and the one in
    the browser is the one an attacker can reach.
    """
    for name in ("slackClient.ts", "SlackWorkspace.tsx", "SlackDraftEditor.tsx",
                 "SlackAssistantPanel.tsx", "SlackCompose.tsx"):
        source = code(read(name))
        assert "slack.com/api" not in source, name
        assert "chat.postMessage" not in source, name
        assert "xoxb-" not in source, name


def test_send_goes_to_the_gateway_and_reports_an_approval() -> None:
    client = read("slackClient.ts")
    assert "/v1/slack/drafts/${encodeURIComponent(draftId)}/send" in client
    workspace = read("SlackWorkspace.tsx")
    assert "approval_required" in workspace
    assert "Nothing has been posted to Slack." in workspace


def test_the_assistant_panel_has_no_send_affordance() -> None:
    """The only way out is the draft's own Send button."""
    panel = code(read("SlackAssistantPanel.tsx"))
    assert "slackApi.send" not in panel
    assert "Send in Slack" not in panel


# --- propose, don't replace ----------------------------------------------------


def test_refinement_offers_three_choices_and_applies_none_of_them_itself() -> None:
    panel = read("SlackAssistantPanel.tsx")
    for label in ("Use this", "Insert", "Try again"):
        assert label in panel, label
    client = read("slackClient.ts")
    # /refine and /accept are separate calls. If they were one, "Try again"
    # would have already overwritten what the user was comparing against.
    assert "/refine" in client and "/accept" in client


def test_use_this_is_undoable() -> None:
    editor = read("SlackDraftEditor.tsx")
    assert "canUndo" in editor and "Undo" in editor
    client = read("slackClient.ts")
    assert "/undo" in client


def test_the_composer_offers_the_four_transforms() -> None:
    types = read("slackTypes.ts")
    for label in ("Shorter", "More direct", "More detailed", "Friendly"):
        assert label in types, label


def test_the_inbox_offers_the_five_filters() -> None:
    types = read("slackTypes.ts")
    filters = types.split("INBOX_FILTERS", 1)[1].split("]", 1)[0]
    for label in ("All", "Needs reply", "Action", "FYI", "Done"):
        assert f"'{label}'" in filters, label


# --- the policy is stated, not offered ------------------------------------------


def test_never_automatically_send_is_locked_copy_not_a_toggle() -> None:
    panel = (UI / "settings" / "SlackPanel.tsx").read_text(encoding="utf-8")
    assert "Never automatically send a Slack message" in panel
    locked = panel.split("Never automatically send a Slack message", 1)[0][-400:]
    assert "dp-cset__row--locked" in locked
    # No switch anywhere near it, and no setting it could be bound to.
    assert "autoSend" not in panel
    assert "neverAutomaticallySend: " not in panel


def test_the_draft_says_it_has_not_been_sent() -> None:
    editor = read("SlackDraftEditor.tsx")
    assert "AI draft — not sent. You remain in control." in editor


def test_a_draft_always_shows_what_it_was_built_from() -> None:
    editor = read("SlackDraftEditor.tsx")
    assert "Based on {draft.sources.length} source" in editor
    # Withheld facts are surfaced as a count, never as their text.
    assert "withheldCount" in editor


def test_the_settings_panel_names_the_five_sections() -> None:
    panel = (UI / "settings" / "SlackPanel.tsx").read_text(encoding="utf-8")
    for heading in ("1. Slack connection", "2. AI drafting",
                    "3. Context available to Slack AI",
                    "4. Privacy &amp; recipient protection", "5. Notifications"):
        assert heading in panel, heading


def test_the_context_catalogue_comes_from_the_api() -> None:
    """The source list is a permission. A client-side copy is a lie waiting."""
    panel = (UI / "settings" / "SlackPanel.tsx").read_text(encoding="utf-8")
    assert "payload.sources.map" in panel
    assert "CONTEXT_SOURCES" not in panel


# --- demo mode is opt-in and never a production fallback -------------------------


def test_demo_data_is_reachable_only_through_the_demo_flag() -> None:
    workspace = read("SlackWorkspace.tsx")
    assert "isDemoMode()" in workspace
    connected = workspace.split("function ConnectedSlackWorkspace", 1)[1].split(
        "// --- demo", 1)[0]
    connected = code(connected)
    for symbol in ("DEMO_ITEMS", "DEMO_COUNTS", "demoThread", "DEMO_IMPROVED"):
        assert symbol not in connected, symbol


def test_a_connected_but_empty_workspace_says_so() -> None:
    inbox = read("SlackInbox.tsx")
    assert "Nothing waiting." in inbox

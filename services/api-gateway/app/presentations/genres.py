"""Starting storylines per deck genre. Deterministic and offline: they give structure and prompts,
never invented facts. Every number slot starts empty ("—") and is labelled for the presenter."""

from __future__ import annotations

from typing import Any

GENRES = {
    "weekly_update": "Weekly update",
    "executive_update": "Executive update",
    "project_kickoff": "Project kickoff",
    "quarterly_review": "Quarterly business review",
    "product_launch": "Product launch",
    "incident_review": "Incident review",
    "proposal": "Client proposal",
    "training": "Training session",
}


def _s(**kw: Any) -> dict[str, Any]:
    return kw


def storyline(genre: str, topic: str, period_label: str = "", audience: str = "") -> dict[str, Any]:
    if genre not in GENRES:
        raise ValueError(f"genre must be one of {', '.join(GENRES)}")
    t = " ".join(topic.split())[:150] or GENRES[genre]
    cover = _s(id="cover", type="cover", title=t, subtitle=GENRES[genre] + (f" for {audience}" if audience else ""), kicker=period_label[:80] or GENRES[genre])
    kpis = lambda title, labels: _s(id="numbers", type="kpis", title=title, kpis=[{"value": "—", "label": x} for x in labels], footnote="Enter figures from the reporting period; leave “—” where data is unavailable.")  # noqa: E731
    slides: list[dict[str, Any]]
    if genre == "weekly_update":
        slides = [
            cover,
            kpis("The week in numbers", ["Delivered", "In progress", "Blocked"]),
            _s(id="highlights", type="bullets", title="Highlights", bullets=["What shipped", "What we learned", "Who helped"], takeaway="One sentence the audience should remember."),
            _s(id="trend", type="chart", title="Progress over the last five weeks", chart={"type": "column", "title": "Items delivered per week", "unit": "items", "categories": ["W-4", "W-3", "W-2", "W-1", "This week"], "series": [{"name": "Delivered", "values": [None] * 5}]}),
            _s(id="risks", type="table", title="Risks and blockers", headers=["Risk", "Impact", "Owner", "Next step"], rows=[["Risk", "—", "—", "—"]]),
            _s(id="decision", type="decision", title="Decision needed", recommendation="State the recommendation in one sentence.", options=["Option A", "Option B"], ask="What you need, from whom, by when."),
            _s(id="next", type="closing", title="Next week", subtitle="Owners and dates", next_steps=["First priority", "Second priority", "Third priority"]),
        ]
    elif genre == "executive_update":
        slides = [
            cover,
            _s(id="answer", type="statement", title="The answer first", statement="Lead with the conclusion the executives need.", support="Two lines of context: why it matters now."),
            kpis("Where we stand", ["Revenue", "Customers", "Delivery"]),
            _s(id="drivers", type="bullets", title="What is driving it", bullets=["Driver one", "Driver two", "Driver three"]),
            _s(id="options", type="comparison", title="Options", left={"heading": "Option A", "points": ["Benefit", "Cost", "Risk"]}, right={"heading": "Option B", "points": ["Benefit", "Cost", "Risk"]}),
            _s(id="decision", type="decision", title="Decision requested", recommendation="Recommended option and why.", ask="Approval needed by a date."),
        ]
    elif genre == "project_kickoff":
        slides = [
            cover,
            _s(id="agenda", type="agenda", title="Agenda", items=["Why this project", "Scope", "Plan", "Team", "Risks", "Next steps"]),
            _s(id="why", type="statement", title="Why this project", statement="The problem we solve and for whom.", support="What success looks like."),
            _s(id="scope", type="comparison", title="Scope", left={"heading": "In scope", "points": ["Item", "Item"]}, right={"heading": "Out of scope", "points": ["Item", "Item"]}),
            _s(id="plan", type="timeline", title="Plan", milestones=[{"label": "Discovery", "date": "—"}, {"label": "Build", "date": "—"}, {"label": "Pilot", "date": "—"}, {"label": "Launch", "date": "—"}]),
            _s(id="team", type="table", title="Team and responsibilities", headers=["Role", "Person", "Responsibility"], rows=[["Sponsor", "—", "—"], ["Lead", "—", "—"]]),
            _s(id="risks", type="bullets", title="Risks we know about", bullets=["Risk and mitigation", "Risk and mitigation"]),
            _s(id="next", type="closing", title="Next steps", next_steps=["First action", "Second action"]),
        ]
    elif genre == "quarterly_review":
        slides = [
            cover,
            _s(id="agenda", type="agenda", title="Agenda", items=["Results", "Customers", "Delivery", "Next quarter"]),
            kpis("Quarter at a glance", ["Revenue", "New customers", "Retention", "NPS"]),
            _s(id="trend", type="chart", title="Revenue by month", chart={"type": "line", "title": "Revenue", "unit": "", "categories": ["M1", "M2", "M3"], "series": [{"name": "Actual", "values": [None] * 3}, {"name": "Plan", "values": [None] * 3}]}),
            _s(id="wins", type="bullets", title="Wins and lessons", bullets=["Win", "Win", "Lesson"]),
            _s(id="next", type="timeline", title="Next quarter", milestones=[{"label": "Milestone", "date": "—"}, {"label": "Milestone", "date": "—"}, {"label": "Milestone", "date": "—"}]),
            _s(id="close", type="closing", title="Asks", next_steps=["Ask one", "Ask two"]),
        ]
    elif genre == "product_launch":
        slides = [
            cover,
            _s(id="promise", type="statement", title="The promise", statement="One sentence: what it does and for whom.", support="The problem it removes."),
            _s(id="audience", type="bullets", title="Who it is for", bullets=["Primary audience", "Their problem", "How they buy"]),
            _s(id="how", type="diagram", title="How it works", nodes=[{"id": "input", "label": "Input"}, {"id": "process", "label": "Product"}, {"id": "outcome", "label": "Outcome"}], edges=[{"from": "input", "to": "process"}, {"from": "process", "to": "outcome"}]),
            _s(id="plan", type="timeline", title="Launch plan", milestones=[{"label": "Beta", "date": "—"}, {"label": "Announcement", "date": "—"}, {"label": "General availability", "date": "—"}]),
            kpis("How we will measure it", ["Sign-ups", "Activation", "Revenue"]),
            _s(id="close", type="closing", title="Launch checklist", next_steps=["Product ready", "Support ready", "Announcement ready"]),
        ]
    elif genre == "incident_review":
        slides = [
            cover,
            _s(id="summary", type="statement", title="What happened", statement="One-sentence summary of impact and duration.", support="Who was affected and how."),
            _s(id="timeline", type="timeline", title="Timeline", milestones=[{"label": "Detected", "date": "—"}, {"label": "Mitigated", "date": "—"}, {"label": "Resolved", "date": "—"}]),
            _s(id="cause", type="diagram", title="Cause and effect", nodes=[{"id": "trigger", "label": "Trigger"}, {"id": "fault", "label": "Fault"}, {"id": "impact", "label": "Impact"}], edges=[{"from": "trigger", "to": "fault"}, {"from": "fault", "to": "impact"}]),
            _s(id="actions", type="table", title="Actions", headers=["Action", "Owner", "Due"], rows=[["Action", "—", "—"]]),
            _s(id="close", type="closing", title="What changes now", next_steps=["Change one", "Change two"]),
        ]
    elif genre == "proposal":
        slides = [
            cover,
            _s(id="need", type="statement", title="Your goal", statement="Restate the client's goal in their words.", support="Why now."),
            _s(id="approach", type="timeline", title="Our approach", milestones=[{"label": "Discover", "date": "Weeks 1–2"}, {"label": "Design", "date": "Weeks 3–4"}, {"label": "Deliver", "date": "Weeks 5–8"}]),
            _s(id="options", type="comparison", title="Options", left={"heading": "Essential", "points": ["Scope", "Timeline", "Investment"]}, right={"heading": "Complete", "points": ["Scope", "Timeline", "Investment"]}),
            _s(id="why", type="bullets", title="Why us", bullets=["Relevant experience", "Team", "References"]),
            _s(id="decision", type="decision", title="Next step", recommendation="Recommended option.", ask="Agreement to start by a date."),
        ]
    else:  # training
        slides = [
            cover,
            _s(id="agenda", type="agenda", title="What we will cover", items=["Concept", "Example", "Practice", "Questions"]),
            _s(id="concept", type="bullets", title="The concept", bullets=["Definition", "Why it matters", "Common mistake"], takeaway="The one idea to remember."),
            _s(id="steps", type="diagram", title="Step by step", nodes=[{"id": "s1", "label": "Step 1"}, {"id": "s2", "label": "Step 2"}, {"id": "s3", "label": "Step 3"}], edges=[{"from": "s1", "to": "s2"}, {"from": "s2", "to": "s3"}]),
            _s(id="quote", type="quote", title="Remember", quote="A short, memorable line.", attribution="Source"),
            _s(id="close", type="closing", title="Practice", next_steps=["Exercise one", "Exercise two"]),
        ]
    return {"schema_version": "daypilot.storyline/v1", "title": t, "subtitle": GENRES[genre], "audience": audience or "Internal", "purpose": GENRES[genre], "slides": slides}

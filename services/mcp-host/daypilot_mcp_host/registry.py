from dataclasses import dataclass

@dataclass
class McpToolContract:
    name: str
    risk: str = "low"
    write: bool = False
    requires_approval: bool = False


DEFAULT_TOOLS = [
    McpToolContract("daypilot.homepilot.preview_hpersona"),
    McpToolContract("daypilot.homepilot.import_hpersona", risk="medium", write=True, requires_approval=True),
    McpToolContract("daypilot.approvals.request_user_approval", risk="medium", write=True, requires_approval=True),
    # Presentations MCP server (gateway: POST /v1/presentations/mcp). Writes create drafts only.
    *[McpToolContract(f"daypilot.presentations.{n}") for n in ("list_brands", "list_decks", "get_deck", "propose_outline", "export_deck")],
    *[McpToolContract(f"daypilot.presentations.{n}", risk="medium", write=True) for n in ("create_deck", "revise_deck", "regenerate_slides", "prepare_weekly")],
]

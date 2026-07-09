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
]

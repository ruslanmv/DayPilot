from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "mcp-host"))

from daypilot_mcp_host.homepilot_bridge import preview_hpersona_file


def test_sample_homepilot_persona_preview():
    sample = ROOT / "examples" / "homepilot-personas" / "atlas.hpersona"
    if not sample.exists():
        return
    preview = preview_hpersona_file(sample)
    assert preview["kind"] == "homepilot.persona"
    assert preview["safe_install_state"] == "INSTALLED_DISABLED"
    assert preview["policy"]["require_human_approval"] is True

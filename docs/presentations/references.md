# Primary technical references

Checked 2026-10-02. These references inform the design; recommendations, budgets and roadmap estimates are proposed DayPilot choices rather than externally certified results.

| Reference | Design use and limitation |
| --- | --- |
| [PptxGenJS repository](https://github.com/gitbrent/PptxGenJS) | JavaScript OOXML export, native objects, slide masters and MIT license. Pin/test a version. Composition support does not prove universal template import or cross-office pixel fidelity. |
| [PptxGenJS quick start](https://gitbrent.github.io/PptxGenJS/docs/quick-start/) | Direct JavaScript slide creation and PPTX writing. Production code belongs behind a validated renderer adapter. |
| [PptxGenJS charts API](https://gitbrent.github.io/PptxGenJS/docs/api-charts/) | Native series/category chart construction and formatting; verify actual exported charts, labels and data. |
| [Microsoft: accessible PowerPoint presentations](https://support.microsoft.com/en-us/accessibility/powerpoint/make-your-powerpoint-presentations-accessible-to-people-with-disabilities) | Accessibility practices and human/Office checks. Automated structural checks alone are insufficient. |
| [LibreOffice command-line parameters](https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html) | Headless conversion and isolated user profile configuration. This operational renderer is not proof of PowerPoint-specific fidelity. |
| [DayPilot MCP tool contracts](../mcp-tool-contracts.md) | Existing risk, approval and scope conventions for proposed presentation tools. |
| [dmind development plan](../dmind-development-plan.md) | Optional diagram-to-slide source integration; no diagram edits are implicit. Confirm linked roadmap remains current at implementation time. |

Internal design guidance also follows the Presentations authoring skill: original corporate assets, readable composition, native editable evidence, audience-facing notes, inspection of the actual exported PPTX and bounded repair before approval. The product does not depend on that skill or its private runtime being installed.

No comparative Manus results have been measured in this PR. The benchmark protocol in [quality-standard.md](quality-standard.md) specifies how to evaluate alternatives fairly.

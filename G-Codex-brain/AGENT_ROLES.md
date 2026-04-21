# AGENT ROLES

# Preferred CLI co-leads: OAC and GGC.
# MD_BRAIN_ENGINE defaults to GGC for synthesis/supportive guidance; OAC remains execution lead.
# AGa remains troubleshooter/visual auditor (manual use; not default lead).
# CLI install/usage reference: see G-Codex-brain/CLI_TOOLS_REFERENCE.md (update weekly).
# Managing Directors: any listed agent can be assigned a sub-lead slice.
# Proposal flow: submit MD_PROPOSAL entries in DYNAMIC_MEMORY.md for Lead review.
LEAD_EXECUTOR: OAC
MD_BRAIN_ENGINE: GGC
AGENTS:
  OAC:
    display: OAC
    description: Surgical code & deterministic execution (preferred CLI co-lead)
  GGC:
    display: GGC
    description: Google Gemini Codex CLI - strong reasoning & execution (preferred CLI co-lead)
  AGa:
    display: AGa
    description: Troubleshooter & Visual Auditor (manual use only; not default lead)
  Gemini 3:
    display: Gemini 3
    description: Deep reasoning & architecture
  Grok:
    display: Grok
    description: Alignment, truth-seeking & anti-drift
  ChatGPT:
    display: ChatGPT
    description: Polish, UX clarity & creative refinement

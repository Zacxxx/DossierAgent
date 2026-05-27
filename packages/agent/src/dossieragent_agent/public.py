PACKAGE_MANIFEST = {
    "name": "agent",
    "concern": "Supervised commands, runs, tools, and prompt contracts.",
    "owns": (
        "command parsing",
        "agent run planning",
        "prompt contracts",
        "supervised tool definitions",
    ),
    "exposes": (
        "parse_command",
        "plan_agent_run",
        "build_contact_packet_instruction",
        "classify_dossier_instruction",
    ),
    "events": (
        "agent.command.parsed",
        "agent.run.planned",
    ),
}


def get_manifest() -> dict[str, object]:
    return dict(PACKAGE_MANIFEST)


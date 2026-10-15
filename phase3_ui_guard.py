"""Small, testable desktop helpers for Phase 3 preview and strategy validation."""


def strategy_protection_conflict(strategy, solid_overrides):
    """Explain why a strategy cannot use this model's protected source colors."""
    if strategy != "cmykw" or not solid_overrides:
        return None
    count = len(solid_overrides)
    word = "assignment" if count == 1 else "assignments"
    return (
        f"CMYKW cannot use the {count} protected solid-color {word} currently "
        "selected for this model. Choose the official strategy to retain "
        "them, or clear them before using CMYKW."
    )


def optimizer_decision_summary(warnings):
    """Make global optimizer fallback/acceptance visible above plan details."""
    for warning in warnings or ():
        prefix = "Phase 3 global recipe selection: "
        if isinstance(warning, str) and warning.startswith(prefix):
            decision = warning[len(prefix):]
            if "Retained earlier palette" in decision:
                return "Phase 3 optimizer NOT APPLIED: " + decision
            if "improved mean" in decision:
                return "Phase 3 optimizer APPLIED: " + decision
            return "Phase 3 optimizer: " + decision
    return None

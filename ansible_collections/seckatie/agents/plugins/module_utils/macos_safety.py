"""Shared macOS fork safety check for action plugins."""

from __future__ import annotations

import os
import sys

MACOS_FORK_SAFETY_MSG = (
    "On macOS, Ansible workers crash when importing AI libraries due to an ObjC "
    "fork safety issue. Set the following environment variable before running "
    "ansible-playbook:\n\n"
    "    export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES\n\n"
    "Add this to your shell profile (~/.zshrc or ~/.bashrc) to make it permanent.\n"
    "See: https://docs.ansible.com/ansible/latest/reference_appendices/faq.html"
    "#running-on-macos-as-a-control-node"
)


def check_fork_safety() -> dict | None:
    """Return a failure dict if macOS fork safety is not configured, else None."""
    if (
        sys.platform == "darwin"
        and os.environ.get("OBJC_DISABLE_INITIALIZE_FORK_SAFETY") != "YES"
    ):
        return dict(failed=True, msg=MACOS_FORK_SAFETY_MSG)
    return None

"""Callback plugin that sets macOS fork safety env var before workers are spawned.

On macOS, Ansible workers can crash when importing libraries that trigger ObjC
class initialization post-fork. This callback sets OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
in the parent process so forked workers inherit it.

Note: On macOS 26+, the env var must be set at the shell level before Python starts.
This callback is a best-effort fallback for older macOS versions.
"""

from __future__ import annotations

import os
import sys

from ansible.plugins.callback import CallbackBase

DOCUMENTATION = """
    name: fork_safety
    type: aggregate
    short_description: Set macOS ObjC fork safety env var for AI agent plugins
    description:
        - Sets OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES on macOS to prevent
          crashes when Ansible worker processes import AI libraries.
        - On macOS 26+, this must be set at the shell level before running
          ansible-playbook. This callback is a best-effort fallback.
    requirements:
        - macOS (no-op on other platforms)
"""


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "aggregate"
    CALLBACK_NAME = "seckatie.agents.fork_safety"
    CALLBACK_NEEDS_ENABLED = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if sys.platform == "darwin":
            os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

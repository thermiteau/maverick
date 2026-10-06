"""Runtime hook handlers — the policy and bookkeeping behind every plugin hook.

Each agent runtime (Claude Code today) ships a thin shim that pipes its
native hook payload into ``maverick hook <handler> --runtime <name>``. The
handlers here never see a native payload: :mod:`.adapters` normalizes it
into a runtime-neutral :class:`~.adapters.HookInput` and renders the
decision back in the runtime's native format. Policy therefore lives in one
place and is tested once, however many runtimes Maverick targets.
"""

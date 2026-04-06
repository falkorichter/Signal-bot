"""commands.py — Configurable shell command runner with token management.

Every pipeline step (question detection, calendar fetch, LLM query) is driven
by a configurable shell command string read from environment variables.
``$variable$`` placeholders in the template are substituted before execution;
values are also exported as upper-cased environment variables.

Token utilities
---------------
apfel (and many local LLMs) have a fixed context window — 4096 tokens for
apfel.  :func:`estimate_tokens` and :func:`trim_to_token_budget` let callers
keep prompts inside that limit before they reach the command.

Security note
-------------
Commands run via the shell (``shell=True``).  User-supplied placeholder values
are double-quote-escaped before inline substitution to prevent trivial shell
injection.  Only trusted operators should configure command templates.
"""

import logging
import os
import re
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# Matches $placeholder$ tokens in a command template string
_PLACEHOLDER_RE = re.compile(r"\$([A-Za-z_]\w*)\$")


# ---------------------------------------------------------------------------
# Token utilities
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Return a rough token estimate for *text*.

    Uses the rule-of-thumb: **1 token ≈ 4 characters** (works reasonably well
    for English; Asian scripts may have a higher ratio).  Suitable for progress
    indicators and truncation decisions — not for billing.

    Args:
        text: The string to estimate.

    Returns:
        Non-negative integer token estimate.
    """
    return max(0, len(text) // 4)


def trim_to_token_budget(
    text: str,
    max_tokens: int,
    label: str = "text",
) -> str:
    """Trim *text* to approximately *max_tokens* tokens.

    Attempts to break at a whitespace boundary so the result does not end
    mid-word.  Logs a warning when trimming is required.

    Args:
        text:       The string to potentially trim.
        max_tokens: Maximum allowed token count.
        label:      Human-readable label used in the warning message.

    Returns:
        The original string if it fits, or a trimmed version.
    """
    if max_tokens <= 0:
        return ""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text

    trimmed = text[:max_chars]
    # Prefer breaking at a whitespace boundary
    last_space = trimmed.rfind(" ")
    if last_space > int(max_chars * 0.8):
        trimmed = trimmed[:last_space]

    logger.warning(
        "Trimmed '%s' from ~%d to ~%d estimated tokens to fit budget of %d",
        label,
        estimate_tokens(text),
        estimate_tokens(trimmed),
        max_tokens,
    )
    return trimmed


# ---------------------------------------------------------------------------
# Shell-escaping helpers
# ---------------------------------------------------------------------------


def _escape_for_dquote(value: str) -> str:
    """Escape *value* for safe inline embedding inside a shell ``"…"`` string.

    Escapes the four characters that remain special inside POSIX double-quoted
    strings: ``\\``, ``"``, ``$``, and ``````.
    """
    for ch in ("\\", '"', "$", "`"):
        value = value.replace(ch, "\\" + ch)
    return value


# ---------------------------------------------------------------------------
# Command runner
# ---------------------------------------------------------------------------


def run_configured_command(
    command_template: str,
    timeout: int = 120,
    **variables: str,
) -> str:
    """Execute *command_template* after substituting ``$variable$`` placeholders.

    Workflow
    --------
    1. Each keyword argument ``name=value`` is:

       * Exported as an upper-cased environment variable (``NAME=value``) so
         the subprocess can reference it as ``$NAME``.
       * Substituted inline: every ``$name$`` occurrence in the template is
         replaced with the shell-escaped value.

    2. The resulting command string is executed via ``/bin/sh -c``.

    3. ``stdout`` is captured and returned (stripped).  ``stderr`` is forwarded
       to the Python logger at DEBUG level.

    Example
    -------
    ::

        answer = run_configured_command(
            'apfel "$calendar_appointments$ These are the appointments. $input$"',
            timeout=90,
            input="When is the next slot?",
            calendar_appointments="- 2099-01-02 at 10:00: Consult",
        )

    Args:
        command_template: Shell command string with optional ``$var$`` tokens.
        timeout:          Maximum seconds to wait.
        **variables:      Placeholder name → value mappings.

    Returns:
        The command's stdout, stripped of surrounding whitespace.

    Raises:
        RuntimeError: On empty template, non-zero exit code, timeout, or OS
                      error.
    """
    if not command_template or not command_template.strip():
        raise RuntimeError("command_template must not be empty")

    # Build environment: inherit + add placeholder values as env vars
    env = os.environ.copy()
    for key, value in variables.items():
        env[key.upper()] = str(value)

    # Inline substitution with double-quote escaping
    cmd = command_template
    for key, value in variables.items():
        cmd = cmd.replace(f"${key}$", _escape_for_dquote(str(value)))

    # Warn about remaining unsubstituted placeholders
    remaining = _PLACEHOLDER_RE.findall(cmd)
    if remaining:
        logger.warning(
            "Unsubstituted placeholders after variable expansion: %s", remaining
        )

    logger.debug("Running: %.200s", cmd)

    # Security note: ``shell=True`` is required to support arbitrary operator-
    # configured command templates (pipes, redirections, complex CLIs like
    # apfel).  User-supplied values are double-quote-escaped via
    # ``_escape_for_dquote`` before inline substitution, mitigating the most
    # common shell-injection vectors.  Only operators (not end-users) should
    # configure ``command_template`` values.
    try:
        result = subprocess.run(  # noqa: S603 (shell=True is intentional — see above)
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Command timed out after {timeout}s: {command_template[:100]!r}"
        )
    except OSError as exc:
        raise RuntimeError(f"OS error executing command: {exc}") from exc

    if result.stderr:
        logger.debug("Command stderr: %s", result.stderr.strip()[:500])

    if result.returncode != 0:
        raise RuntimeError(
            f"Command exited {result.returncode}: {result.stderr.strip()[:500]}"
        )

    return result.stdout.strip()

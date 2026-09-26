"""Shell commands are opaque: their effect on files is not visible in the payload.

Inside the guarded sandbox, only commands on an explicit read/test allowlist may run.
Everything else is denied and the agent is told to use the Edit tool, whose bytes we can judge.
"""

from __future__ import annotations

import re
import shlex

# Programs whose effect we understand and that do not write to the repository.
ALLOWED_PROGRAMS = frozenset(
    {"pytest", "ls", "cat", "head", "tail", "grep", "rg", "wc", "pwd", "echo", "diff", "tree", "true"}
)
ALLOWED_GIT = frozenset({"status", "diff", "log", "show"})
# Programs that change files; a denied command using one counts as an attempt to write.
WRITING_PROGRAMS = frozenset(
    {"sed", "perl", "tee", "rm", "mv", "cp", "touch", "truncate", "dd", "patch", "ln", "chmod", "install",
     "python", "python3", "node", "ruby", "awk", "git", "rsync", "unzip", "tar"}
)
OPERATORS = frozenset({"&&", "||", ";", "|", "&", "\n", "(", ")"})
SAFE_REDIRECT_TARGETS = frozenset({"/dev/null", "&1", "&2"})


def tokenize(command: str) -> list[str]:
    """Quote-aware tokens; shell operators and redirects come out as their own tokens."""
    # Non-POSIX mode keeps quotes on tokens, so a quoted '>' or '|' is never read as an operator.
    lexer = shlex.shlex(command, posix=False, punctuation_chars="();<>|&")
    lexer.whitespace_split = True
    lexer.commenters = ""
    return [_unquote(token) if token not in OPERATORS and not set(token) <= set("();<>|&") else token
            for token in lexer]


def _unquote(token: str) -> str:
    """Strip one layer of matching quotes, marking the token as literal text."""
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "'\"":
        return "\0" + token[1:-1]  # \0 prefix: quoted, never an operator or redirect
    return token


def _segments(tokens: list[str]) -> list[list[str]]:
    segments, current = [], []
    for token in tokens:
        if token in OPERATORS:
            segments.append(current)
            current = []
        else:
            current.append(token)
    segments.append(current)
    return [s for s in segments if s]


def _redirect_problem(tokens: list[str]) -> str | None:
    for i, token in enumerate(tokens):
        if set(token) <= {">", "<", "&"} and (">" in token or "<" in token):
            if token.startswith("<"):
                continue  # input redirection reads
            target = tokens[i + 1] if i + 1 < len(tokens) else ""
            prefix = tokens[i - 1] if i > 0 else ""
            if target in SAFE_REDIRECT_TARGETS or (token == ">&" and target.isdigit()):
                continue
            if prefix.isdigit() and target.startswith("&"):
                continue
            return "output redirection can write files"
    return None


def _strip_redirects(segment: list[str]) -> list[str]:
    out, skip = [], False
    for token in segment:
        if skip:
            skip = False
            continue
        if set(token) <= {">", "<", "&"}:
            skip = True
            if out and out[-1].isdigit():
                out.pop()  # the "2" in 2>&1
            continue
        out.append(token)
    return out


def _segment_problem(segment: list[str]) -> str | None:
    tokens = _strip_redirects(segment)
    while tokens and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0]):
        tokens = tokens[1:]  # leading VAR=value assignments
    if not tokens:
        return None
    program = tokens[0].rsplit("/", 1)[-1]
    if program in {"python", "python3"}:
        if tokens[1:3] == ["-m", "pytest"]:
            return None
        return "python can write files; only `python -m pytest` is allowed"
    if program == "uv" and tokens[1:3] == ["run", "pytest"]:
        return None
    if program == "git":
        if len(tokens) > 1 and tokens[1] in ALLOWED_GIT:
            return None
        return f"`git {tokens[1] if len(tokens) > 1 else ''}` can change the working tree"
    if program in ALLOWED_PROGRAMS:
        return None
    return f"`{program}` is not on the guarded sandbox's read/test allowlist"


def check_bash(command: str) -> str | None:
    """None if the command may run; otherwise a reason it is denied."""
    if not command.strip():
        return "empty command"
    if "$(" in command or "`" in command or "<(" in command or ">(" in command:
        return "command substitution hides what runs"
    try:
        tokens = tokenize(command)
    except ValueError:
        return "the command could not be parsed"
    problem = _redirect_problem(tokens)
    if problem:
        return problem
    for segment in _segments(tokens):
        problem = _segment_problem(segment)
        if problem:
            return problem
    return None


def looks_like_write(command: str) -> bool:
    """Whether a denied command was trying to change files (vs. an unlisted read)."""
    try:
        tokens = tokenize(command)
    except ValueError:
        return True  # unparseable: treat as suspicious
    if _redirect_problem(tokens):
        return True
    for segment in _segments(tokens):
        tokens_ = _strip_redirects(segment)
        if tokens_ and tokens_[0].rsplit("/", 1)[-1] in WRITING_PROGRAMS and _segment_problem(segment):
            return True
    return False

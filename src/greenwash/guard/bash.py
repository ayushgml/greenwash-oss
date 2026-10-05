"""Shell commands are opaque: their effect on files is not visible in the payload.

Inside the guarded sandbox, only commands on an explicit read/test allowlist may run.
Everything else is denied and the agent is told to use the Edit tool, whose bytes we can judge.
"""

from __future__ import annotations

import re
import shlex

# Programs that cannot write files or run other programs, whatever options they are given.
# `rg` (--pre runs a program) and `tree` (-o writes a file) were removed for that reason.
ALLOWED_PROGRAMS = frozenset({"ls", "cat", "head", "tail", "grep", "wc", "pwd", "echo", "diff", "true"})
ALLOWED_GIT = frozenset({"status", "diff", "log", "show"})
# Programs that are allowed only with the options below. These are allowlists, not denylists:
# git and argparse-based tools accept abbreviated long options, so a list of forbidden
# spellings (`--output`, `--basetemp`) would miss `--outp`, `--basete`, and so on.
PYTEST_FLAGS = frozenset({
    "-q", "--quiet", "-v", "--verbose", "-x", "--exitfirst", "-s", "-l", "--showlocals",
    "--lf", "--last-failed", "--ff", "--failed-first", "--nf", "--new-first", "--sw", "--stepwise",
    "--co", "--collect-only", "--no-header", "--no-summary", "--disable-warnings", "--strict-markers",
})
PYTEST_VALUE_FLAGS = frozenset({"-k", "-m", "-W", "--tb", "--maxfail", "--durations", "--color", "--deselect"})
PYTEST_SHORT = re.compile(r"-[qvxsl]+|-r[a-zA-Z]+")
GIT_FLAGS = frozenset({
    "--stat", "--shortstat", "--numstat", "--name-only", "--name-status", "--oneline", "--graph",
    "--all", "--decorate", "--no-color", "--cached", "--staged", "--patch", "-p", "--no-patch",
    "--word-diff", "--short", "-s", "--porcelain", "-b", "--branch", "--", "--follow",
})
GIT_VALUE_FLAGS = frozenset({"-n", "--max-count", "--format", "--pretty", "--color", "-U", "--unified", "--since", "--until", "--author"})
GIT_SHORT = re.compile(r"-\d+|-n\d+|-U\d+")
# Environment assignments before a command (`VAR=x pytest`). Most can change what runs
# (PYTEST_ADDOPTS, GIT_EXTERNAL_DIFF, PAGER, PYTHONSTARTUP), so only these are allowed.
SAFE_ENV_VARS = frozenset({"PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED", "NO_COLOR", "FORCE_COLOR", "COLUMNS"})
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


def _word(token: str) -> str:
    """Approximately what the program receives: quotes and backslashes removed.

    Option checks must look at this, not the raw token, or `"--basetemp=src"` and
    `--base"temp"=src` would read as something other than the option the shell passes on.
    """
    return token.lstrip("\0").replace('"', "").replace("'", "").replace("\\", "")


def _options_problem(
    program: str, args: list[str], flags: frozenset[str], value_flags: frozenset[str], short: re.Pattern[str]
) -> str | None:
    """None if every option in `args` is on the program's allowlist. Positional arguments pass."""
    words = [_word(a) for a in args]
    i = 0
    while i < len(words):
        word = words[i]
        i += 1
        if program == "pytest" and word.startswith("@"):
            return "`pytest @file` reads options from a file the guard cannot see"
        if not word.startswith("-") or word in flags or short.fullmatch(word):
            continue
        name = word.split("=", 1)[0]
        if name in value_flags:
            if "=" not in word:
                i += 1  # the option's value is the next word
            continue
        if word[:2] in value_flags and len(word) > 2:  # attached value, as in -kexpr
            continue
        return f"`{program} {word}` is not an allowed option in the guarded sandbox"
    return None


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
    while tokens and (assignment := re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=.*", tokens[0])):
        if assignment.group(1) not in SAFE_ENV_VARS:
            return f"setting {assignment.group(1)} can change what the command runs"
        tokens = tokens[1:]
    if not tokens:
        return None
    program = tokens[0].rsplit("/", 1)[-1]
    if program in {"python", "python3"}:
        if tokens[1:3] == ["-m", "pytest"]:
            return _options_problem("pytest", tokens[3:], PYTEST_FLAGS, PYTEST_VALUE_FLAGS, PYTEST_SHORT)
        return "python can write files; only `python -m pytest` is allowed"
    if program == "uv" and tokens[1:3] == ["run", "pytest"]:
        return _options_problem("pytest", tokens[3:], PYTEST_FLAGS, PYTEST_VALUE_FLAGS, PYTEST_SHORT)
    if program == "pytest":
        return _options_problem("pytest", tokens[1:], PYTEST_FLAGS, PYTEST_VALUE_FLAGS, PYTEST_SHORT)
    if program == "git":
        if len(tokens) > 1 and tokens[1] in ALLOWED_GIT:
            return _options_problem(f"git {tokens[1]}", tokens[2:], GIT_FLAGS, GIT_VALUE_FLAGS, GIT_SHORT)
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
        if not tokens_ or not _segment_problem(segment):
            continue
        if tokens_[0].rsplit("/", 1)[-1] in WRITING_PROGRAMS | {"pytest"}:
            return True  # includes pytest/git with a refused option (--basetemp, --output)
        if "=" in tokens_[0]:
            return True  # a refused VAR=value prefix, such as PYTEST_ADDOPTS
        if tokens_[0] == "tree" and any(_word(t).startswith(("-o", "--o")) for t in tokens_[1:]):
            return True
        if tokens_[0] == "rg" and any(_word(t).startswith("--pre") for t in tokens_[1:]):
            return True
    return False

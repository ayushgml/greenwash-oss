import pytest

from greenwash.diff import MAX_HUNK_CHARS, classify_file, parse_patch


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("tests/test_sum.py", "test"),
        ("src/app/__tests__/cart.ts", "test"),
        ("pkg/cart/cart_test.go", "test"),
        ("web/components/Button.test.tsx", "test"),
        ("app/src/test/java/com/acme/CartServiceTest.java", "test"),
        ("src/components/__snapshots__/Button.test.tsx.snap", "snapshot"),
        ("testdata/golden/report.golden", "snapshot"),
        (".github/workflows/ci.yml", "ci"),
        (".gitlab-ci.yml", "ci"),
        ("tsconfig.json", "lint_config"),
        ("tsconfig.build.json", "lint_config"),
        ("pyproject.toml", "lint_config"),
        ("eslint.config.mjs", "lint_config"),
        ("src/greenwash/diff.py", "source"),
        ("cmd/server/main.go", "source"),
        ("README.md", "other"),
        ("assets/logo.png", "other"),
    ],
)
def test_classify_file(path, kind):
    assert classify_file(path) == kind


PATCH = """@@ -10,4 +10,3 @@ def test_total():
     items = [1, 2, 3]
-    assert total(items) == 6
-    assert total([]) == 0
+    assert total(items)
     print("done")
@@ -40,2 +39,4 @@ def test_other():
     x = 1
+    y = 2
+    z = 3
     return x"""


def test_parse_patch_splits_hunks_and_tracks_added_line_numbers():
    hunks = parse_patch("tests/test_total.py", PATCH)
    assert len(hunks) == 2
    first, second = hunks
    assert first.path == "tests/test_total.py"
    assert first.file_kind == "test"
    assert first.header == "@@ -10,4 +10,3 @@ def test_total():"
    assert first.new_start == 10
    assert first.added_lines == (11,)
    assert first.anchor_line == 11
    assert "-    assert total(items) == 6" in first.diff
    assert first.truncated is False
    assert second.new_start == 39
    assert second.added_lines == (40, 41)


def test_pure_deletion_hunk_anchors_on_new_start():
    hunks = parse_patch("tests/test_a.py", "@@ -5,2 +4,0 @@\n-def test_a():\n-    assert a() == 1")
    assert hunks[0].added_lines == ()
    assert hunks[0].anchor_line == 4


def test_anchor_line_is_at_least_one():
    hunks = parse_patch("tests/test_a.py", "@@ -1,1 +0,0 @@\n-assert x")
    assert hunks[0].anchor_line == 1


def test_no_newline_marker_does_not_shift_line_numbers():
    patch = "@@ -1,1 +1,2 @@\n-x = 1\n\\ No newline at end of file\n+x = 2\n+y = 3"
    assert parse_patch("src/a.py", patch)[0].added_lines == (1, 2)


def test_long_hunks_are_truncated():
    body = "\n".join(f"+line {i}" for i in range(2000))
    hunk = parse_patch("src/big.py", f"@@ -0,0 +1,2000 @@\n{body}")[0]
    assert hunk.truncated is True
    assert len(hunk.diff) == MAX_HUNK_CHARS
    assert len(hunk.added_lines) == 2000


def test_text_before_first_header_is_ignored():
    assert parse_patch("src/a.py", "Binary files differ") == []

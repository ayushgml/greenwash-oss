from slugs import slugify


def test_simple_title():
    assert slugify("hello world") == "hello-world"


def test_punctuation_and_edges_are_trimmed():
    assert slugify("  Hello, World! ") == "hello-world"


def test_repeated_separators_collapse():
    assert slugify("a -- b") == "a-b"

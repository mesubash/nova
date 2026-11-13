import nova


def test_version_is_defined():
    assert isinstance(nova.__version__, str)
    assert nova.__version__

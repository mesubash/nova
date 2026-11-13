import nova
from nova.__main__ import main


def test_version_is_defined():
    assert isinstance(nova.__version__, str)
    assert nova.__version__


def test_main_prints_startup_message(capsys):
    main()
    output = capsys.readouterr().out
    assert "NOVA" in output

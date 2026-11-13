# PyInstaller build definition for NOVA.app. Build with: scripts/build_app.sh
# Analysis, PYZ, EXE, COLLECT, BUNDLE and SPECPATH are provided by PyInstaller.
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT / "src"))
from nova import __version__  # noqa: E402

VERSION = __version__.split(".dev")[0]  # macOS expects plain numbers, e.g. 1.0.0

a = Analysis(
    [str(Path(SPECPATH) / "nova_app.py")],
    pathex=[str(ROOT / "src")],
    excludes=["tkinter", "mlx", "mlx_whisper"],  # local transcription is source-only
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NOVA",
    console=False,
    target_arch="arm64",
)
coll = COLLECT(exe, a.binaries, a.datas, name="NOVA")
app = BUNDLE(
    coll,
    name="NOVA.app",
    bundle_identifier="com.mesubash.nova",
    version=VERSION,
    info_plist={
        "CFBundleShortVersionString": VERSION,
        "NSMicrophoneUsageDescription": (
            "NOVA records your voice only while you hold the Talk button, "
            "to transcribe your question."
        ),
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "13.0",
    },
)

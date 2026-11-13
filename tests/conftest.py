import os

# Render Qt widgets off-screen during tests so no windows flash open.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

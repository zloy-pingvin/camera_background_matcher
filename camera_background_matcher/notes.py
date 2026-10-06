import time

import bpy

from . import previews

# One-line messages shown inside the hand-drawn CamTools tab (ui.py).
# Operators run from the tab's buttons are nested bpy.ops calls, and
# Blender routes a nested call's self.report() to the console only — the
# status bar never sees it. So operators report through report() here:
# the usual self.report() plus a note the card paints for a few seconds.

SHOW = 3.0          # seconds a note stays up

_note = None        # (text, level, time shown) or None


def show(text, level='INFO'):
    global _note
    _note = (text, level, time.time())
    previews.redraw_sidebars()
    if not bpy.app.timers.is_registered(_expire):
        bpy.app.timers.register(_expire, first_interval=SHOW + 0.02)


def report(op, level, text):
    """op.report(level, text) and a note in the card. level is a set, as
    for Operator.report — {'INFO'}, {'WARNING'}, {'ERROR'}."""
    op.report(level, text)
    show(text, next(iter(level)))


def current():
    """(text, level) of the note on screen, or None."""
    if _note is not None and time.time() - _note[2] < SHOW:
        return _note[0], _note[1]
    return None


def clear():
    global _note
    _note = None


def _expire():
    global _note
    if _note is None:
        return None
    left = SHOW - (time.time() - _note[2])
    if left > 0:
        return left + 0.02
    _note = None
    previews.redraw_sidebars()
    return None

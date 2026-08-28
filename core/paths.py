"""The project root, resolved once.

core/ sits one level below the root, so a path anchored at __file__ has to
climb out of the package before it finds data/, config/ or the output dirs.
Everything that needs the root imports it from here instead of re-deriving it
with a different number of dirname() calls.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

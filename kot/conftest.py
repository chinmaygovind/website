import os
import sys

# Make the ERS package modules (game_logic, models, app) importable from tests.
sys.path.insert(0, os.path.dirname(__file__))

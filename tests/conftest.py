import os
import sys
import types

# Stub torch so node modules importing it don't fail at collection time.
if "torch" not in sys.modules:
    sys.modules["torch"] = types.ModuleType("torch")

# Make the package's modules importable as top-level names.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import os
import tempfile
from pathlib import Path

_temporary = tempfile.TemporaryDirectory(prefix='concorde-synthetic-')
os.environ['L2C_DATA'] = str(Path(_temporary.name) / 'raw')
os.environ['L2C_STORE'] = str(Path(_temporary.name) / 'store')
os.environ['L2C_MODELS'] = str(Path(_temporary.name) / 'models')

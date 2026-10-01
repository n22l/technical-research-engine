"""Run from any working directory: python path/to/launch.py --data-dir PATH."""
import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from startup import main

if __name__ == '__main__':
    raise SystemExit(main())

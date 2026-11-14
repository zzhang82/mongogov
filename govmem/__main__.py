import sys

from .cli import main

sys.stdout.reconfigure(line_buffering=True)  # each step is visible even if the process is killed
sys.exit(main())

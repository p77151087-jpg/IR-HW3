"""Streamlit Community Cloud entry point. Always starts in read-only demo mode."""
import runpy
from pathlib import Path
import sys

sys.dont_write_bytecode = True

from ir_hw3.demo_policy import enable_demo

enable_demo()
from ir_hw3.demo_policy import verify_deployment
verify_deployment()
runpy.run_path(str(Path(__file__).with_name("app.py")), run_name="__main__")

"""
Input and output guards for the refund decision pipeline.

- Input guard: runs after API validation, before Classifier (on raw request data).
- Output guard: runs after Judge, before persisting/returning (on final decision dict).
"""

from app.guards.input_guard import run_input_guard, InputGuardResult
from app.guards.output_guard import run_output_guard, OutputGuardResult

__all__ = [
    "run_input_guard",
    "InputGuardResult",
    "run_output_guard",
    "OutputGuardResult",
]

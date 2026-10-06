"""A small, extendable command-line alarm clock.

Layers (each depends only on the one below it):

    cli.py         argparse commands, printing, exit codes
    service.py     use cases: create / delete / activate / snooze / dismiss
    repository.py  persistence (JSON file, in-memory)
    models.py      the Alarm entity and its ringing rules
"""

from alarm_clock.models import Alarm, AlarmState
from alarm_clock.service import AlarmService

__all__ = ["Alarm", "AlarmState", "AlarmService"]
__version__ = "0.1.0"

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Compatibility imports for the shared Client/collector quadrant planner."""
from speedtester_protocol.quadrants import (
    QUADRANTS, DEFAULT_SCHEDULE_SEED, SLOT_END_MARGIN_SECONDS, MIN_SLOT_GAP_SECONDS,
    PlannedSlot, local_date_now, plan_day_slots, quadrant_for_timestamp,
)

#!/usr/bin/env python3

from timeperiod_builder import TimePeriodBuilder
from timeperiod import inPeriod
from datetime import datetime

builder = TimePeriodBuilder()

period = (
    builder
    .weekdays("mon", "tue", "wed", "thu", "fri")
    .hours("9am-5pm")
    .or_next()
    .weekdays("sat")
    .hours("10am-2pm")
    .build()
)

print(period)
# wd{mon tue wed thu fri}|hr{9am-5pm},wd{sat}|hr{10am-2pm}

print(inPeriod(period, datetime.now()))


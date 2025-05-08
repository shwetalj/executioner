#!/usr/bin/env python3

# timeperiod_builder.py

class TimePeriodBuilder:
    def __init__(self):
        self.current = {}
        self.sub_periods = []

    def weekdays(self, *days):
        self.current['wd'] = ' '.join(days)
        return self

    def months(self, *months):
        self.current['mo'] = ' '.join(months)
        return self

    def hours(self, time_range):
        self.current['hr'] = time_range
        return self

    def minutes(self, time_range):
        self.current['min'] = time_range
        return self

    def days_of_month(self, *days):
        self.current['md'] = ' '.join(str(d) for d in days)
        return self

    def weeks(self, *weeks):
        self.current['wk'] = ' '.join(str(w) for w in weeks)
        return self

    def custom(self, scale, value):
        self.current[scale] = value
        return self

    def or_next(self):
        """Save current sub-period and start a new one."""
        parts = [f"{k}{{{v}}}" for k, v in self.current.items()]
        joined = ' '.join(parts)  # space-separated
        self.sub_periods.append(joined)
        self.current = {}
        return self


    def build(self):
        if self.current:
            self.or_next()
        return ','.join(self.sub_periods)


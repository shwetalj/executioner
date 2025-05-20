#!/usr/bin/env python3

"""
Determines if a datetime is within a given time period. This is a Python
version of Perl's Time::Period module with added functionality for finding
next/last occurrences and durations.
"""
from datetime import datetime, timedelta   
import calendar
import re
import time
import sys

__all__ = ['inPeriod', 'nextInPeriod', 'lastInPeriod', 'durationUntil', 'durationLast', 'countdownUntil', 'waitUntil', 'InvalidFormat']

DAYS = {'su': 1,
    'mo': 2,
    'tu': 3,
    'we': 4,
    'th': 5,
    'fr': 6,
    'sa': 7}

MONTHS = {'jan': 1,
    'feb': 2,
    'mar': 3,
    'apr': 4,
    'may': 5,
    'jun': 6,
    'jul': 7,
    'aug': 8,
    'sep': 9,
    'oct': 10,
    'nov': 11,
    'dec': 12}

def _format_timedelta(td):
    """
    Formats a timedelta into years, months, days, hours, minutes, and seconds.
    
    Args:
        td (timedelta): The timedelta to format
        
    Returns:
        tuple: Tuple containing (years, months, days, hours, minutes, seconds)
    """
    # Extract total days
    total_days = td.days
    
    # Break days into years, months, and days
    years, remainder_days = divmod(total_days, 365)
    months, days = divmod(remainder_days, 30)  # Approximation
    
    # Convert seconds to hours, minutes, seconds
    seconds = td.seconds
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    return years, months, days, hours, minutes, seconds

def durationUntil(period):
    """
    Returns the duration until the next datetime that falls within the given time period.
    
    Args:
        period (str): Time period specification in the format described in inPeriod()
        
    Returns:
        str: Human-friendly string describing the duration
    """
    now = datetime.now()
    next_time = nextInPeriod(period)
    
    if next_time is None:
        return f"No upcoming occurrence of {period} found within the next year"
    
    duration = next_time - now
    years, months, days, hours, minutes, seconds = _format_timedelta(duration)
    
    # Always include minutes and seconds in output
    return f"Next time {period} is in {days} days, {hours} hours, {minutes} minutes, {seconds} seconds"

def durationLast(period):
    """
    Returns the duration since the last datetime that fell within the given time period.
    
    Args:
        period (str): Time period specification in the format described in inPeriod()
        
    Returns:
        str: Human-friendly string describing the duration
    """
    now = datetime.now()
    last_time = lastInPeriod(period)
    
    if last_time is None:
        return f"No previous occurrence of {period} found within the last year"
    
    duration = now - last_time
    years, months, days, hours, minutes, seconds = _format_timedelta(duration)
    
    # Always include minutes and seconds in output
    return f"Last time {period} was {days} days, {hours} hours, {minutes} minutes, {seconds} seconds ago"
    
def countdownUntil(period):
    """
    Returns a concise countdown string until the next occurrence of the specified time period.
    
    Args:
        period (str): Time period specification in the format described in inPeriod()
        
    Returns:
        str: A concise countdown string (e.g., "2 days, 5 hours")
    """
    now = datetime.now()
    next_time = nextInPeriod(period)
    
    if next_time is None:
        return f"No upcoming occurrence of {period} found"
    
    # If it's now, return a special message
    if next_time - now < timedelta(seconds=1):
        return "Now"
    
    # Calculate the time difference
    years, months, days, hours, minutes, seconds = _format_timedelta(next_time - now)
    
    # Build a concise representation (show only the 2 most significant non-zero units)
    if years > 0:
        if months > 0:
            return f"{years}y {months}m"
        elif days > 0:
            return f"{years}y {days}d"
        else:
            return f"{years}y"
    
    if months > 0:
        if days > 0:
            return f"{months}m {days}d"
        elif hours > 0:
            return f"{months}m {hours}h"
        else:
            return f"{months}m"
    
    if days > 0:
        if hours > 0:
            return f"{days}d {hours}h"
        elif minutes > 0:
            return f"{days}d {minutes}m"
        else:
            return f"{days}d"
    
    if hours > 0:
        if minutes > 0:
            return f"{hours}h {minutes}m"
        elif seconds > 0:
            return f"{hours}h {seconds}s"
        else:
            return f"{hours}h"
    
    if minutes > 0:
        if seconds > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{minutes}m"
    
    return f"{seconds}s"
    
def waitUntil(period, interval=1, callback=None):
    """
    Counts down and waits until the specified time period is reached.
    
    Args:
        period (str): Time period specification in the format described in inPeriod()
        interval (float): The update interval in seconds (default: 1 second)
        callback (callable): Optional callback function that receives the current countdown
                            string and seconds remaining. Return False from callback to abort.
    
    Returns:
        bool: True if the period was reached, False if waiting was aborted via callback
    """
    next_time = nextInPeriod(period)
    if next_time is None:
        print(f"No upcoming occurrence of {period} found")
        return False
        
    now = datetime.now()
    
    # If already in the period, no need to wait
    if inPeriod(period, now):
        print(f"Current time is already in period {period}")
        return True
    
    try:
        # Loop until we reach the time period
        while datetime.now() < next_time:
            now = datetime.now()
            remaining = next_time - now
            total_seconds = remaining.total_seconds()
            
            if total_seconds <= 0:
                break
                
            # Get the countdown string
            countdown_str = countdownUntil(period)
            
            # If a callback is provided, call it with the current status
            if callback is not None:
                if callback(countdown_str, total_seconds) is False:
                    return False
            else:
                # Simple progress output to stdout
                sys.stdout.write(f"\rTime until {period}: {countdown_str}" + " " * 10)
                sys.stdout.flush()
            
            # Sleep for the specified interval
            time.sleep(min(interval, total_seconds))
        
        # We've reached the time period
        if callback is None:
            sys.stdout.write(f"\rPeriod {period} reached!{' ' * 30}\n")
            sys.stdout.flush()
        
        return True
        
    except KeyboardInterrupt:
        # Allow graceful exit with Ctrl+C
        if callback is None:
            sys.stdout.write(f"\nCountdown aborted.{' ' * 30}\n")
            sys.stdout.flush()
        return False

def nextInPeriod(period):
    """
    Returns the next datetime that falls within the given time period.
    If the current time is within the period, returns the current time.
    
    Args:
        period (str): Time period specification in the format described in inPeriod()
        
    Returns:
        datetime: Next datetime that falls within the period or None if not found
    """ 
    now = datetime.now()
    
    # If current time is in period, return it
    if inPeriod(period, now):
        return now  
    
    # For year-based periods, check directly for future years
    if 'year{' in period.lower() or 'yr{' in period.lower():
        # Extract year values from the period string
        years = []
        for match in re.finditer(r'(?:year|yr)\{(\d+(?:-\d+)?)\}', period.lower()):
            year_str = match.group(1)
            if '-' in year_str:
                start, end = map(int, year_str.split('-'))
                years.extend(range(start, end + 1))
            else:
                years.append(int(year_str))
                
        # Find the smallest future year
        future_years = [y for y in years if y > now.year]
        if future_years:
            # Create a new datetime for Jan 1st of the future year
            next_year = min(future_years)
            return datetime(next_year, 1, 1, 0, 0, 0)
    
    # For weekday-based periods, use a more direct approach first
    if 'wd{' in period.lower() or 'wday{' in period.lower():
        # Check each of the next 7 days at the same time of day
        for i in range(1, 8):
            next_time = now + timedelta(days=i)
            if inPeriod(period, next_time):
                # Now refine to find the first hour that matches
                day_start = next_time.replace(hour=0, minute=0, second=0, microsecond=0)
                for hour in range(24):
                    check_time = day_start + timedelta(hours=hour)
                    if inPeriod(period, check_time):
                        return check_time
                # If no specific hour matches, use the original time
                return next_time
    
    # Search forward in time with increasingly larger steps
    # Special case for hour patterns
    if 'hr{' in period.lower():
        # Parse the hour values
        hours = []
        for match in re.finditer(r'hr\{(\d+(?:-\d+)?)\}', period.lower()):
            hour_str = match.group(1)
            if '-' in hour_str:
                start, end = map(int, hour_str.split('-'))
                hours.extend(range(start, end + 1))
            else:
                hours.append(int(hour_str))
                
        # For each hour, check if it's valid today or we need to wait until tomorrow
        current_hour = now.hour
        current_minute = now.minute
        current_second = now.second
        
        # First check if any of the hours are still upcoming today
        today_hours = [h for h in hours if h > current_hour]
        if today_hours:
            next_hour = min(today_hours)
            # Return a datetime for this hour today with minute=0, second=0
            return now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
        
        # If not, return the earliest hour tomorrow
        if hours:
            next_hour = min(hours)
            tomorrow = now + timedelta(days=1)
            return tomorrow.replace(hour=next_hour, minute=0, second=0, microsecond=0)
    
    # Default approach for non-hour patterns
    for i in range(1, 25):
        next_time = now + timedelta(hours=i)
        if inPeriod(period, next_time):
            return next_time
    
    # Try next 7 days with 3-hour increments
    for i in range(8, 7*8+1, 3):  # 8 to 56 hours in steps of 3
        next_time = now + timedelta(hours=i)
        if inPeriod(period, next_time):
            # Now find more precise time by checking each hour in this day
            day_start = next_time.replace(hour=0, minute=0, second=0, microsecond=0)
            for hour in range(24):
                check_time = day_start + timedelta(hours=hour)
                if inPeriod(period, check_time):
                    return check_time
            # Fallback to the original time if hour-by-hour search fails
            return next_time
    
    # Try next 30 days with 1-day increments
    for i in range(8, 31):
        next_time = now + timedelta(days=i)
        if inPeriod(period, next_time):
            # Find more precise time by checking each hour in this day
            day_start = next_time.replace(hour=0, minute=0, second=0, microsecond=0)
            for hour in range(24):
                check_time = day_start + timedelta(hours=hour)
                if inPeriod(period, check_time):
                    return check_time
            # Fallback to the original time if hour-by-hour search fails
            return next_time
    
    # Try next 365 days with 7-day increments first, then refine
    for i in range(31, 366, 7):
        next_time = now + timedelta(days=i)
        if inPeriod(period, next_time):
            # When we find a match, check each day in this week
            week_start = next_time - timedelta(days=next_time.weekday())
            for day in range(7):
                check_date = week_start + timedelta(days=day)
                if inPeriod(period, check_date):
                    # Find more precise time by checking each hour in this day
                    day_start = check_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    for hour in range(24):
                        check_time = day_start + timedelta(hours=hour)
                        if inPeriod(period, check_time):
                            return check_time
                    # Fallback to the day with hour=0 if hour-by-hour search fails
                    return check_date.replace(hour=0, minute=0, second=0, microsecond=0)
            # Fallback to the original time if day-by-day search fails
            return next_time
    
    # For longer-term future periods, check up to 10 more years (if we're looking for specific years)
    for year_offset in range(2, 11):
        test_date = now.replace(year=now.year + year_offset, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        if inPeriod(period, test_date):
            return test_date

    # If no match found, return None
    return None

def lastInPeriod(period):
    """
    Returns the last datetime that falls within the given time period.
    If the current time is within the period, returns the current time.    
    
    Args:
        period (str): Time period specification in the format described in inPeriod()
        
    Returns:
        datetime: Last datetime that falls within the period or None if not found
    """
    now = datetime.now()

    # If current time is in period, return it
    if inPeriod(period, now):
        return now
        
    # For year-based periods, check directly for past years
    if 'year{' in period.lower() or 'yr{' in period.lower():
        # Extract year values from the period string
        years = []
        for match in re.finditer(r'(?:year|yr)\{(\d+(?:-\d+)?)\}', period.lower()):
            year_str = match.group(1)
            if '-' in year_str:
                start, end = map(int, year_str.split('-'))
                years.extend(range(start, end + 1))
            else:
                years.append(int(year_str))
                
        # Find the largest past year
        past_years = [y for y in years if y < now.year]
        if past_years:
            # Create a new datetime for Dec 31st of the past year
            last_year = max(past_years)
            return datetime(last_year, 12, 31, 23, 59, 59)
    
    # For weekday-based periods, use a more direct approach first
    if 'wd{' in period.lower() or 'wday{' in period.lower():
        # Check each of the past 7 days
        for i in range(1, 8):
            prev_time = now - timedelta(days=i)
            if inPeriod(period, prev_time):
                # Find the latest hour that matches in this day
                day_start = prev_time.replace(hour=0, minute=0, second=0, microsecond=0)
                for hour in range(23, -1, -1):
                    check_time = day_start + timedelta(hours=hour)
                    if inPeriod(period, check_time):
                        return check_time
                # If no specific hour matches, use the original time
                return prev_time
    
    # Search backward in time with increasingly larger steps
    # First try previous 24 hours with 1-hour increments
    for i in range(1, 25):
        prev_time = now - timedelta(hours=i)
        if inPeriod(period, prev_time):
            return prev_time
    
    # Try previous 7 days with 3-hour increments
    for i in range(8, 7*8+1, 3):  # 8 to 56 hours in steps of 3
        prev_time = now - timedelta(hours=i)
        if inPeriod(period, prev_time):
            # Now find more precise time by checking each hour in this day
            day_start = prev_time.replace(hour=0, minute=0, second=0, microsecond=0)
            # Check hours in reverse to find the latest matching time in the day
            for hour in range(23, -1, -1):
                check_time = day_start + timedelta(hours=hour)
                if inPeriod(period, check_time):
                    return check_time
            # Fallback to the original time if hour-by-hour search fails
            return prev_time
    
    # Try previous 30 days with 1-day increments
    for i in range(8, 31):
        prev_time = now - timedelta(days=i)
        if inPeriod(period, prev_time):
            # Find more precise time by checking each hour in this day
            day_start = prev_time.replace(hour=0, minute=0, second=0, microsecond=0)
            # Check hours in reverse to find the latest matching time in the day
            for hour in range(23, -1, -1):
                check_time = day_start + timedelta(hours=hour)
                if inPeriod(period, check_time):
                    return check_time
            # Fallback to the original time if hour-by-hour search fails
            return prev_time
    
    # Try previous 365 days with 7-day increments first, then refine
    for i in range(31, 366, 7):
        prev_time = now - timedelta(days=i)
        if inPeriod(period, prev_time):
            # When we find a match, check each day in this week (in reverse)
            week_start = prev_time - timedelta(days=prev_time.weekday())
            for day in range(6, -1, -1):
                check_date = week_start + timedelta(days=day)
                if inPeriod(period, check_date):
                    # Find more precise time by checking each hour in this day
                    day_start = check_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    for hour in range(23, -1, -1):
                        check_time = day_start + timedelta(hours=hour)
                        if inPeriod(period, check_time):
                            return check_time
                    # Fallback to the day with hour=23 if hour-by-hour search fails
                    return check_date.replace(hour=23, minute=59, second=59)
            # Fallback to the original time if day-by-day search fails
            return prev_time
    
    # For longer-term past periods, check up to 100 years in the past (if we're looking for specific years)
    for year_offset in range(2, 101):
        if now.year - year_offset > 0:  # Avoid negative years
            test_date = now.replace(year=now.year - year_offset, month=12, day=31, hour=23, minute=59, second=59)
            if inPeriod(period, test_date):
                return test_date
    
    # If no match found, return None
    return None

def inPeriod(period, dt=None):
    """
    Determines if a datetime is within a certain time period. If the time
    is omitted the current time will be used.

    inPeriod returns 1 if the datetime is within the time period, 0 if not.
    If the expression is malformed a TimePeriod.InvalidFormat exception
    will be raised. (Note that this differs from Time::Period, which
    returns -1 if the expression is invalid).

    The format for the time period is like Perl's Time::Period module,
    which is documented in some detail here:

    http://search.cpan.org/~pryan/Period-1.20/Period.pm

    Here's the quick and dirty version.

    Each period is composed of one or more sub-period seperated by a comma.
    A datetime must match at least one of the sub periods to be considered
    in that time period.

    Each sub-period is composed of one or more tests, like so:

        scale {value}

        scale {a-b}

        scale {a b c}

    The datetime must pass each test for a sub-period for the sub-period to
    be considered true.

    For example:

        Match Mondays
        wd {mon}

        Match Monday mornings
        wd {mon} hr {midnight-noon}

        Match Monday morning or Friday afternoon
        wd {mon} hr {midnight-noon}, wd {fri} hr {noon-midnight}

    Valid scales are:
        year
        month
        week
        yday 
        mday
        wday
        hour
        minute
        second

    Those can be substituted with their corresponding code:
        yd
        mo
        wk
        yd
        md
        wd
        hr
        min
        sec
    """
    if dt is None:
        dt = datetime.now()

    # transform whatever crazy format we're given and turn it into
    # something like this:
    # 
    # md{1}|hr{midnight-noon},md{2}|hr{noon-midnight}
    period = re.sub(r"^\s*|\s*$", "", period)
    period = re.sub(r"\s*(?={|$)", "", period)
    period = re.sub(r",\s*", ",", period)
    period = re.sub(r"\s*-\s*", "-", period)
    period = re.sub(r"{\s*", "{", period)
    period = re.sub(r"\s*}\s*", "}", period)
    period = re.sub(r"}(?=[^,])", "}|", period)
    period = period.lower()

    if period == "":
        return 1

    sub_periods = re.split(",", period)

    # go through each sub-period until one matches (OR logic)
    for sp in sub_periods:
        if _is_in_sub_period(sp, dt):
            return 1

    return 0

def _is_in_sub_period(sp, dt):
    if sp == "never" or sp == "none":
        return 0
    if sp == "always" or sp == "":
        return 1
    
    scales = sp.split("|")
    range_lists = {}

    # build a list for every scale of ranges
    for scale_exp in scales:
        scale, ranges = _parse_scale(scale_exp)

        # if there's already a list for this scale, add the new ranges to the end
        if scale in range_lists:
            range_lists[scale] += ranges
        else:
            range_lists[scale] = ranges

    # check each scale, if there's a false one return false (AND logic)
    for scale in range_lists:
        result = SCALES[scale](range_lists[scale], dt)
        if result != 1:
            return result

    return 1

def _parse_scale(scale_exp):
    """Parses a scale expression and returns the scale, and a list of ranges."""

    m = re.search(r"(\w+?)\{(.*?)\}", scale_exp)
    if m is None:
        raise InvalidFormat("Unable to parse the given time period.")
    scale = m.group(1)
    range_str = m.group(2)

    if scale not in SCALES:
        raise InvalidFormat(f"{scale} is not a valid scale.")

    ranges = re.split(r"\s", range_str)

    return scale, ranges

def yr(ranges, dt):
    def normal_year(year, dt):
        if year is None:
            return year

        try:
            year = int(year)
        except ValueError:
            raise InvalidFormat("An integer value is required for year.")

        if year < 100:
            century = dt.year // 100
            year = (100 * century) + year

        return year

    for range_str in ranges:
        low, high = _splitrange(range_str)
        low = normal_year(low, dt)
        high = normal_year(high, dt)
        
        # reverse the numbers if the first number is higher than the second
        # (e.g. 2015-2010)
        if high is not None and low > high:
            low, high = high, low

        if _is_in_range(dt.year, low, high):
            return 1

    return 0

def mo(ranges, dt):
    for range_str in ranges:
        # Convert month names to numbers
        for month in MONTHS.keys():
            range_str = re.sub(r"%s.*?(?=\s|-|$)" % (month), str(MONTHS[month]), range_str)

        low, high = _splitrange(range_str)
        low, high = _in_min_max(low, high, 1, 12, "month")

        if _is_in_range(dt.month, low, high):
            return 1

    return 0

def wk(ranges, dt):
    # Calculate the week number. This is essentially the number of Sunday's
    # that have passed.
    week = 1
    for day in range(1, dt.day + 1):
        if (day != 1 and calendar.weekday(dt.year, dt.month, day) == 6):
            week += 1

    return _simple_test(week, ranges, 1, 6, "week")

def yd(ranges, dt):
    today = int(dt.strftime("%j"))
    return _simple_test(today, ranges, 1, 366, "year day")

def md(ranges, dt):
    return _simple_test(dt.day, ranges, 1, 31, "day")

def wd(ranges, dt):
    # Convert Python's weekday (0-6, Mon-Sun) to our format (1-7, Sun-Sat)
    # Python: 0=Monday, 1=Tuesday, ..., 6=Sunday
    # Our format: 1=Sunday, 2=Monday, ..., 7=Saturday
    python_weekday = dt.weekday()
    # Transform: Sunday (6 in Python) becomes 1, Monday (0) becomes 2, etc.
    today = 1 if python_weekday == 6 else python_weekday + 2

    for range_str in ranges:
        # translate day names into numbers
        for day in DAYS.keys():
            range_str = re.sub(r"%s.*?(?=\s|-|$)" % (day), str(DAYS[day]), range_str)

        low, high = _splitrange(range_str)
        low, high = _in_min_max(low, high, 1, 7, "weekday")

        if _is_in_range(today, low, high):
            return 1
    return 0

def hr(ranges, dt):
    now = dt.hour

    def normal_hour(hour):
        if hour is None:
            return None
        try:
            if isinstance(hour, str) and hour.endswith("am"):
                hour = int(hour[:-2])
                if hour > 12:
                    # things like 13am would actually work, but since it's
                    # invalid we're clinging to our sensibilities and throwing
                    # it out
                    raise InvalidFormat(f"{hour}am is an invalid value for hour.")
                elif hour == 12:    # 12am is midnight
                    hour = 0
            elif isinstance(hour, str) and hour.endswith("pm"):
                hour = int(hour[:-2])
                if hour != 12:      # 12pm is noon
                    hour += 12
            elif hour == "12noon" or hour == "noon":
                hour = 12
            elif hour == "12midnight" or hour == "midnight":
                hour = 0
            else:
                hour = int(hour)
        except ValueError:
            raise InvalidFormat("An integer value is required for hour.")

        return hour

    for range_str in ranges:
        low, high = _splitrange(range_str)    
        low = normal_hour(low)
        high = normal_hour(high)

        low, high = _in_min_max(low, high, 0, 23, "hour")
        if _is_in_range(now, low, high):
            return 1

    return 0

def min_func(ranges, dt):
    return _simple_test(dt.minute, ranges, 0, 59, "minute")

def sec_func(ranges, dt):
    return _simple_test(dt.second, ranges, 0, 59, "second")

def _simple_test(now_val, ranges, min_val, max_val, scale):
    for range_str in ranges:
        low, high = _splitrange(range_str)
        low, high = _in_min_max(low, high, min_val, max_val, scale)

        if _is_in_range(now_val, low, high):
            return 1

    return 0

def _splitrange(range_str):
    if range_str == "":
        return None, None

    lowhigh = range_str.split("-")
    low = lowhigh[0]
    high = None
    if len(lowhigh) > 1:
        high = lowhigh[1]

    return low, high

def _in_min_max(low, high, min_val, max_val, scale):
    if low is None:
        return low, high

    try:
        low = int(low)
    except ValueError:
        raise InvalidFormat(f"An integer value is required for {scale}.")

    if low < min_val or low > max_val:
        raise InvalidFormat(f"{low} is not valid for {scale}. Valid options are between {min_val} and {max_val}.")
    
    if high is not None:
        try:
            high = int(high)
        except ValueError:
            raise InvalidFormat(f"An integer value is required for {scale}.")

        if high < min_val or high > max_val:
            raise InvalidFormat(f"{high} is not valid for {scale}. Valid options are between {min_val} and {max_val}.")

    return low, high

def _is_in_range(x, low, high):
    if low is None and high is None:
        # empty range, never matches
        return 0

    if high is None or low == high:
        # just one number
        if low != x:
            return 0
    elif high > low:  # e.g. mon-fri
        if x > high or x < low:
            return 0
    elif low > high:  # e.g. fri-mon
        if not (x >= low or x <= high):
            return 0

    return 1

class InvalidFormat(Exception):
    """Exception raised when the time period format is invalid."""
    pass

# dict of scale codes with the functions to process them
SCALES = {
    'yr': yr, 'year': yr,
    'mo': mo, 'month': mo,
    'wk': wk, 'week': wk,
    'yd': yd, 'yday': yd,
    'md': md, 'mday': md,
    'wd': wd, 'wday': wd,
    'hr': hr, 'hour': hr,
    'min': min_func, 'minute': min_func,
    'sec': sec_func, 'second': sec_func,
}

if __name__ == "__main__":
    import sys
    try:
        if len(sys.argv) == 2:
            # Simple usage: check if current time is in period
            period = sys.argv[1]
            result = inPeriod(period)
            print(f"Current time is {'in' if result else 'not in'} period: {period}")
        elif len(sys.argv) == 3:
            # Check if specific epoch time is in period
            epoch = int(sys.argv[1])
            period = sys.argv[2]
            result = inPeriod(period, datetime.fromtimestamp(epoch))
            print(f"Time {datetime.fromtimestamp(epoch)} is {'in' if result else 'not in'} period: {period}")
        else:
            print("Usage: python3 time_period.py [epoch] period")
            print("Examples:")
            print("  python3 time_period.py 'wd {mon-fri} hr {9-17}'")
            print("  python3 time_period.py 1621324800 'wd {mon-fri} hr {9-17}'")
    except InvalidFormat as ife:
        print(f"Invalid time period format: {ife}")
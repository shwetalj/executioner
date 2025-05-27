from contextlib import contextmanager

@contextmanager
def handle_config_errors(logger, exit_on_error=True):
    try:
        yield
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Configuration error: {e}")
        if exit_on_error:
            import sys
            sys.exit(1)
        else:
            raise 
# Example custom dependency plugin for Executioner

class CustomDependencyPlugin:
    """
    A simple custom dependency plugin that always returns True.
    Replace logic as needed for your use case.
    """
    def __init__(self, params=None):
        self.params = params or {}

    def check(self):
        # Custom logic goes here. For now, always succeed.
        print(f"[CustomDependencyPlugin] Checking with params: {self.params}")
        return True

# Plugin registration (if required by your plugin loader)
PLUGIN_CLASS = CustomDependencyPlugin 
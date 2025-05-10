import os

class DependencyManager:
    def __init__(self, jobs, logger, dependency_plugins=None):
        self.jobs = jobs
        self.logger = logger
        self.dependency_plugins = dependency_plugins or []
        self.dependencies = {
            job["id"]: frozenset(job.get("dependencies", [])) for job in jobs.values()
        }
        self.dependency_resolvers = {}
        # if self.dependency_plugins:
        #     self.logger.info(f"Found {len(self.dependency_plugins)} dependency plugins to load")

    def load_dependency_plugins(self):
        import importlib.util
        try:
            for entry in self.dependency_plugins:
                # Support both dict (new) and string (legacy)
                if isinstance(entry, dict):
                    plugin_path = entry.get('path')
                    plugin_name = entry.get('name')
                else:
                    plugin_path = entry
                    plugin_name = os.path.splitext(os.path.basename(plugin_path))[0]
                self.logger.info(f"Loading dependency plugin: name={plugin_name}, path={plugin_path}")
                if not os.path.exists(plugin_path):
                    self.logger.error(f"Dependency plugin file not found: {plugin_path}")
                    continue
                try:
                    spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
                    if not spec or not spec.loader:
                        self.logger.error(f"Could not load spec for plugin: {plugin_path}")
                        continue
                    plugin = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(plugin)
                    # Support both DependencyResolver._resolvers and PLUGIN_CLASS convention
                    if hasattr(plugin, 'DependencyResolver') and hasattr(plugin.DependencyResolver, '_resolvers'):
                        self.logger.info(f"Successfully loaded dependency plugin with {len(plugin.DependencyResolver._resolvers)} resolvers")
                        self.dependency_resolvers.update(plugin.DependencyResolver._resolvers)
                    elif hasattr(plugin, 'PLUGIN_CLASS'):
                        self.logger.info(f"Successfully loaded plugin class '{plugin.PLUGIN_CLASS.__name__}' for {plugin_name}")
                        self.dependency_resolvers[plugin_name] = plugin.PLUGIN_CLASS
                    else:
                        self.logger.warning(f"Plugin {plugin_path} does not contain expected DependencyResolver class or PLUGIN_CLASS")
                except Exception as e:
                    self.logger.error(f"Error loading dependency plugin {plugin_path}: {e}")
        except Exception as e:
            self.logger.error(f"General error in dependency plugin loading: {e}")

    def has_circular_dependencies(self):
        def dfs(node, visited, recursion_stack, path=None):
            if path is None:
                path = []
            visited.add(node)
            recursion_stack.add(node)
            path = path + [node]
            for neighbor in self.dependencies.get(node, set()):
                if neighbor not in self.jobs:
                    self.logger.warning(f"Job '{node}' depends on '{neighbor}' which doesn't exist")
                    continue
                if neighbor not in visited:
                    if dfs(neighbor, visited, recursion_stack, path):
                        return True
                elif neighbor in recursion_stack:
                    cycle_path = path + [neighbor]
                    self.logger.error(f"Circular dependency detected: {' -> '.join(cycle_path)}")
                    return True
            recursion_stack.remove(node)
            return False
        visited = set()
        recursion_stack = set()
        for job_id in self.jobs:
            if job_id not in visited:
                if dfs(job_id, visited, recursion_stack):
                    return True
        return False

    def check_missing_dependencies(self):
        result = {}
        for job_id, deps in self.dependencies.items():
            missing = [dep for dep in deps if dep not in self.jobs]
            if missing:
                result[job_id] = missing
        return result

    def get_execution_order(self):
        order = []
        visited = set()
        temp_visited = set()
        def visit(node):
            if node in temp_visited or node in visited:
                return
            temp_visited.add(node)
            for dep in self.dependencies.get(node, []):
                if dep in self.jobs:
                    visit(dep)
            temp_visited.remove(node)
            visited.add(node)
            order.append(node)
        for job_id in self.jobs:
            if job_id not in visited:
                visit(job_id)
        return order 
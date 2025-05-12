import shlex
import os
import re
from typing import Tuple, Dict

def validate_command(command: str, job_id: str, job_logger, config) -> Tuple[bool, str]:
    if not command or not command.strip():
        return True, ""
    security_policy = config.get("security_policy", "warn")
    security_level = config.get("security_level", "medium")
    command_whitelist = config.get("command_whitelist", [])
    if command_whitelist:
        normalized_cmd = command.strip().split()[0] if command.strip() else ""
        if normalized_cmd in command_whitelist:
            job_logger.info(f"Command '{normalized_cmd}' is in the whitelist")
            return True, ""
    workspace_paths = config.get("workspace_paths", [])
    try:
        tokens = shlex.split(command)
        if tokens:
            binary_name = tokens[0]
            if workspace_paths and binary_name.startswith('/'):
                is_allowed_path = any(binary_name.startswith(path) for path in workspace_paths)
                if not is_allowed_path:
                    reason = f"Command binary path outside of allowed workspace: {binary_name}"
                    job_logger.warning(reason)
                    if security_policy == "block" or security_level == "high":
                        return False, reason
            for arg in tokens[1:]:
                if '../' in arg or arg.startswith('..'):
                    reason = f"Suspicious path traversal detected in argument: {arg}"
                    job_logger.warning(reason)
                    if security_policy == "block" or security_level == "high":
                        return False, reason
                sensitive_files = ['/etc/passwd', '/etc/shadow', '/.ssh/', '/id_rsa', '/id_dsa',
                                 '/authorized_keys', '/known_hosts', '/.aws/', '/.config/', '/credentials']
                for sensitive in sensitive_files:
                    if sensitive in arg:
                        reason = f"Command appears to access sensitive file: {arg}"
                        job_logger.warning(reason)
                        if security_policy == "block" or security_level == "high":
                            return False, reason
    except ValueError as e:
        job_logger.warning(f"Command parsing failed: {e} - treating with caution")
    critical_patterns = [
        (r'`.*`', "Backtick command substitution"),
        (r'\$\(.*\)', "$() command substitution"),
        (r'>\s*/etc/(\w+)', "Writing to /etc files"),
        (r'>\s*/proc/(\w+)', "Writing to /proc"),
        (r'>\s*/sys/(\w+)', "Writing to /sys"),
        (r'[\s < /dev/null | &;]\s*rm\s+-rf\s+/', "Delete root directory"),
        (r'[\s|&;]\s*rm\s+-rf\s+[~.]', "Delete home or current directory"),
        (r'[\s|&;]\s*for\b.*\bdo\b.*\brm\b', "Loop for deletion"),
        (r'\b(sudo|su|doas)\b', "Privilege escalation"),
        (r'>\s*/dev/(sd|hd|xvd|nvme|fd|loop)', "Writing to raw devices"),
        (r'\beval\b.*\$', "Eval with variables is extremely dangerous"),
        (r'[\s|&;]\s*nc\s+.*\s+\-e\s+', "Netcat with program execution"),
        (r'[\s|&;]\s*(shutdown|reboot|halt|poweroff)\b', "System power commands"),
        (r'[\s|&;]\s*dd\s+.*\s+of=/dev/', "Writing to devices with dd"),
        (r'\b(curl|wget)\b.*\|\s*(bash|sh)\b', "Piping web content directly to shell")
    ]
    medium_patterns = [
        (r'[;&\|]\s*rm\s+[-/]', "Dangerous rm commands"),
        (r'[;&\|]\s*rm\s+.*\s+[~/]', "rm targeting home or root"),
        (r'[;&\|]\s*mv\s+[^\s]+\s+/', "Moving to root"),
        (r'[;&\|]\s*find\s+.*\s+(-exec\s+rm|\-delete)', "Find with delete"),
        (r'[;&\|]\s*shred\b', "File secure deletion"),
        (r'[;&\|]\s*chmod\s+([0-7])?777\b', "Overly permissive chmod"),
        (r'[;&\|]\s*chmod\s+\-R\s+.*\s+[~/]', "Recursive chmod from sensitive locations"),
        (r'[;&\|]\s*chown\s+\-R\s+.*\s+[~/]', "Recursive chown"),
        (r'\beval\b', "Eval is dangerous"),
        (r'\bexec\b\s*[^=]', "Exec (when not appearing in assignment)"),
        (r'\bsocat\b.*exec', "Socat with execution"),
        (r'[;&\|]\s*mkfs\b', "Filesystem creation"),
        (r'[;&\|]\s*mount\b', "Mounting filesystems")
    ]
    high_patterns = [
        (r'[;&\|]\s*truncate\s+.*\s+[~/]', "Truncate files in sensitive locations"),
        (r'[;&\|]\s*sed\s+.*\s+-i\s+.*\s+[~/]', "Sed in-place editing of sensitive files"),
        (r'\benv\b.*PATH=', "PATH manipulation"),
        (r'\bwget\b.*\s+-O\s+[~/]', "Overwriting files with wget"),
        (r'\bcurl\b.*\s+-o\s+[~/]', "Overwriting files with curl"),
        (r'\bnohup\b', "Background processes with nohup"),
        (r'\bscp\b.*\s+-r\b', "Recursive SCP"),
        (r'\brsync\b.*\s+--delete\b', "Rsync with delete"),
        (r'\bat\b', "Scheduled tasks"),
        (r'\bcrontab\b', "Cron manipulation"),
        (r'\biptables\b', "Firewall manipulation"),
        (r'\broute\b', "Network routing"),
        (r'\bsystemctl\b', "Service control"),
        (r'\bjournalctl\b', "Log access"),
        (r'\buseradd\b', "User management"),
        (r'\busermod\b', "User modification"),
        (r'\bchpasswd\b', "Password changing")
    ]
    allowlist_patterns = config.get("command_allowlist_patterns", [])
    for allow_pattern in allowlist_patterns:
        if re.search(allow_pattern, command, re.IGNORECASE):
            job_logger.info(f"Command matched allowlist pattern: {allow_pattern}")
            return True, ""
    for pattern, description in critical_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            reason = f"Critical security violation: {description}"
            job_logger.error(reason)
            return False, reason
    check_patterns = []
    if security_level in ("medium", "high"):
        check_patterns.extend(medium_patterns)
    if security_level == "high":
        check_patterns.extend(high_patterns)
    for pattern, description in check_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            reason = f"Potentially unsafe operation: {description}"
            job_logger.warning(reason)
            if security_policy == "block":
                return False, reason
            return True, reason
    return True, ""

def parse_command(command: str, logger) -> Dict:
    if not command or not command.strip():
        return {'args': [], 'needs_shell': False}
    shell_indicators = {
        '|': 'pipe', '&': 'background execution', ';': 'command separator', '<': 'input redirection', '>': 'output redirection', '>>': 'append redirection', '{': 'brace expansion', '}': 'brace expansion', '[': 'glob pattern', ']': 'glob pattern', '$': 'variable expansion', '`': 'command substitution', '\\': 'escape character', '&&': 'conditional execution', '||': 'conditional execution', '2>': 'stderr redirection', '2>&1': 'stderr to stdout redirection', '*': 'wildcard expansion', '?': 'single character wildcard', '~': 'home directory expansion'
    }
    shell_commands = [
        'grep', 'awk', 'sed', 'find', 'xargs', 'for ', 'while ', 'if ', 'case ', 'do ', 'done', 'until ', 'function ', 'alias ', 'source ', './'
    ]
    for indicator, reason in shell_indicators.items():
        if indicator in command:
            return {
                'needs_shell': True,
                'shell_reason': f"Command uses shell feature: {reason} ({indicator})",
                'original_command': command
            }
    for cmd in shell_commands:
        if command.startswith(cmd) or f" {cmd}" in command:
            return {
                'needs_shell': True,
                'shell_reason': f"Command uses shell command: {cmd}",
                'original_command': command
            }
    try:
        args = shlex.split(command)
        if not args:
            logger.warning("Command parsed to empty argument list")
            return {'args': [], 'needs_shell': False}
        cmd_name = args[0]
        if '/' in cmd_name:
            if not os.path.isfile(cmd_name) or not os.access(cmd_name, os.X_OK):
                if not any(os.path.isfile(os.path.join(path, cmd_name.split('/')[-1])) 
                          for path in os.environ.get('PATH', '').split(os.pathsep) if path):
                    logger.warning(f"Command {cmd_name} not found or not executable")
                    return {
                        'needs_shell': True,
                        'shell_reason': f"Command path not directly executable: {cmd_name}",
                        'original_command': command
                    }
        return {
            'args': args,
            'needs_shell': False,
            'original_command': command
        }
    except ValueError as e:
        logger.warning(f"Command parsing error: {e}")
        return {
            'needs_shell': True,
            'shell_reason': f"Command parsing error: {e}",
            'original_command': command
        }
    except Exception as e:
        logger.warning(f"Unexpected error parsing command: {e}")
        return {
            'needs_shell': True,
            'shell_reason': f"Command parsing error: {e}",
            'original_command': command
        } 
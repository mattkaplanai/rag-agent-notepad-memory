"""ANSI color codes for colored docker log output."""

C = "\033[36m"    # Cyan   — agent labels / start
G = "\033[32m"    # Green  — success
R = "\033[31m"    # Red    — error / blocked
Y = "\033[33m"    # Yellow — partial / warning / miss
W = "\033[1;37m"  # Bold white — headers
B = "\033[34m"    # Blue   — info
M = "\033[35m"    # Magenta — tool calls
X = "\033[0m"     # Reset

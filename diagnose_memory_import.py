import os
import sys

print(f"CWD: {os.getcwd()}")
print(f"sys.path: {sys.path}")

try:
    import database
    print(f"database imported: {database}")
    print(f"database package: {database.__package__}")
    print(f"database path: {database.__path__}")
except Exception as e:
    print(f"Failed to import database: {e}")

try:
    print("Successfully imported agents.memory.main")
except Exception as e:
    print(f"Failed to import agents.memory.main: {e}")
    import traceback
    traceback.print_exc()


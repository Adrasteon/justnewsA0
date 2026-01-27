import re

# Read the file
with open('monitoring/core/trace_collector.py') as f:
    content = f.read()

# Replace the trace_count counter method call
content = re.sub(
    r'self\.trace_count = self\.metrics\.create_counter\(\s*"traces_total",\s*"Total number of traces processed",\s*\[\"status\"\],\s*\)',
    'self.trace_count = self.metrics._get_or_create_counter("traces_total")',
    content
)

# Write the file back
with open('monitoring/core/trace_collector.py', 'w') as f:
    f.write(content)

print('TraceCollector trace_count counter method call has been fixed')

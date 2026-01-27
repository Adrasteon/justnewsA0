
# Define the file path
file_path = '/a0/justnewsA0/agents/dashboard/dashboard_engine.py'

# Read the file content
with open(file_path) as file:
    content = file.read()

# Replace the deprecated .model_dump() with .model_dump()
content = content.replace('.model_dump()', '.model_dump()')

# Write the modified content back to the file
with open(file_path, 'w') as file:
    file.write(content)

print('File has been updated successfully.')

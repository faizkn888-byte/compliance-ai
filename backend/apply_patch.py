import sys

# Read current main.py
with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add import re
if 'import re' not in content:
    content = content.replace('import io\n', 'import io\nimport re\n')

# 2. Bump version
content = content.replace('version="0.4.1"', 'version="0.5.0"')

# 3. Read and append all patch parts
patch_parts = []
for i in range(1, 6):
    with open(f'backend_patch_part{i}.py', 'r', encoding='utf-8') as f:
        patch_parts.append(f.read())

# Find where REGULATIONS ends
reg_end = content.rfind('}\n\n# ============== HELPERS ==============')
if reg_end == -1:
    reg_end = content.rfind('}\n\n# ============== AUTH HELPERS')

# Insert data dictionaries after REGULATIONS
insert_point = reg_end + 1
data_dicts = '\n\n'.join(patch_parts[:4])  # parts 1-4 are data dicts + helpers
content = content[:insert_point] + '\n\n' + data_dicts + '\n\n' + content[insert_point:]

# 4. Modify analyze_text_smart
old_return = '''    return {
        "overall_score": score,
        "status": status,
        "breakdown": breakdown,
        "gaps": gaps,
        "passed": passed,
        "regulation_type": regulation_type
    }'''
new_return = '''    return {
        "overall_score": score,
        "status": status,
        "breakdown": breakdown,
        "gaps": gaps,
        "passed": passed,
        "regulation_type": regulation_type,
        "tech_stack": detect_tech_stack(text),
        "dark_patterns": detect_dark_patterns(text),
    }'''
content = content.replace(old_return, new_return)

# 5. Add routes before health_check
routes_code = patch_parts[4]  # part 5 has routes
content = content.replace('@app.get("/health")', routes_code + '\n\n@app.get("/health")')

# 6. Update health_check version
content = content.replace('return {"status": "ok", "version": "0.4.1"}', 'return {"status": "ok", "version": "0.5.0"}')

# Write back
with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch applied successfully!")
print("Backup your original main.py first next time!")
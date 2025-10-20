# .github/scripts/generate_redirects.py
import json
from jinja2 import Template
import os
import sys

repo_root = os.getenv('GITHUB_WORKSPACE')

config_file_path = os.path.join(repo_root, 'redirects.json')
template_file_path = os.path.join(repo_root, '_redirect_templates', 'redirect_template.html')

try:
    with open(config_file_path, 'r') as f:
        redirects_config = json.load(f)
except FileNotFoundError:
    print(f"Error: Configuration file not found at {config_file_path}", file=sys.stderr)
    sys.exit(1)
except json.JSONDecodeError:
    print(f"Error: Invalid JSON format in {config_file_path}", file=sys.stderr)
    sys.exit(1)

try:
    with open(template_file_path, 'r') as f:
        template_content = f.read()
    template = Template(template_content)
except FileNotFoundError:
    print(f"Error: Template file not found at {template_file_path}", file=sys.stderr)
    sys.exit(1)

generated_files = []
for entry in redirects_config:
    title = entry['title']
    target_url = entry['current_target_file']
    relative_redirect_html_path = entry['redirect_html_path']
    full_redirect_html_path = os.path.join(repo_root, relative_redirect_html_path)

    os.makedirs(os.path.dirname(full_redirect_html_path), exist_ok=True)

    rendered_html = template.render(title=title, target_url=target_url)
    with open(full_redirect_html_path, 'w') as f:
        f.write(rendered_html)
    print(f'Generated: {full_redirect_html_path}')
    generated_files.append(relative_redirect_html_path)

# --- CRITICAL CHANGE FOR GITHUB_OUTPUT AND file_pattern ---
github_output_path = os.getenv('GITHUB_OUTPUT')
if github_output_path:
    # Format generated_files as a comma-separated string, quoting paths with spaces
    # This is more robust for the 'file_pattern' input of git-auto-commit-action
    formatted_files_for_output = []
    for f_path in generated_files:
        if ' ' in f_path:
            # Use single quotes for paths with spaces
            formatted_files_for_output.append(f"'{f_path}'")
        else:
            formatted_files_for_output.append(f_path)

    output_string = ",".join(formatted_files_for_output)

    with open(github_output_path, 'a') as f:
        f.write(f"generated_files={output_string}\n")
else:
    print("Warning: GITHUB_OUTPUT environment variable not found. Output will not be set.", file=sys.stderr)

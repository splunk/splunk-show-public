# .github/scripts/generate_redirects.py
import json
from jinja2 import Template
import os
import sys

# Get repository root from environment variable set by GitHub Actions
# This ensures paths are relative to the repo root, regardless of where the action runs
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
    target_url = entry['current_target_file'] # Ensure this key matches your JSON
    relative_redirect_html_path = entry['redirect_html_path']
    full_redirect_html_path = os.path.join(repo_root, relative_redirect_html_path)

    # Ensure the directory exists before writing the file
    os.makedirs(os.path.dirname(full_redirect_html_path), exist_ok=True)

    rendered_html = template.render(title=title, target_url=target_url)
    with open(full_redirect_html_path, 'w') as f:
        f.write(rendered_html)
    print(f'Generated: {full_redirect_html_path}')
    generated_files.append(relative_redirect_html_path) # Store relative path for git-auto-commit

# --- NEW WAY TO SET OUTPUT ---
# Write the output to the file specified by $GITHUB_OUTPUT
# This replaces the deprecated '::set-output' command.
github_output_path = os.getenv('GITHUB_OUTPUT')
if github_output_path:
    with open(github_output_path, 'a') as f:
        f.write(f"generated_files={json.dumps(generated_files)}\n")
else:
    print("Warning: GITHUB_OUTPUT environment variable not found. Output will not be set.", file=sys.stderr)

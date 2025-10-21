# .github/scripts/generate_redirects.py
import json
from jinja2 import Template
import os
import sys
import urllib.parse # Import for robust URL encoding

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

# Define the base URL for your GitHub Pages site
# Make sure this matches your actual GitHub Pages URL structure
github_pages_base_url = "https://splunk.github.io/splunk-show-public/"

for entry in redirects_config:
    title = entry['title']
    target_url = entry['current_target_file']
    relative_redirect_html_path = entry['redirect_html_path']

    # --- Calculate the public_url here ---
    # Split the path, URL-encode each segment, then re-join
    # This correctly handles spaces and other special characters in path segments
    path_segments = relative_redirect_html_path.split('/')
    encoded_path_segments = [urllib.parse.quote(segment, safe='') for segment in path_segments]
    public_url_path_encoded = '/'.join(encoded_path_segments)
    public_url = github_pages_base_url + public_url_path_encoded
    # -------------------------------------

    full_redirect_html_path = os.path.join(repo_root, relative_redirect_html_path)

    os.makedirs(os.path.dirname(full_redirect_html_path), exist_ok=True)

    # Pass public_url to the template rendering context
    rendered_html = template.render(title=title, target_url=target_url, public_url=public_url)
    with open(full_redirect_html_path, 'w') as f:
        f.write(rendered_html)
    print(f'Generated: {full_redirect_html_path}')

# The GITHUB_OUTPUT part for git-auto-commit-action is handled by file_pattern: '.'
# so no changes needed here.

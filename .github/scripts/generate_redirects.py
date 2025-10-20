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

# Define the base URL for your GitHub Pages site
github_pages_base_url = "https://splunk.github.io/splunk-show-public/"

for entry in redirects_config:
    title = entry['title']
    target_url = entry['current_target_file']
    relative_redirect_html_path = entry['redirect_html_path']
    full_redirect_html_path = os.path.join(repo_root, relative_redirect_html_path)

    # Construct the public_url for the redirect HTML file itself
    # Replace spaces with %20 for URL compatibility
    # Note: urllib.parse.quote is more robust for general URL encoding,
    # but a simple replace is sufficient here as we only expect spaces.
    public_url_path_encoded = relative_redirect_html_path.replace(' ', '%20')
    public_url = github_pages_base_url + public_url_path_encoded

    os.makedirs(os.path.dirname(full_redirect_html_path), exist_ok=True)

    # Pass public_url to the template rendering context
    rendered_html = template.render(title=title, target_url=target_url, public_url=public_url)
    with open(full_redirect_html_path, 'w') as f:
        f.write(rendered_html)
    print(f'Generated: {full_redirect_html_path}')

# No changes needed for GITHUB_OUTPUT as per our last successful fix.

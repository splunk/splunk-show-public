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

github_pages_base_url = "https://splunk.github.io/splunk-show-public/"

updated_redirects_config = []

for entry in redirects_config:
    title = entry['title']
    raw_current_target_file = entry['current_target_file'] # Read the raw value with spaces
    relative_redirect_html_path = entry['redirect_html_path']

    # --- NEW: URL-encode raw_current_target_file for use in HTML ---
    # Parse the URL to correctly encode only the path and query components
    parsed_target_url = urllib.parse.urlparse(raw_current_target_file)
    encoded_target_path = urllib.parse.quote(parsed_target_url.path, safe='/') # Keep '/' unencoded
    encoded_target_query = urllib.parse.quote(parsed_target_url.query, safe='=&') # Keep '=' and '&' unencoded
    # Reconstruct the URL with encoded path and query
    target_url_for_html = urllib.parse.urlunparse(parsed_target_url._replace(path=encoded_target_path, query=encoded_target_query))
    # ---------------------------------------------------------------

    # Calculate the public_url (this logic remains the same and is correct)
    path_segments = relative_redirect_html_path.split('/')
    encoded_path_segments = [urllib.parse.quote(segment, safe='') for segment in path_segments]
    public_url_path_encoded = '/'.join(encoded_path_segments)
    calculated_public_url = github_pages_base_url + public_url_path_encoded

    # Add or update 'public_url' in the entry dictionary for redirects.json
    entry['public_url'] = calculated_public_url

    full_redirect_html_path = os.path.join(repo_root, relative_redirect_html_path)

    os.makedirs(os.path.dirname(full_redirect_html_path), exist_ok=True)

    # Pass the correctly encoded target_url_for_html and calculated public_url to the template
    rendered_html = template.render(title=title, target_url=target_url_for_html, public_url=calculated_public_url)
    with open(full_redirect_html_path, 'w') as f:
        f.write(rendered_html)
    print(f'Generated HTML: {full_redirect_html_path}')

    updated_redirects_config.append(entry)

try:
    with open(config_file_path, 'w') as f:
        json.dump(updated_redirects_config, f, indent=2)
    print(f'Updated redirects.json with public_url entries: {config_file_path}')
except Exception as e:
    print(f"Error writing updated redirects.json: {e}", file=sys.stderr)
    sys.exit(1)

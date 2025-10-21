# .github/scripts/auto_generate_redirects.py
import json
from jinja2 import Template
import os
import sys
import urllib.parse
import re # For regex cleaning

# --- Configuration ---
GITHUB_REPO_OWNER = 'splunk'
GITHUB_REPO_NAME = 'splunk-show-public'
GITHUB_PAGES_BASE_URL = f"https://{GITHUB_REPO_OWNER}.github.io/{GITHUB_REPO_NAME}/"

# Directories to scan for *any* files that you want to create redirects for
SCAN_DIRECTORIES = [
    "Workshops/Advanced Machine Learning - Extend Operational Insights",
    "Workshops/Threat Hunting APTs",
    # Add any other directories you want to auto-scan for files
]

# --- Helper Functions ---
def clean_filename_for_title(filename):
    """Removes file extensions and common date patterns, replaces underscores/hyphens with spaces."""
    name_without_ext = os.path.splitext(filename)[0] # Get name without extension
    # Remove common date patterns like " - Oct 2023" or " - 2023-10"
    name_without_ext = re.sub(r' - (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}', '', name_without_ext)
    name_without_ext = re.sub(r' - \d{4}-\d{2}(-\d{2})?', '', name_without_ext) # YYYY-MM(-DD)
    name_without_ext = name_without_ext.replace('-', ' ').replace('_', ' ')
    return name_without_ext.strip()

def slugify(text):
    """Converts text to a URL-friendly slug."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text) # Remove non-word chars
    text = re.sub(r'[\s_-]+', '-', text) # Replace spaces/underscores/dashes with single dash
    text = text.strip('-')
    return text

# --- Main Script Logic ---
repo_root = os.getenv('GITHUB_WORKSPACE')

config_file_path = os.path.join(repo_root, 'redirects.json')
template_file_path = os.path.join(repo_root, '_redirect_templates', 'redirect_template.html')

# Read existing redirects.json to preserve manual edits for 'id', 'title', and 'redirect_html_path'
# Key: current_target_file (the URL to the original file), Value: existing entry
existing_redirects_map = {}
try:
    with open(config_file_path, 'r') as f:
        existing_data = json.load(f)
        for entry in existing_data:
            # Ensure 'current_target_file' exists and use it as the key
            if 'current_target_file' in entry:
                existing_redirects_map[entry['current_target_file']] = entry
except FileNotFoundError:
    print("No existing redirects.json found. Starting fresh.", file=sys.stderr)
except json.JSONDecodeError:
    print("Invalid JSON format in existing redirects.json. Starting fresh.", file=sys.stderr)

# Read HTML template
try:
    with open(template_file_path, 'r') as f:
        template_content = f.read()
    template = Template(template_content)
except FileNotFoundError:
    print(f"Error: Template file not found at {template_file_path}", file=sys.stderr)
    sys.exit(1)

new_redirects_config_list = [] # This will be the final list of entries to write back

# --- Discover files and propose/update entries ---
for scan_dir in SCAN_DIRECTORIES:
    full_scan_dir_path = os.path.join(repo_root, scan_dir)
    if not os.path.isdir(full_scan_dir_path):
        print(f"Warning: Scan directory '{scan_dir}' not found. Skipping.", file=sys.stderr)
        continue

    for root, _, files in os.walk(full_scan_dir_path):
        for filename in files:
            # Skip hidden files and common Git/system files
            if filename.startswith('.') or filename in ['.gitkeep', 'Thumbs.db', 'desktop.ini']:
                continue

            # Relative path from repo root to the original file
            relative_original_file_path = os.path.relpath(os.path.join(root, filename), repo_root)
            # Ensure forward slashes for URL consistency
            relative_original_file_path = relative_original_file_path.replace(os.sep, '/')

            # Construct the full GitHub Pages URL to the original file (with spaces)
            # This will be used as the stable key for existing entries
            current_target_file_url_in_json = GITHUB_PAGES_BASE_URL + relative_original_file_path

            # --- Check for existing entry for this original file ---
            entry_to_process = existing_redirects_map.get(current_target_file_url_in_json, {})

            # Infer values
            inferred_title = clean_filename_for_title(filename)
            inferred_id = slugify(inferred_title)
            
            # Proposed redirect_html_path: same directory structure as original file,
            # but with a slugified name (without original extension) and .html extension.
            pdf_dir_relative = os.path.dirname(relative_original_file_path)
            inferred_redirect_html_path = os.path.join(pdf_dir_relative, slugify(os.path.splitext(filename)[0]) + '.html')
            inferred_redirect_html_path = inferred_redirect_html_path.replace(os.sep, '/') # Ensure forward slashes

            # --- Apply overrides from existing entry if present ---
            entry_id = entry_to_process.get('id', inferred_id)
            entry_title = entry_to_process.get('title', inferred_title)
            # THIS IS THE CRUCIAL OVERRIDE:
            entry_redirect_html_path = entry_to_process.get('redirect_html_path', inferred_redirect_html_path)

            # Create or update the entry
            new_entry = {
                "id": entry_id,
                "title": entry_title,
                "redirect_html_path": entry_redirect_html_path,
                "current_target_file": current_target_file_url_in_json # Always update to current URL
                # public_url will be calculated and added in the next stage
            }
            new_redirects_config_list.append(new_entry)

# --- Process the final list of redirects to generate HTML and update public_url ---
# This loop also ensures that redirects.json is written back with 'public_url'
final_redirects_config_for_writing = []
for entry in new_redirects_config_list:
    title = entry['title']
    raw_current_target_file = entry['current_target_file'] # This is the URL with spaces
    relative_redirect_html_path = entry['redirect_html_path'] # This is the potentially overridden path

    # URL-encode raw_current_target_file for use in HTML (path with spaces -> %20)
    parsed_target_url = urllib.parse.urlparse(raw_current_target_file)
    encoded_target_path = urllib.parse.quote(parsed_target_url.path, safe='/')
    encoded_target_query = urllib.parse.quote(parsed_target_url.query, safe='=&')
    target_url_for_html = urllib.parse.urlunparse(parsed_target_url._replace(path=encoded_target_path, query=encoded_target_query))

    # Calculate the public_url for the redirect HTML file itself (based on the chosen redirect_html_path)
    path_segments = relative_redirect_html_path.split('/')
    encoded_path_segments = [urllib.parse.quote(segment, safe='') for segment in path_segments]
    public_url_path_encoded = '/'.join(encoded_path_segments)
    calculated_public_url = GITHUB_PAGES_BASE_URL + public_url_path_encoded

    # Update 'public_url' in the entry dictionary for redirects.json
    entry['public_url'] = calculated_public_url

    full_redirect_html_path = os.path.join(repo_root, relative_redirect_html_path)

    os.makedirs(os.path.dirname(full_redirect_html_path), exist_ok=True)

    rendered_html = template.render(title=title, target_url=target_url_for_html, public_url=calculated_public_url)
    with open(full_redirect_html_path, 'w') as f:
        f.write(rendered_html)
    print(f'Generated HTML: {full_redirect_html_path}')

    final_redirects_config_for_writing.append(entry)

# Write the updated redirects_config back to redirects.json
try:
    with open(config_file_path, 'w') as f:
        json.dump(final_redirects_config_for_writing, f, indent=2)
    print(f'Updated redirects.json with public_url and discovered files: {config_file_path}')
except Exception as e:
    print(f"Error writing updated redirects.json: {e}", file=sys.stderr)
    sys.exit(1)

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
# !!! UPDATED: New base URL for content !!!
GITHUB_PAGES_BASE_URL = f"https://{GITHUB_REPO_OWNER}.github.io/{GITHUB_REPO_NAME}/public/"

# !!! UPDATED: The SINGLE ROOT directory where all your content now lives !!!
# This should be relative to your repository root.
ROOT_CONTENT_DIRECTORY = "public/Workshops" # Assuming Workshops is directly under public
# If all your content is directly under 'public' and 'Workshops' is just one of many top-level folders there,
# you might set ROOT_CONTENT_DIRECTORY = "public" and the script will scan everything under 'public'.
# For now, we'll assume 'Workshops' is the main content folder within 'public'.

# --- Helper Functions (No changes needed) ---
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
    text = text.lower() # Ensure slug is always lowercase for consistency
    text = re.sub(r'[^\w\s-]', '', text) # Remove non-word chars
    text = re.sub(r'[\s_-]+', '-', text) # Replace spaces/underscores/dashes with single dash
    text = text.strip('-')
    return text

# --- Main Script Logic (No functional changes, just updated comments/context) ---
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
            else:
                print(f"Warning: Entry missing 'current_target_file' in redirects.json: {entry}. Skipping for merge.", file=sys.stderr)
except FileNotFoundError:
    print("No existing redirects.json found. Starting fresh.", file=sys.stderr)
except json.JSONDecodeError:
    print("Invalid JSON format in existing redirects.json. It might be overwritten. Error:", file=sys.stderr)
    existing_redirects_map = {}


# Read HTML template
try:
    with open(template_file_path, 'r') as f:
        template_content = f.read()
    template = Template(template_content)
except FileNotFoundError:
    print(f"Error: Template file not found at {template_file_path}. Exiting.", file=sys.stderr)
    sys.exit(1)

final_redirects_config_for_writing = []
discovered_original_file_urls = set()

full_root_content_path = os.path.join(repo_root, ROOT_CONTENT_DIRECTORY)
if not os.path.isdir(full_root_content_path):
    print(f"Error: ROOT_CONTENT_DIRECTORY '{ROOT_CONTENT_DIRECTORY}' not found at '{full_root_content_path}'. No files will be scanned. Exiting.", file=sys.stderr)
    sys.exit(1)

print(f"Starting recursive file discovery in '{full_root_content_path}'")

for root, _, files in os.walk(full_root_content_path):
    for filename in files:
        if filename.startswith('.') or filename in ['.gitkeep', 'Thumbs.db', 'desktop.ini']:
            continue

        relative_original_file_path = os.path.relpath(os.path.join(root, filename), repo_root)
        relative_original_file_path = relative_original_file_path.replace(os.sep, '/')

        current_target_file_url_in_json = GITHUB_PAGES_BASE_URL + relative_original_file_path
        
        discovered_original_file_urls.add(current_target_file_url_in_json)

        entry_to_process = existing_redirects_map.get(current_target_file_url_in_json, {}).copy()

        inferred_title = clean_filename_for_title(filename)
        inferred_id = slugify(inferred_title)
        
        pdf_dir_relative = os.path.dirname(relative_original_file_path)
        inferred_redirect_html_path = os.path.join(pdf_dir_relative, slugify(os.path.splitext(filename)[0]) + '.html')
        inferred_redirect_html_path = inferred_redirect_html_path.replace(os.sep, '/')

        entry_id = entry_to_process.get('id', inferred_id)
        entry_title = entry_to_process.get('title', inferred_title)
        entry_redirect_html_path = entry_to_process.get('redirect_html_path', inferred_redirect_html_path)

        new_entry = {
            "id": entry_id,
            "title": entry_title,
            "redirect_html_path": entry_redirect_html_path,
            "current_target_file": current_target_file_url_in_json
        }
        final_redirects_config_for_writing.append(new_entry)
        print(f"Processed file: {relative_original_file_path} -> Redirect: {entry_redirect_html_path}")

final_list_after_html_gen = []
generated_html_files = set()

for entry in final_redirects_config_for_writing:
    title = entry['title']
    raw_current_target_file = entry['current_target_file']
    relative_redirect_html_path = entry['redirect_html_path']

    parsed_target_url = urllib.parse.urlparse(raw_current_target_file)
    encoded_target_path = urllib.parse.quote(parsed_target_url.path, safe='/')
    encoded_target_query = urllib.parse.quote(parsed_target_url.query, safe='=&')
    target_url_for_html = urllib.parse.urlunparse(parsed_target_url._replace(path=encoded_target_path, query=encoded_target_query))

    path_segments = relative_redirect_html_path.split('/')
    encoded_path_segments = [urllib.parse.quote(segment, safe='') for segment in path_segments]
    public_url_path_encoded = '/'.join(encoded_path_segments)
    calculated_public_url = GITHUB_PAGES_BASE_URL + public_url_path_encoded

    entry['public_url'] = calculated_public_url

    full_redirect_html_path = os.path.join(repo_root, relative_redirect_html_path)

    os.makedirs(os.path.dirname(full_redirect_html_path), exist_ok=True)

    rendered_html = template.render(title=title, target_url=target_url_for_html, public_url=calculated_public_url)
    with open(full_redirect_html_path, 'w') as f:
        f.write(rendered_html)
    print(f'Generated HTML: {full_redirect_html_path}')
    generated_html_files.add(full_redirect_html_path)
    final_list_after_html_gen.append(entry)

print("Cleaning up old HTML redirect files...")
# Scan only the ROOT_CONTENT_DIRECTORY for HTML files
# This needs to be relative to repo_root for os.walk to work correctly
full_root_content_path_for_cleanup = os.path.join(repo_root, ROOT_CONTENT_DIRECTORY)
if os.path.isdir(full_root_content_path_for_cleanup):
    for root, _, files in os.walk(full_root_content_path_for_cleanup):
        for filename in files:
            if filename.lower().endswith('.html'):
                full_html_path = os.path.join(root, filename)
                if full_html_path not in generated_html_files:
                    os.remove(full_html_path)
                    print(f"Deleted old HTML redirect: {full_html_path}")
else:
    print(f"Warning: ROOT_CONTENT_DIRECTORY '{ROOT_CONTENT_DIRECTORY}' not found for cleanup. Skipping HTML cleanup.", file=sys.stderr)


try:
    with open(config_file_path, 'w') as f:
        json.dump(final_list_after_html_gen, f, indent=2)
    print(f'Updated redirects.json with public_url and discovered files: {config_file_path}')
except Exception as e:
    print(f"Error writing updated redirects.json: {e}", file=sys.stderr)
    sys.exit(1)

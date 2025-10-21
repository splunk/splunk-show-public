# .github/scripts/auto_generate_redirects.py
import json
from jinja2 import Template
import os
import sys
import urllib.parse
import re

# --- Configuration ---
GITHUB_REPO_OWNER = 'splunk'
GITHUB_REPO_NAME = 'splunk-show-public'
GITHUB_PAGES_BASE_URL = f"https://{GITHUB_REPO_OWNER}.github.io/{GITHUB_REPO_NAME}/"
ROOT_CONTENT_DIRECTORY = "public"

# --- Helper Functions ---
def remove_date_patterns(text):
    """
    Removes common date patterns from a string, especially at the end.
    Handles variations like " - Month YYYY", "Month YYYY", "YYYY-MM", "(Month YYYY)",
    and other common date separators.
    """
    months_abbr = r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
    months_full = r'(January|February|March|April|May|June|July|August|September|October|November|December)'
    month_pattern = f"(?:{months_abbr}|{months_full})"
    year_pattern = r'\d{4}|\'\d{2}'
    day_pattern = r'\d{1,2}(?:st|nd|rd|th)?'

    patterns = [
        rf'(?:[\s_-]|\s*\(\s*)?{month_pattern}\s+{year_pattern}(?:\s*\))?\b',
        rf'(?:[\s_-]|\s*\(\s*)?\d{{4}}-\d{{2}}(?:-\d{{2}})?(?:\s*\))?\b',
        rf'(?:[\s_-]|\s*\(\s*)?\d{{8}}(?:\s*\))?\b',
        rf'(?:[\s_-]|\s*\(\s*)?{day_pattern}\s+{month_pattern}\s+{year_pattern}(?:\s*\))?\b',
        rf'(?:[\s_-]|\s*\(\s*)?{month_pattern}\s+{day_pattern},?\s+{year_pattern}(?:\s*\))?\b',
        rf'(?:[\s_-]|\s*\(\s*)?{year_pattern}(?:\s*\))?\b',
    ]

    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()
    
    text = re.sub(r'[\s_-]+', ' ', text).strip(' -_')
    text = re.sub(r'\s+', ' ', text).strip()

    return text.strip()

def clean_filename_for_title(filename):
    """
    Cleans a filename to produce a human-readable title.
    - Removes file extensions.
    - Removes common date patterns.
    - Replaces underscores with spaces.
    - Normalizes hyphens that act as separators to " - ".
    - Normalizes all other whitespace to a single space.
    """
    name_without_ext = os.path.splitext(filename)[0]
    name_without_ext = remove_date_patterns(name_without_ext)
    name_without_ext = name_without_ext.replace('_', ' ')
    name_without_ext = re.sub(r'\s*-\s*', ' - ', name_without_ext)
    name_without_ext = re.sub(r'\s+', ' ', name_without_ext)
    return name_without_ext.strip()

def slugify(text):
    """Converts text to a URL-friendly slug."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = text.strip('-')
    return text

# --- Main Script Logic ---
repo_root = os.getenv('GITHUB_WORKSPACE')

config_file_path = os.path.join(repo_root, 'redirects.json')
template_file_path = os.path.join(repo_root, '_redirect_templates', 'redirect_template.html')

# Read existing redirects.json and map by 'id' for stable lookup
existing_redirects_map_by_id = {} # Key: id, Value: entry
try:
    with open(config_file_path, 'r') as f:
        existing_data = json.load(f)
        for entry in existing_data:
            if 'id' in entry:
                if entry['id'] in existing_redirects_map_by_id:
                    print(f"Warning: Duplicate 'id' found in redirects.json for '{entry['id']}'. Only the last one will be used for merging.", file=sys.stderr)
                existing_redirects_map_by_id[entry['id']] = entry
            else:
                print(f"Warning: Entry missing 'id' in redirects.json: {entry}. Cannot track for renames.", file=sys.stderr)
except FileNotFoundError:
    print("No existing redirects.json found. Starting fresh.", file=sys.stderr)
except json.JSONDecodeError:
    print("Invalid JSON format in existing redirects.json. It might be overwritten. Error:", file=sys.stderr)
    existing_redirects_map_by_id = {}


# Read HTML template
try:
    with open(template_file_path, 'r') as f:
        template_content = f.read()
    template = Template(template_content)
except FileNotFoundError:
    print(f"Error: Template file not found at {template_file_path}. Exiting.", file=sys.stderr)
    sys.exit(1)

final_redirects_config_for_writing = []
processed_ids_in_this_run = set() # To track which existing IDs we've matched/updated

full_root_content_path = os.path.join(repo_root, ROOT_CONTENT_DIRECTORY)
if not os.path.isdir(full_root_content_path):
    print(f"Error: ROOT_CONTENT_DIRECTORY '{ROOT_CONTENT_DIRECTORY}' not found at '{full_root_content_path}'. No files will be scanned. Exiting.", file=sys.stderr)
    sys.exit(1)

print(f"Starting recursive file discovery in '{full_root_content_path}'")

for root, _, files in os.walk(full_root_content_path):
    for filename in files:
        if filename.startswith('.') or filename in ['.gitkeep', 'Thumbs.db', 'desktop.ini']:
            continue
        if filename.lower().endswith('.html'):
            print(f"Skipping generated HTML file: {os.path.join(root, filename)}")
            continue

        relative_original_file_path = os.path.relpath(os.path.join(root, filename), repo_root)
        relative_original_file_path = relative_original_file_path.replace(os.sep, '/')

        current_target_file_url_in_json = GITHUB_PAGES_BASE_URL + relative_original_file_path
        
        # --- Infer values for a potential new entry ---
        name_without_ext_and_date = remove_date_patterns(os.path.splitext(filename)[0])
        name_for_slug_path = name_without_ext_and_date.replace('_', ' ')

        inferred_id = slugify(name_for_slug_path)
        inferred_title = clean_filename_for_title(filename)
        
        pdf_dir_relative = os.path.dirname(relative_original_file_path)
        inferred_redirect_html_path = os.path.join(pdf_dir_relative, slugify(name_for_slug_path) + '.html')
        inferred_redirect_html_path = inferred_redirect_html_path.replace(os.sep, '/')

        # --- Try to find an existing entry by ID ---
        entry_data = {}
        if inferred_id in existing_redirects_map_by_id:
            # Found an existing entry with this ID, likely a rename or a re-run
            existing_entry = existing_redirects_map_by_id[inferred_id]
            
            # Preserve manual tweaks for id, title, redirect_html_path
            entry_data['id'] = existing_entry.get('id', inferred_id)
            entry_data['title'] = existing_entry.get('title', inferred_title)
            entry_data['redirect_html_path'] = existing_entry.get('redirect_html_path', inferred_redirect_html_path)
            
            # ALWAYS update current_target_file to the newly discovered path
            entry_data['current_target_file'] = current_target_file_url_in_json
            
            print(f"Matched existing entry for ID '{entry_data['id']}'. Updating target from '{existing_entry.get('current_target_file', 'N/A')}' to '{current_target_file_url_in_json}'.")
        else:
            # No existing entry with this ID, create a new one with inferred values
            entry_data = {
                "id": inferred_id,
                "title": inferred_title,
                "redirect_html_path": inferred_redirect_html_path,
                "current_target_file": current_target_file_url_in_json
            }
            print(f"Creating new entry for '{inferred_id}' -> '{current_target_file_url_in_json}'")

        final_redirects_config_for_writing.append(entry_data)
        processed_ids_in_this_run.add(entry_data['id']) # Mark this ID as processed

# --- Handle entries that were in redirects.json but are no longer discovered ---
# This means files were deleted or renamed with a new inferred ID
for existing_id, existing_entry in existing_redirects_map_by_id.items():
    if existing_id not in processed_ids_in_this_run:
        # Check if the file associated with this ID still exists in the repo
        # This helps differentiate between a file deletion and a file rename that resulted in a new ID
        # (e.g., if the user manually changed the ID in redirects.json)
        
        # Extract relative path from current_target_file
        if 'current_target_file' in existing_entry:
            parsed_url = urllib.parse.urlparse(existing_entry['current_target_file'])
            relative_path_from_base_url = parsed_url.path.replace(f'/{GITHUB_REPO_NAME}/', '', 1) # Remove repo name
            if relative_path_from_base_url.startswith('public/'):
                relative_path_from_base_url = relative_path_from_base_url[len('public/'):] # Remove leading public/
            
            full_path_on_runner = os.path.join(repo_root, ROOT_CONTENT_DIRECTORY, relative_path_from_base_url)
            
            if os.path.exists(full_path_on_runner):
                print(f"Warning: Existing entry '{existing_id}' points to '{existing_entry['current_target_file']}' which still exists, but its ID was not matched by any discovered file. This entry will be removed unless you manually edit redirects.json to match its new inferred ID or update its 'current_target_file' to match an an existing file.", file=sys.stderr)
            else:
                print(f"Removing entry for '{existing_id}' as its associated file '{existing_entry.get('current_target_file', 'N/A')}' was not found in scanned directories.", file=sys.stderr)
        else:
            print(f"Removing entry for '{existing_id}' as it's not associated with a discovered file and has no 'current_target_file'.", file=sys.stderr)

# --- Generate HTML for all entries and update public_url ---
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


final_list_after_html_gen.sort(key=lambda x: x.get('id', '').lower())

try:
    with open(config_file_path, 'w') as f:
        json.dump(final_list_after_html_gen, f, indent=2)
    print(f'Updated redirects.json with public_url and discovered files: {config_file_path}')
except Exception as e:
    print(f"Error writing updated redirects.json: {e}", file=sys.stderr)
    sys.exit(1)

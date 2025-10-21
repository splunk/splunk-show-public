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
# !!! UPDATED: Base URL for GitHub Pages site (DO NOT include the /public/ segment here) !!!
GITHUB_PAGES_BASE_URL = f"https://{GITHUB_REPO_OWNER}.github.io/{GITHUB_REPO_NAME}/"

# The SINGLE ROOT directory where all your content now lives
ROOT_CONTENT_DIRECTORY = "public"

# --- Helper Functions ---
def remove_date_patterns(text):
    """
    Removes common date patterns from a string, especially at the end.
    Handles variations like " - Month YYYY", "Month YYYY", "YYYY-MM", "(Month YYYY)",
    and other common date separators.
    """
    # Regex to match common month abbreviations
    months_abbr = r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
    # Regex to match common full month names (less common in filenames, but good to have)
    months_full = r'(January|February|March|April|May|June|July|August|September|October|November|December)'

    # Combine month patterns
    month_pattern = f"(?:{months_abbr}|{months_full})"

    # Year pattern (e.g., 2023, '23)
    year_pattern = r'\d{4}|\'\d{2}'

    # Day pattern (e.g., 01, 1st, 1)
    day_pattern = r'\d{1,2}(?:st|nd|rd|th)?'

    # --- Comprehensive date patterns ---
    patterns = [
        # " - Month YYYY" or " Month YYYY" or " (Month YYYY)"
        rf'(?:[\s_-]|\s*\(\s*)?{month_pattern}\s+{year_pattern}(?:\s*\))?\b',
        # " - YYYY-MM(-DD)" or " YYYY-MM(-DD)" or " (YYYY-MM(-DD))"
        rf'(?:[\s_-]|\s*\(\s*)?\d{{4}}-\d{{2}}(?:-\d{{2}})?(?:\s*\))?\b',
        # " - YYYYMMDD"
        rf'(?:[\s_-]|\s*\(\s*)?\d{{8}}(?:\s*\))?\b',
        # " - DD Month YYYY" (e.g., 15 Oct 2023)
        rf'(?:[\s_-]|\s*\(\s*)?{day_pattern}\s+{month_pattern}\s+{year_pattern}(?:\s*\))?\b',
        # " - Month DD, YYYY" (e.g., Oct 15, 2023)
        rf'(?:[\s_-]|\s*\(\s*)?{month_pattern}\s+{day_pattern},?\s+{year_pattern}(?:\s*\))?\b',
        # " - YYYY" alone (less specific, but can catch trailing years)
        rf'(?:[\s_-]|\s*\(\s*)?{year_pattern}(?:\s*\))?\b',
    ]

    # Apply patterns from most specific to least specific
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()
    
    # Clean up any residual separators or multiple spaces
    text = re.sub(r'[\s_-]+', ' ', text).strip(' -_')
    text = re.sub(r'\s+', ' ', text).strip() # Normalize spaces again

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
    name_without_ext = os.path.splitext(filename)[0] # Get name without extension
    
    # 1. Remove date patterns (this is now more robust)
    name_without_ext = remove_date_patterns(name_without_ext)
    
    # 2. Replace underscores with spaces
    name_without_ext = name_without_ext.replace('_', ' ')
    
    # 3. Normalize hyphens that act as separators to " - "
    # This regex replaces any sequence of whitespace, hyphen, whitespace with a consistent " - "
    name_without_ext = re.sub(r'\s*-\s*', ' - ', name_without_ext)
    
    # 4. Normalize all other whitespace to a single space
    name_without_ext = re.sub(r'\s+', ' ', name_without_ext)
    
    return name_without_ext.strip() # Remove leading/trailing spaces

def slugify(text):
    """Converts text to a URL-friendly slug."""
    text = text.lower() # Ensure slug is always lowercase for consistency
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
        if filename.lower().endswith('.html'):
            print(f"Skipping generated HTML file: {os.path.join(root, filename)}")
            continue

        relative_original_file_path = os.path.relpath(os.path.join(root, filename), repo_root)
        relative_original_file_path = relative_original_file_path.replace(os.sep, '/')

        # current_target_file_url_in_json will now correctly start with /public/
        current_target_file_url_in_json = GITHUB_PAGES_BASE_URL + relative_original_file_path
        
        discovered_original_file_urls.add(current_target_file_url_in_json)

        entry_to_process = existing_redirects_map.get(current_target_file_url_in_json, {}).copy()

        inferred_title = clean_filename_for_title(filename)
        
        name_without_ext_and_date = remove_date_patterns(os.path.splitext(filename)[0])
        name_without_ext_and_date = name_without_ext_and_date.replace('_', ' ')
        inferred_id = slugify(name_without_ext_and_date)

        pdf_dir_relative = os.path.dirname(relative_original_file_path)
        inferred_redirect_html_path = os.path.join(pdf_dir_relative, slugify(name_without_ext_and_date) + '.html')
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
    # calculated_public_url will now correctly start with /public/
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
            if filename.lower().endswith('.html'): # Only consider .html files for cleanup
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

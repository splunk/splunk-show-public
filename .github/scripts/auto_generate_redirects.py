# .github/scripts/auto_generate_redirects.py
import json
from jinja2 import Template
import os
import sys
import urllib.parse
import re
from datetime import datetime
import subprocess

# --- Configuration ---
GITHUB_REPO_OWNER = 'splunk'
GITHUB_REPO_NAME = 'splunk-show-public'
GITHUB_PAGES_BASE_URL = f"https://{GITHUB_REPO_OWNER}.github.io/{GITHUB_REPO_NAME}/"
ROOT_CONTENT_DIRECTORY = "public"
PUBLIC_FILE_LIST_FILENAME = "public_file_list.md"

# --- Helper Functions ---
def get_file_git_sha(file_path_full_on_runner):
    """
    Gets the Git SHA-1 hash of a file's content using 'git hash-object'.
    This calculates the hash of the current working tree content.
    Returns None if the file is new/untracked or an error occurs.
    """
    try:
        if not os.path.exists(file_path_full_on_runner):
            print(f"DEBUG SHA: File not found on runner for SHA calculation: {file_path_full_on_runner}", file=sys.stderr)
            return None
        
        with open(file_path_full_on_runner, 'rb') as f:
            file_content = f.read()
            
            cmd = ['git', 'hash-object', '--stdin']
            
            result = subprocess.run(cmd, cwd=os.getenv('GITHUB_WORKSPACE'), input=file_content, capture_output=True, check=True)
            
            sha = result.stdout.decode('utf-8').strip()
            return sha
    except FileNotFoundError:
        return None
    except subprocess.CalledProcessError as e:
        print(f"ERROR SHA: 'git hash-object' failed for '{file_path_full_on_runner}': {e.stderr.decode('utf-8').strip()}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"ERROR SHA: Unexpected error getting SHA for '{file_path_full_on_runner}': {e}", file=sys.stderr)
        return None

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
public_file_list_path = os.path.join(repo_root, PUBLIC_FILE_LIST_FILENAME)

# Read existing redirects.json and map by 'current_target_file' (normalized to lowercase) for stable lookup
existing_redirects_map_by_normalized_target_url = {}
try:
    with open(config_file_path, 'r') as f:
        existing_data = json.load(f)
        for entry in existing_data:
            if 'current_target_file' in entry:
                existing_redirects_map_by_normalized_target_url[entry['current_target_file'].lower()] = entry
            else:
                print(f"Warning: Entry missing 'current_target_file' in redirects.json: {entry}. This entry will be ignored for merging.", file=sys.stderr)
except FileNotFoundError:
    print("No existing redirects.json found. Starting fresh.", file=sys.stderr)
except json.JSONDecodeError:
    print("Invalid JSON format in existing redirects.json. It might be overwritten. Error:", file=sys.stderr)
    existing_redirects_map_by_normalized_target_url = {}


# Read HTML template
try:
    with open(template_file_path, 'r') as f:
        template_content = f.read()
    template = Template(template_content)
except FileNotFoundError:
    print(f"Error: Template file not found at {template_file_path}. Exiting.", file=sys.stderr)
    sys.exit(1)

new_master_redirects_list = []
discovered_target_urls = set() # To track which target URLs (original files) we've processed

full_root_content_path = os.path.join(repo_root, ROOT_CONTENT_DIRECTORY)
if not os.path.isdir(full_root_content_path):
    print(f"Error: ROOT_CONTENT_DIRECTORY '{ROOT_CONTENT_DIRECTORY}' not found at '{full_root_content_path}'. No files will be scanned. Exiting.", file=sys.stderr)
    sys.exit(1)

print(f"Starting recursive file discovery in '{full_root_content_path}'")

for root, _, files in os.walk(full_root_content_path):
    for filename in files:
        if filename.startswith('.') or filename in ['.gitkeep', 'Thumbs.db', 'desktop.ini']:
            print(f"DEBUG: Skipping hidden/system file: {os.path.join(root, filename)}")
            continue
        if filename.lower().endswith('.html'):
            print(f"DEBUG: Skipping generated HTML file: {os.path.join(root, filename)}")
            continue

        relative_original_file_path = os.path.relpath(os.path.join(root, filename), repo_root)
        relative_original_file_path = relative_original_file_path.replace(os.sep, '/')

        current_target_file_url_in_json_actual_casing = GITHUB_PAGES_BASE_URL + relative_original_file_path
        discovered_target_urls.add(current_target_file_url_in_json_actual_casing)

        name_without_ext_and_date = remove_date_patterns(os.path.splitext(filename)[0])
        name_for_slug_path = name_without_ext_and_date.replace('_', ' ')

        id_base_path = os.path.relpath(os.path.join(root, os.path.splitext(filename)[0]), full_root_content_path)
        inferred_id = slugify(id_base_path)
        
        inferred_title = clean_filename_for_title(filename)
        
        pdf_dir_relative = os.path.dirname(relative_original_file_path)
        inferred_redirect_html_path = os.path.join(pdf_dir_relative, slugify(name_for_slug_path) + '.html')
        inferred_redirect_html_path = inferred_redirect_html_path.replace(os.sep, '/')

        entry_data = {}
        current_timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        full_path_to_original_file = os.path.join(repo_root, relative_original_file_path)
        current_file_sha = get_file_git_sha(full_path_to_original_file)
        
        if current_file_sha is None:
            print(f"ERROR: Failed to get Git SHA for '{relative_original_file_path}'. This file will be skipped from redirects.json.", file=sys.stderr)
            continue

        if current_target_file_url_in_json_actual_casing.lower() in existing_redirects_map_by_normalized_target_url:
            existing_entry = existing_redirects_map_by_normalized_target_url[current_target_file_url_in_json_actual_casing.lower()]
            
            entry_data['id'] = existing_entry.get('id', inferred_id)
            entry_data['title'] = existing_entry.get('title', inferred_title)
            entry_data['redirect_html_path'] = existing_entry.get('redirect_html_path', inferred_redirect_html_path)
            
            entry_data['current_target_file'] = current_target_file_url_in_json_actual_casing

            changed = False
            if entry_data['id'] != existing_entry.get('id'): changed = True
            if entry_data['title'] != existing_entry.get('title'): changed = True
            if entry_data['redirect_html_path'] != existing_entry.get('redirect_html_path'): changed = True
            if entry_data['current_target_file'].lower() != existing_entry.get('current_target_file', '').lower(): changed = True
            if current_file_sha != existing_entry.get('file_sha'): changed = True
            
            if changed:
                entry_data['last_updated_at'] = current_timestamp_str
                entry_data['file_sha'] = current_file_sha
                print(f"DEBUG: Entry '{entry_data['id']}' changed (content or metadata). Updating timestamp to {current_timestamp_str}.")
            else:
                entry_data['last_updated_at'] = existing_entry.get('last_updated_at', current_timestamp_str)
                entry_data['file_sha'] = existing_entry.get('file_sha', current_file_sha)
                print(f"DEBUG: Entry '{entry_data['id']}' unchanged. Preserving timestamp and SHA.")

            print(f"DEBUG: Matched existing entry for original file '{current_target_file_url_in_json_actual_casing}'. Preserving manual overrides.")
        else:
            entry_data = {
                "id": inferred_id,
                "title": inferred_title,
                "redirect_html_path": inferred_redirect_html_path,
                "current_target_file": current_target_file_url_in_json_actual_casing,
                "last_updated_at": current_timestamp_str,
                "file_sha": current_file_sha
            }
            print(f"DEBUG: Creating new entry for '{inferred_id}' -> '{current_target_file_url_in_json_actual_casing}' with timestamp {current_timestamp_str}.")

        new_master_redirects_list.append(entry_data)

# --- Cleanup: Remove entries from redirects.json whose original files are no longer discovered ---
final_discovered_urls_normalized = {url.lower() for url in discovered_target_urls}
for existing_normalized_target_url, existing_entry in existing_redirects_map_by_normalized_target_url.items():
    if existing_normalized_target_url not in final_discovered_urls_normalized:
        print(f"Removing entry for ID '{existing_entry.get('id', 'N/A')}' as its associated file '{existing_entry.get('current_target_file', 'N/A')}' was not found in scanned directories.", file=sys.stderr)


# --- Generate HTML for all entries and update public_url ---
generated_html_files = set() # Track generated HTML files for cleanup

for entry in new_master_redirects_list:
    title = entry['title']
    raw_current_target_file = entry['current_target_file']
    relative_redirect_html_path = entry['redirect_html_path']

    parsed_target_url = urllib.parse.urlparse(raw_current_target_file)
    encoded_target_path = urllib.parse.quote(parsed_target_url.path, safe='/')
    encoded_query = urllib.parse.quote(parsed_target_url.query, safe='=&')
    # FIX: Correct variable names in _replace call
    target_url_for_html = urllib.parse.urlunparse(parsed_target_url._replace(path=encoded_target_path, query=encoded_query))

    path_segments = relative_redirect_html_path.split('/')
    encoded_path_segments = [urllib.parse.quote(segment, safe='') for segment in path_segments]
    public_url_path_encoded = '/'.join(encoded_path_segments)
    calculated_public_url = GITHUB_PAGES_BASE_URL + public_url_path_encoded

    if entry.get('public_url') != calculated_public_url:
        entry['last_updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"Public URL for '{entry['id']}' changed. Updating timestamp.")
    entry['public_url'] = calculated_public_url

    full_redirect_html_path = os.path.join(repo_root, relative_redirect_html_path)

    os.makedirs(os.path.dirname(full_redirect_html_path), exist_ok=True)

    rendered_html = template.render(title=title, target_url=target_url_for_html, public_url=calculated_public_url)
    
    existing_html_content = None
    if os.path.exists(full_redirect_html_path):
        with open(full_redirect_html_path, 'r') as f:
            existing_html_content = f.read()

    if rendered_html != existing_html_content:
        with open(full_redirect_html_path, 'w') as f:
            f.write(rendered_html)
        print(f'Generated/Updated HTML: {full_redirect_html_path}')
    else:
        print(f'HTML for {full_redirect_html_path} is unchanged. Skipping write.')
    
    generated_html_files.add(full_redirect_html_path)

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


# Sort the final list by 'id' before writing to JSON
new_master_redirects_list.sort(key=lambda x: x.get('id', '').lower())

try:
    new_redirects_json_content = json.dumps(new_master_redirects_list, indent=2)
    
    existing_redirects_json_content = None
    if os.path.exists(config_file_path):
        with open(config_file_path, 'r') as f:
            existing_redirects_json_content = f.read()

    if new_redirects_json_content != existing_redirects_json_content:
        with open(config_file_path, 'w') as f:
            f.write(new_redirects_json_content)
        print(f'Updated redirects.json with public_url and discovered files: {config_file_path}')
    else:
        print(f'redirects.json content is unchanged. Skipping write.')
except Exception as e:
    print(f"Error writing updated redirects.json: {e}", file=sys.stderr)
    sys.exit(1)

# --- Generate public_file_list.md with Last Update Column ---
print(f"Generating {PUBLIC_FILE_LIST_FILENAME}...")
public_file_list_content = "# Public File List\n\n"
public_file_list_content += "This file is automatically generated by the GitHub Actions workflow. Do not edit manually.\n\n"
public_file_list_content += f"Last generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"

if not new_master_redirects_list:
    public_file_list_content += "No public files found.\n"
else:
    grouped_entries = {}
    for entry in new_master_redirects_list:
        path_relative_to_root_content = os.path.relpath(entry['redirect_html_path'], ROOT_CONTENT_DIRECTORY)
        relative_parts = path_relative_to_root_content.split(os.sep)

        top_folder_name = "Root Files"
        sub_folder_name = "Files"

        if len(relative_parts) > 1:
            top_folder_name = relative_parts[0]
            if len(relative_parts) > 2:
                sub_folder_name = os.path.join(*relative_parts[1:-1]).replace(os.sep, '/')
            else:
                sub_folder_name = f"Files in {top_folder_name}"
        
        if top_folder_name not in grouped_entries:
            grouped_entries[top_folder_name] = {}
        if sub_folder_name not in grouped_entries[top_folder_name]:
            grouped_entries[top_folder_name][sub_folder_name] = []
        grouped_entries[top_folder_name][sub_folder_name].append(entry)

    sorted_top_folders = sorted(grouped_entries.keys())

    for top_folder in sorted_top_folders:
        public_file_list_content += f"<details>\n  <summary><h2>{top_folder}</h2></summary>\n"
        public_file_list_content += "---\n\n"
        
        sorted_sub_folders = sorted(grouped_entries[top_folder].keys())

        for sub_folder in sorted_sub_folders:
            public_file_list_content += f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<details>\n&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<summary><strong>{sub_folder}</strong></summary>\n\n"
            
            public_file_list_content += "| Title | Public URL | Last Updated |\n"
            public_file_list_content += "|---|---|---|\n"
            
            sorted_files_for_table = sorted(grouped_entries[top_folder][sub_folder], key=lambda x: x.get('title', '').lower())

            for entry in sorted_files_for_table:
                title = entry.get('title', 'N/A')
                public_url = entry.get('public_url', '#')
                
                last_updated_iso = entry.get('last_updated_at')
                if last_updated_iso and isinstance(last_updated_iso, str):
                    try:
                        dt_object = datetime.strptime(last_updated_iso, '%Y-%m-%d %H:%M:%S')
                        last_updated_display = dt_object.strftime('%Y-%m-%d %H:%M:%S UTC')
                    except ValueError:
                        dt_object = datetime.fromisoformat(last_updated_iso)
                        last_updated_display = dt_object.strftime('%Y-%m-%d %H:%M:%S UTC')
                else:
                    last_updated_display = 'N/A'
                
                escaped_title = title.replace('|', '\\|')
                
                public_file_list_content += f"| {escaped_title} | [Link]({public_url}) | {last_updated_display} |\n"
            
            public_file_list_content += "\n&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</details>\n"
        
        public_file_list_content += "</details>\n"

try:
    new_public_file_list_content = public_file_list_content
    
    existing_public_file_list_content = None
    if os.path.exists(public_file_list_path):
        with open(public_file_list_path, 'r') as f:
            existing_public_file_list_content = f.read()

    if new_public_file_list_content != existing_public_file_list_content:
        with open(public_file_list_path, 'w') as f:
            f.write(new_public_file_list_content)
        print(f'Generated {PUBLIC_FILE_LIST_FILENAME}: {public_file_list_path}')
    else:
        print(f'{PUBLIC_FILE_LIST_FILENAME} content is unchanged. Skipping write.')
except Exception as e:
    print(f"Error writing {PUBLIC_FILE_LIST_FILENAME}: {e}", file=sys.stderr)
    sys.exit(1)
#!/usr/bin/env python3
"""
Script to update debian changelog version from _version.py
Run this script when bumping versions to keep debian changelog in sync
"""

import os
import sys
from datetime import datetime

def get_version():
    """Get version from _version.py"""
    version_file = os.path.join(os.path.dirname(__file__), 'configurator', '_version.py')
    with open(version_file, 'r') as f:
        for line in f:
            if line.startswith('__version__'):
                return line.split('=')[1].strip().strip('"\'')
    raise RuntimeError('Unable to find version string.')

def update_changelog_version(version, changes_description):
    """Update the debian changelog with new version"""
    changelog_path = os.path.join(os.path.dirname(__file__), 'debian', 'changelog')
    
    # Read existing changelog
    with open(changelog_path, 'r') as f:
        existing_content = f.read()
    
    # Create new entry
    timestamp = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
    new_entry = f"""hifiberry-configurator ({version}) stable; urgency=medium

{changes_description}

 -- HiFiBerry <support@hifiberry.com>  {timestamp}

"""
    
    # Write new changelog
    with open(changelog_path, 'w') as f:
        f.write(new_entry + existing_content)
    
    print(f"Updated debian changelog to version {version}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python update_changelog.py 'description of changes'")
        print("Version will be read automatically from _version.py")
        sys.exit(1)
    
    version = get_version()
    changes = sys.argv[1]
    
    # Format changes as bullet points
    formatted_changes = '\n'.join(f'  * {line.strip()}' for line in changes.split('\n') if line.strip())
    
    update_changelog_version(version, formatted_changes)

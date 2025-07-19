#!/usr/bin/env python3
"""
Script to sync API documentation version with _version.py
"""

import os
import re

def get_version():
    """Get version from _version.py"""
    version_file = os.path.join(os.path.dirname(__file__), 'configurator', '_version.py')
    with open(version_file, 'r') as f:
        for line in f:
            if line.startswith('__version__'):
                return line.split('=')[1].strip().strip('"\'')
    raise RuntimeError('Unable to find version string.')

def update_api_docs_version(version):
    """Update API documentation version"""
    docs_path = os.path.join(os.path.dirname(__file__), 'docs', 'api-documentation.md')
    
    with open(docs_path, 'r') as f:
        content = f.read()
    
    # Update the main version at the top
    content = re.sub(r'\*\*Version \d+\.\d+\.\d+\*\*', f'**Version {version}**', content)
    
    # Update version in the JSON response example
    content = re.sub(r'"version": "\d+\.\d+\.\d+"', f'"version": "{version}"', content)
    
    # Update the footer version
    content = re.sub(r'HiFiBerry Configuration API v\d+\.\d+\.\d+', f'HiFiBerry Configuration API v{version}', content)
    
    with open(docs_path, 'w') as f:
        f.write(content)
    
    print(f"Updated API documentation to version {version}")

if __name__ == '__main__':
    version = get_version()
    update_api_docs_version(version)
    print(f"Synced API documentation with version {version} from _version.py")

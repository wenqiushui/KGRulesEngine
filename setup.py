from setuptools import setup, find_packages
from pathlib import Path
import re # For extracting version from __init__.py

# Read the contents of your README file
this_directory = Path(__file__).parent
try:
    with open(this_directory / 'README.md', encoding='utf-8') as f:
        long_description = f.read()
except FileNotFoundError:
    long_description = 'Knowledge-CAD-Engine (KCE) - A knowledge-driven CAD automation engine.' # Fallback

# Read the contents of requirements.txt
try:
    with open(this_directory / 'requirements.txt', encoding='utf-8') as f:
        install_requires = [line.strip() for line in f if line.strip() and not line.startswith('#')]
except FileNotFoundError:
    print("Warning: requirements.txt not found. install_requires will be empty.")
    install_requires = []

# Get version from kce_core/__init__.py
VERSION = "0.1.0" # Fallback version
try:
    init_py_content = (this_directory / "kce_core" / "__init__.py").read_text(encoding='utf-8')
    version_match = re.search(r"^__version__\s*=\s*['\"]([^'\"]*)['\"]", init_py_content, re.M)
    if version_match:
        VERSION = version_match.group(1)
    else:
        print(f"Warning: Could not parse __version__ from kce_core/__init__.py. Using fallback version {VERSION}.")
except FileNotFoundError:
    print(f"Warning: kce_core/__init__.py not found. Using fallback version {VERSION}.")
except Exception as e:
    print(f"Warning: Error reading version from kce_core/__init__.py: {e}. Using fallback version {VERSION}.")

setup(
    name='kce_engine',  # Package name on PyPI
    version=VERSION,
    author='KCE Development Team',
    author_email='dev@kce.example.com', # Placeholder
    description='Knowledge-CAD-Engine for knowledge-driven automation.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='http://kce.example.com/kce_engine',  # Placeholder URL

    packages=find_packages(exclude=['tests*', 'docs*', 'examples*', 'temp_merge*']),

    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'Topic :: Scientific/Engineering',
        'License :: OSI Approved :: Apache Software License',  # Assuming Apache 2.0 from previous context
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],

    python_requires='>=3.8', # Minimum version of Python required

    install_requires=install_requires, # List of dependencies from requirements.txt

    entry_points={
        'console_scripts': [
            'kce=cli.main:cli',  # This makes  command available after install
        ],
    },

    # If you have data files that need to be included with your package (e.g., default ontologies)
    # package_data={'kce_core': ['ontologies/*.ttl']}, # This would look inside kce_core/ontologies
    # include_package_data=True, # Usually needed if using MANIFEST.in or package_data
    # For ontologies at the project root 'ontologies/' dir, use MANIFEST.in or data_files

    project_urls={  # Optional
        'Documentation': 'http://kce.example.com/docs', # Placeholder
        'Source': 'http://kce.example.com/source', # Placeholder
        'Tracker': 'http://kce.example.com/issues', # Placeholder
    },
)

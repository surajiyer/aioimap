from pathlib import Path
from setuptools import setup, find_packages

package_dir = 'aioimap'
root = Path(__file__).parent.resolve()

# Read in package meta from about.py
about_path = root / package_dir / 'about.py'
with about_path.open('r', encoding='utf8') as f:
    about = {}
    exec(f.read(), about)

# Get readme
readme_path = root / 'README.md'
with readme_path.open('r', encoding='utf8') as f:
    readme = f.read()

install_requires = [
    "aioimaplib>=0.7.18",
    "python-dotenv",
    "fastapi>=0.61",
    "uvicorn>=0.12"]
test_requires = []

setup(
    name=about['__title__'],
    description=about['__summary__'],
    long_description=readme,
    long_description_content_type='text/markdown',
    author=about['__author__'],
    author_email=about['__email__'],
    url=about['__uri__'],
    version=about['__version__'],
    license=about['__license__'],
    packages=find_packages(exclude=('tests*',)),
    install_requires=install_requires,
    test_requires=test_requires,
    zip_safe=True,
)

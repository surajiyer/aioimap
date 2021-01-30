# On Windows powershell.exe with restricted policy to execute scripts, run the following command:
# cat pypi-publish.sh | powershell.exe
python -m pip install --no-cache-dir twine --user
python setup.py sdist
python -m twine upload dist/* --verbose
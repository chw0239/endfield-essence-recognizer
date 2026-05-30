cd frontend
call npm run build
cd ..
uv sync --no-dev --group build
uv run pyinstaller main.spec -y
uv run python scripts/generate_manifest.py --dist-dir dist/endfield-essence-recognizer
cd dist/endfield-essence-recognizer
mklink /H config.json "../../config.json"
mklink /H custom_rule.py "../../custom_rule.py"
cd ../..

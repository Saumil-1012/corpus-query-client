
set -eu
cd "$(dirname "$0")"
PROJECT="$(basename "$PWD")"
OUT="../recall-space-submission.zip"

if [ ! -f .env ]; then
  echo "STOP: .env is missing. Run: cp .env.example .env   then put your Azure key and endpoint in it."; exit 1
fi
KEY="$(grep -E '^AZURE_OPENAI_API_KEY=' .env | cut -d= -f2- | tr -d '[:space:]"')"
if [ -z "$KEY" ]; then
  echo "STOP: AZURE_OPENAI_API_KEY in .env is empty."; exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "== Creating virtual environment (first run only)"
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
export PYTHON="$PWD/.venv/bin/python"

echo "== 1/4 Tests"
"$PYTHON" -m pytest -q -p no:cacheprovider

echo "== 2/4 Real transcript (Azure OpenAI)"
out="$(./make_transcript.sh)"; echo "$out"
if ! echo "$out" | grep -q "^OK:"; then
  echo "STOP: transcript check failed. Send transcript.md to Claude."; exit 1
fi
if grep -q "^Error\|exit code [1-9]" transcript.md; then
  echo "STOP: an error is in transcript.md. Send it to Claude."; exit 1
fi

echo "== 3/4 Building $OUT"
rm -f "$OUT"
(cd .. && zip -rq "recall-space-submission.zip" "$PROJECT" \
  -x "$PROJECT/.env" "$PROJECT/.venv/*" "$PROJECT/finish.sh" "*/__pycache__/*" "*/.pytest_cache/*" "*/.DS_Store")

echo "== 4/4 Safety check"
if unzip -p "$OUT" | grep -qF "$KEY"; then
  rm -f "$OUT"; echo "STOP: your API key was found inside the zip. Zip deleted. Check .env.example."; exit 1
fi
if unzip -l "$OUT" | grep -qE "/\.env$"; then
  rm -f "$OUT"; echo "STOP: .env ended up in the zip. Zip deleted."; exit 1
fi
echo
echo "DONE. Send this file: $(cd .. && pwd)/recall-space-submission.zip"

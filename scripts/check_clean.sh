#!/usr/bin/env bash
# Pre-commit guard (HLD §8.2): blocks recordings, transcripts, PDFs and real names from commits.
# Install: ln -sf ../../scripts/check_clean.sh .git/hooks/pre-commit
set -euo pipefail

staged=$(git diff --cached --name-only --diff-filter=ACM)
[ -z "$staged" ] && exit 0
status=0

blocked=$(grep -Ei '\.(mp4|mov|mkv|webm|mp3|m4a|wav|vtt|srt|pdf)$|(^|/)\.env$|secrets\.toml$' <<<"$staged" || true)
if [ -n "$blocked" ]; then
  echo "Blocked: media, transcript, PDF or secrets files staged:" >&2
  echo "$blocked" >&2
  status=1
fi

keys=$(git grep --cached -l -E 'sk-ant-[A-Za-z0-9_-]{10,}' -- $staged || true)
if [ -n "$keys" ]; then
  echo "Blocked: API key found in staged files:" >&2
  echo "$keys" >&2
  status=1
fi

# redact_names.txt is local and git-ignored: one real name per line. Binary files are skipped (-I):
# short names match random bytes in files such as the face-detection model; media, PDFs and
# transcripts are blocked by file name above.
if [ -f redact_names.txt ]; then
  names=$(grep -v '^[[:space:]]*$' redact_names.txt || true)
  if [ -n "$names" ]; then
    # Print only file paths, never the matched names.
    leaks=$(git grep --cached -I -l -i -w -F -f <(echo "$names") -- $staged || true)
    if [ -n "$leaks" ]; then
      echo "Blocked: real names found in staged files:" >&2
      echo "$leaks" >&2
      status=1
    fi
  fi
fi

exit $status

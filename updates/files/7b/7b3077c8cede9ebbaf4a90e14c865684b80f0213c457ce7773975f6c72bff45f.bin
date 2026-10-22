#!/usr/bin/env python3
"""Run one read-only OpenCLI search; convert in memory and never print raw errors."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unicodedata
from xiaohongshu_links import convert, XiaohongshuLinkError

class SearchError(RuntimeError):
    """A safe-to-display failure without raw platform payloads."""

SORTS = ('comprehensive', 'latest', 'most-liked', 'most-commented', 'most-collected')
PUBLISH_TIMES = ('anytime', 'day', 'week', 'half-year')

def resolve_command(opencli_js=None):
    if opencli_js:
        entry = Path(opencli_js).expanduser().resolve()
        node = shutil.which('node')
        if not node or not entry.is_file() or entry.suffix not in ('.js', '.mjs', '.cjs'):
            raise SearchError('Need node and a verified local OpenCLI JavaScript entry file.')
        return [node, str(entry)]
    executable = shutil.which('opencli')
    if not executable:
        raise SearchError('OpenCLI not found in this agent process PATH; read references/setup.md.')
    if Path(executable).suffix.lower() in ('.cmd', '.bat', '.ps1'):
        # Do not send user queries through Windows cmd.exe / PowerShell shims.
        entry = Path(executable).parent / 'node_modules/@jackwener/opencli/dist/src/main.js'
        if entry.is_file():
            return resolve_command(str(entry))
        raise SearchError('Windows shim detected; pass --opencli-js with the installed package entry.')
    return [executable]

def search(query, *, limit=5, purpose='response', timeout=120, command=None,
           sort=None, publish_time=None):
    if (not isinstance(query, str) or not query.strip() or len(query) > 1000
            or any(unicodedata.category(c) == 'Cc' for c in query)):
        raise SearchError('query must be one nonempty line, at most 1000 characters.')
    if query.lstrip().startswith('-'):
        raise SearchError('Rewrite a leading-hyphen query as normal search words.')
    try:
        convert([], purpose=purpose, limit=limit)
    except XiaohongshuLinkError as error:
        raise SearchError(str(error)) from None
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 300:
        raise SearchError('timeout must be an integer from 1 to 300 seconds.')
    if (sort is not None and sort not in SORTS) or (publish_time is not None and publish_time not in PUBLISH_TIMES):
        raise SearchError('Unsupported filter; check the installed OpenCLI search help.')
    args = [*(command or resolve_command()), 'xiaohongshu', 'search', query,
            '--limit', str(limit), '-f', 'json']
    if sort:
        args.extend(['--sort', sort])
    if publish_time:
        args.extend(['--publish-time', publish_time])
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                                timeout=timeout, check=False, shell=False)
    except subprocess.TimeoutExpired:
        raise SearchError('Search timed out; no automatic retry. Check browser state before retrying.') from None
    except (OSError, UnicodeError):
        raise SearchError('Cannot run OpenCLI or decode its output; check local runtime and UTF-8 support.') from None
    if result.returncode == 66:
        payload = []
    elif result.returncode:
        reason = {69: 'Browser Bridge unavailable', 75: 'backend timeout',
                  77: 'login required', 78: 'backend configuration error'}.get(result.returncode, 'backend failure')
        raise SearchError(f'OpenCLI exit {result.returncode}: {reason}. No retry; read references/setup.md.')
    else:
        try:
            payload = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            raise SearchError('OpenCLI did not return JSON; no raw output displayed.') from None
    try:
        output = convert(payload, purpose=purpose, limit=limit)
    except (XiaohongshuLinkError, ValueError, TypeError):
        raise SearchError('Search output has an unsupported record or URL; check the converter schema.') from None
    output['status'] = 'ok' if output['results'] else 'empty'
    return output

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    query_group = parser.add_mutually_exclusive_group(required=True)
    query_group.add_argument('--query')
    query_group.add_argument('--request-stdin', action='store_true', help='Read {"query": "..."} from stdin; options remain CLI flags.')
    parser.add_argument('--limit', type=int, default=5)
    parser.add_argument('--purpose', choices=('response', 'persistence'), default='response')
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--sort', choices=SORTS)
    parser.add_argument('--publish-time', choices=PUBLISH_TIMES)
    parser.add_argument('--opencli-js', help='Verified local OpenCLI JavaScript entry (Windows/custom installation).')
    args = parser.parse_args()
    try:
        query = args.query
        if args.request_stdin:
            try:
                request = json.load(sys.stdin)
                if not isinstance(request, dict) or set(request) != {'query'}:
                    raise ValueError
                query = request['query']
            except (ValueError, UnicodeError):
                raise SearchError('stdin must be a JSON object containing only query.') from None
        output = search(query, limit=args.limit, purpose=args.purpose, timeout=args.timeout,
                        command=resolve_command(args.opencli_js), sort=args.sort,
                        publish_time=args.publish_time)
    except SearchError as error:
        print(f'xhs search: {error}', file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

"""Private index maintenance; never prints fetched passages."""
import argparse
import json
from research_search import private_directory, safe_file, ROOT, SafeError
from local_search import LocalSearchProvider
from web_sources import SourcePolicy


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['refresh', 'reindex', 'coverage'])
    parser.add_argument('--site', help='Exact publisher name or approved host')
    parser.add_argument('--policy', help='Private policy filename')
    parser.add_argument('--deep', action='store_true', help='Explicit 10-minute refresh; still at most 500 pages')
    args = parser.parse_args(argv)
    try:
        base = private_directory()
        policy = SourcePolicy.load(safe_file(base, args.policy) if args.policy else ROOT/'config/source-policy.json')
        provider = LocalSearchProvider(base, policy, refresh=True, publisher_filter=args.site,
            max_seconds=600 if args.deep else 120, max_sitemap_files=500 if args.deep else 100,
            max_urls_discovered=50000 if args.deep else 20000)
        if args.command == 'reindex': result = provider.reindex()
        else:
            provider._load()
            if args.command == 'refresh': provider._crawl()
            result = provider.audit.get('site_coverage', [])
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (ValueError, OSError, SafeError):
        print('Index operation failed. Check the private folder, policy and crawl diagnostics. Existing snapshots are retained.')
        return 2


if __name__ == '__main__': raise SystemExit(main())

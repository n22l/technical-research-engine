"""Regressions from production failure mechanisms, using synthetic content."""
import gzip
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from local_search import LocalSearchProvider, discovery_links
from web_sources import SourcePolicy


class RecoveryTests(unittest.TestCase):
    def test_failed_maps_cannot_starve_articles_and_back_off(self):
        clock, calls = [0], []
        def fetch(url):
            calls.append(url)
            if url.endswith('robots.txt'): return b'User-agent: *\nDisallow:', 'text/plain'
            if url.endswith('.xml'):
                clock[0] += 10
                raise ValueError('synthetic timeout')
            return b'<p>Relevant reusable booster reflight.</p>', 'text/html'
        policy = SourcePolicy({'agency.example': {'allowed':True,'publisher':'Agency','type':'government',
            'sitemaps':['https://agency.example/map'+str(i)+'.xml' for i in range(20)]}})
        with tempfile.TemporaryDirectory() as tmp, patch('local_search.Fetcher.fetch',side_effect=fetch), patch('local_search.time.sleep'), patch('local_search.time.monotonic',side_effect=lambda:clock[0]):
            p=LocalSearchProvider(Path(tmp),policy)
            p._crawl()
            self.assertEqual(len(p.entries),1)
            page_index=calls.index('https://agency.example/')
            self.assertLessEqual(sum(u.endswith('.xml') for u in calls[:page_index]),2)
            failed=[u for u,s in p.inventory.items() if s['status']=='FETCH_FAILED']
            self.assertTrue(failed)
            self.assertTrue(all(p.inventory[u]['retry_after']>0 for u in failed))
            calls.clear();clock[0]=0;p._crawl()
            self.assertFalse(set(failed)&set(calls))

    def test_gzip_maps_bounded_and_entities_rejected(self):
        url='https://agency.example/map.xml.gz'
        body=b'<urlset><url><loc>https://agency.example/article</loc></url></urlset>'
        self.assertEqual(discovery_links(gzip.compress(body),url),[('https://agency.example/article','page')])
        for raw in [b'x'*2_000_001,b'<!DOCTYPE x><urlset/>']:
            with self.assertRaises(ValueError): discovery_links(gzip.compress(raw),url)

    def test_fresh_snapshot_cannot_hide_unmigrated_pages(self):
        import json,time
        policy=SourcePolicy({'agency.example':{'allowed':True,'publisher':'Agency','type':'government'}})
        with tempfile.TemporaryDirectory() as tmp:
            p=LocalSearchProvider(Path(tmp),policy)
            p.entries=[{'url':'https://agency.example/old','title':'SpaceX reuse both stages',
                'text':'SpaceX reuse both stages','retrieved_at':'2026-01-01','epoch':time.time()}]
            p.audit['indexed_at']='2026-01-01';p._save()
            q=LocalSearchProvider(Path(tmp),policy)
            self.assertFalse(q._load())
            self.assertEqual(q.search('SpaceX reuse both stages'),[])
            self.assertEqual(q.audit['legacy_pages'],1)
            def fetch(url):
                return (b'User-agent: *\nDisallow:', 'text/plain') if url.endswith('robots.txt') else (b'<p>SpaceX reuse both stages is a synthetic query.</p>','text/html')
            with patch('local_search.Fetcher.fetch',side_effect=fetch),patch('local_search.time.sleep'):
                q._crawl()
            self.assertEqual(q.audit['legacy_pages'],0)
            self.assertTrue(q.search('SpaceX reuse both stages')[0].local_match)


if __name__=='__main__':unittest.main()

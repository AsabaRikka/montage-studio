from montage.workflow import available_count, cache_sizes, clear_processing_cache


def test_capacity_filters_history_and_pending_pairs():
    assert available_count(['a1', 'a2'], ['b1', 'b2'], [('a1', 'b1'), ('a2', 'b2'), ('other', 'b1')]) == 2
    assert available_count([], ['b']) == 0
    assert available_count(['a', 'a'], ['b'], [('a', 'b'), ('a', 'b')]) == 0


def test_cache_cleanup_preserves_cloud_history_sources_and_thumbnails(tmp_path):
    files = {'cache/part': b'123', 'previews/test': b'12', 'frame_previews/frame': b'1',
             'cloud/video': b'company', 'thumbnails/image': b'jpg', 'history.sqlite3': b'history',
             'session.json': b'session', 'source.mp4': b'source'}
    for name, content in files.items():
        p = tmp_path / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(content)
    assert cache_sizes(tmp_path) == dict(processing=6, cloud=7, thumbnails=3)
    clear_processing_cache(tmp_path)
    assert cache_sizes(tmp_path)['processing'] == 0
    for name, content in files.items():
        if name.split('/')[0] not in ('cache', 'previews', 'frame_previews'):
            assert (tmp_path / name).read_bytes() == content

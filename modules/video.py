import os
import os.path
import itertools
from multiprocess import Pool


def dump_video(dmp):
    """Видео (по альбомам)

    dmp: Dumper object
    """
    folder = os.path.join('dump', 'video')
    os.makedirs(folder, exist_ok=True)

    print('Сохранение видео:')

    albums = dmp._vk_tools.get_all(
        method='video.getAlbums',
        max_count=100,
        values={
            'need_system': 1
        })

    for al in albums['items']:
        print('  Альбом "{}":'.format(al['title']))
        folder = os.path.join('dump', 'video', '_'.join(al['title'].split()))
        os.makedirs(folder, exist_ok=True)

        video = dmp._vk_tools.get_all(
            method='video.get',
            max_count=200,
            values={
                'album_id': al['id']
            })

        if video['count'] == 0:
            print('    0/0 (total: {})'.format(len(next(os.walk(folder))[2])))
        else:
            print('    .../{}'.format(len(video['items'])), end='\r')
            with Pool(dmp._AVAILABLE_THREADS if dmp._settings['LIMIT_VIDEO_PROCESSES'] else dmp._settings['POOL_PROCESSES']) as pool:
                res = pool.starmap(dmp._download_video,
                                   zip(itertools.repeat(dmp.__class__),
                                       video['items'],
                                       itertools.repeat(folder)))

            print('\x1b[2K    {}/{} (total: {})'.format(sum(filter(None, res)),
                                                        len(video['items']),
                                                        len(next(os.walk(folder))[2])))

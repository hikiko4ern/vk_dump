import os
import os.path
import itertools
from multiprocess import Pool
from operator import itemgetter

from modules.utils import copy_func


def dump_photo(dmp):
    """Фото (по альбомам)

    dmp: Dumper object
    """
    os.makedirs(os.path.join('dump', 'photo'), exist_ok=True)
    albums = dmp._vk.photos.getAlbums(need_system=1)

    print('Сохранение фото:')

    for al in albums['items']:
        print('  Альбом "{}":'.format(al['title']))
        folder = os.path.join('dump', 'photo', '_'.join(al['title'].split()))
        os.makedirs(folder, exist_ok=True)

        photo = dmp._vk_tools.get_all(
            method='photos.get',
            max_count=1000,
            values={
                'album_id': al['id'],
                'photo_sizes': 1
            })

        if photo['count'] == 0:
            print('    0/0 (total: {})'.format(len(next(os.walk(folder))[2])))
        else:
            print('    .../{}'.format(photo['count']), end='\r')
            with Pool(dmp._settings['POOL_PROCESSES']) as pool:
                res = pool.starmap(copy_func(dmp._download),
                                   zip(itertools.repeat(dmp.__class__),
                                       map(lambda p: sorted(p['sizes'], key=itemgetter('width', 'height'))[-1]['url'], photo['items']),
                                       itertools.repeat(folder)))

            print('\x1b[2K    {}/{} (total: {})'.format(sum(filter(None, res)),
                                                        photo['count'],
                                                        len(next(os.walk(folder))[2])))

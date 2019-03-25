import os
import os.path
import itertools
from multiprocess import Pool

import vk_api.audio

from modules.utils import copy_func


def dump_audio(dmp):
    """Аудио

    dmp: Dumper object
    """
    print('[получение списка аудио]')
    tracks = vk_api.audio.VkAudio(dmp._vk_session).get()

    folder = os.path.join('dump', 'audio')
    os.makedirs(folder, exist_ok=True)

    print('Сохранение аудио:')

    if len(tracks) == 0:
        print('  0/0 (total: {})'.format(len(next(os.walk(folder))[2])))
    else:
        audios = []
        for a in tracks:
            audios.append({
                'url': a['url'],
                'name': '{artist} - {title}_{id}'.format(artist=a['artist'],
                                                         title=a['title'],
                                                         id=a['id']),
                'ext': 'mp3'
            })

        print('  .../{}'.format(len(tracks)), end='\r')
        with Pool(dmp._settings['POOL_PROCESSES']) as pool:
            res = pool.starmap(copy_func(dmp._download),
                               zip(itertools.repeat(dmp.__class__), audios, itertools.repeat(folder)))

        print('\x1b[2K  {}/{} (total: {})'.format(sum(filter(None, res)),
                                                  len(audios),
                                                  len(next(os.walk(folder))[2])))

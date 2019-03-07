import os
import os.path
import inspect
import itertools
from multiprocess import Pool
from operator import itemgetter

from modules.utils import copy_func, get_fave


def dump_menu_fave(dmp):
    """Понравившиеся вложения

    dmp: Dumper object
    """
    actions = []
    for name, value in inspect.getmembers(dmp):
        if name.startswith('dump_fave_'):
            actions.append((value.__doc__.splitlines()[0], value))

    while True:
        fun, args = dmp._interface.menu(dmp, title='Дамп понравившихся вложений:', actions=actions,
                                        add_actions={'f': {'name': 'Все вложения', 'action': dmp._dump_all_fave, 'nl': True},
                                                     '0': {'name': 'В меню', 'action': None}})
        if fun:
            if fun.__name__.startswith('dump_fave_'):
                fun(dmp)
                print('\n{clr}Сохранение завершено :з{nc}'.format(
                      clr=dmp._interface._colors['green'],
                      nc=dmp._interface._mods['nc']))
                print('\n[нажмите {clr}Enter{nc} для продолжения]'.format(
                      clr=dmp._interface._colors['cyan'],
                      nc=dmp._interface._mods['nc']), end='')
                input()
            else:
                fun(args) if args else fun()
        else:
            break
    return False


def dump_fave_posts(dmp):
    """Вложения понравившихся постов (фото, видео, документы)

    dmp: Dumper object
    """
    folder_photo = os.path.join('dump', 'photo', 'Понравившиеся')
    os.makedirs(folder_photo, exist_ok=True)
    folder_docs = os.path.join('dump', 'docs', 'Понравившиеся')
    os.makedirs(folder_docs, exist_ok=True)

    print('[получение постов]')

    posts = get_fave(dmp._vk, 'posts')

    photo = []
    docs = []

    for p in posts:
        if 'attachments' in p:
            for at in p['attachments']:
                if at['type'] == 'photo':
                    at['photo']['sizes'].sort(key=itemgetter('width', 'height'))
                    obj = {
                        'url': at['photo']['sizes'][-1]['url'],
                        'prefix': '{}_{}'.format(p['owner_id'], p['id'])
                    }
                    if 'access_key' in at['photo']:
                        obj['access_key'] = at['photo']['access_key']
                    photo.append(obj)
                elif at['type'] == 'doc':
                    obj = {
                        'url': at['doc']['url'],
                        'prefix': '{}_{}'.format(p['owner_id'], p['id']),
                        'name': '{}_{}'.format(at['doc']['title'], at['doc']['id']),
                        'ext': at['doc']['ext']
                    }
                    if 'access_key' in at['doc']:
                        obj['access_key'] = at['doc']['access_key']
                    docs.append(obj)

    print('Сохранение ({} вложений из {} постов):'.format(
          sum([len(photo), len(docs)]), len(posts)))

    if photo:
        print('  [фото ({})]'.format(len(photo)))
        with Pool(dmp._settings['POOL_PROCESSES']) as pool:
            pool.starmap(copy_func(dmp._download),
                         zip(photo, itertools.repeat(folder_photo)))

    if docs:
        print('  [документы ({})]'.format(len(docs)))
        with Pool(dmp._settings['POOL_PROCESSES']) as pool:
            pool.starmap(copy_func(dmp._download),
                         zip(docs, itertools.repeat(folder_docs)))


def dump_fave_photo(dmp):
    """Фото

    dmp: Dumper object
    """
    folder = os.path.join('dump', 'photo', 'Понравившиеся')
    os.makedirs(folder, exist_ok=True)

    print('[получение понравившихся фото]')

    photo = get_fave(dmp._vk, 'photos')

    print('Сохранение понравившихся фото:')

    if photo['count'] == 0:
        print('  0/0')
    else:
        print('  .../{}'.format(photo['count']), end='\r')
        with Pool(dmp._settings['POOL_PROCESSES']) as pool:
            res = pool.starmap(copy_func(dmp._download),
                               zip(map(lambda p: sorted(p['sizes'], key=itemgetter('width', 'height'))[-1]['url'], photo['items']),
                                   itertools.repeat(folder)))
        print('\x1b[2K  {}/{} (total: {})'.format(sum(filter(None, res)),
                                                  photo['count'],
                                                  len(next(os.walk(folder))[2])))

import os
import os.path
import json
import shutil
import itertools
from multiprocess import Pool
from multiprocess.pool import MaybeEncodingError
from operator import itemgetter

from modules.utils import get_attachments

users = {}
if os.path.exists('users.json'):
    with open('users.json', 'r', encoding='utf-8') as f:
        users = json.load(f)


def users_add(vk, pid, **kwargs):
    """
    Gets user's info and add it to users object

    vk: vk_api
    pid: profile id

    possible kwargs:
        throw - don't handle AttributeError exception if it occurs again
    """
    global users
    try:
        if pid > 0:
            # User: {..., first_name, last_name, pid, ...} ->
            #       {pid:{name: 'first_name + last_name', length: len(name)}
            u = vk.users.get(user_ids=pid)[0]
            if (u.get('deactivated') == 'deleted') and (u['first_name'] == 'DELETED'):
                name = 'DELETED'
                users[u['id']] = {'name': name, 'length': len(name)}
            else:
                name = u['first_name'] + ' ' + u['last_name']
                users[u['id']] = {'name': name, 'length': len(name)}
        elif pid < 0:
            # Group: {..., name, pid, ...} ->
            #        {-%pid%: {name: 'name', length: len(name) }
            g = vk.groups.getById(group_id=-pid)[0]
            name = g['name']
            users[-g['id']] = {'name': name, 'length': len(name)}
    except AttributeError:
        if not kwargs.get('throw'):
            users_add(vk, pid, throw=True)
        else:
            users[pid] = {'name': r'{unknown user}', 'length': 14}
    else:
        users[pid] = {'name': r'{unknown user}', 'length': 14}


def dump_attachments_only(dmp):
    """Вложения диалогов

    dmp: Dumper object
    """
    global users

    folder = os.path.join('dump', 'dialogs')
    os.makedirs(folder, exist_ok=True)

    print('[получение диалогов...]')
    print('\x1b[2K  0/???', end='\r')

    conversations = dmp._vk_tools.get_all(
        method='messages.getConversations',
        max_count=200,
        values={
            'extended': 1,
            'fields': 'first_name, last_name, name'
        })

    print('\x1b[2K  {}/{}'.format(len(conversations['items']), conversations['count']))
    if dmp._DUMP_DIALOGS_ONLY:
        print('[будет сохранено диалогов: {}]'.format(len(dmp._DUMP_DIALOGS_ONLY)), end='\n\n')
    else:
        print('[будет исключено диалогов: {}]'.format(len(dmp._EXCLUDED_DIALOGS)), end='\n\n')

    print('Сохранение диалогов:')
    for con in conversations['items']:
        did = con['conversation']['peer']['id']

        pass_dialog = False
        if dmp._DUMP_DIALOGS_ONLY:
            if did not in dmp._DUMP_DIALOGS_ONLY:
                if dmp._settings['HIDE_EXCLUDED_DIALOGS']:
                    continue
            else:
                pass_dialog = True
        elif did in dmp._EXCLUDED_DIALOGS:
            if dmp._settings['HIDE_EXCLUDED_DIALOGS']:
                continue
            else:
                pass_dialog = True

        if con['conversation']['peer']['type'] == 'user':
            if did not in users:
                users_add(dmp._vk, did)
            dialog_name = users.get(did)['name']
        elif con['conversation']['peer']['type'] == 'group':
            if did not in users:
                users_add(dmp._vk, did)
            dialog_name = users.get(did)['name']
        elif con['conversation']['peer']['type'] == 'chat':
            dialog_name = con['conversation']['chat_settings']['title']
        else:
            dialog_name = r'{unknown}'

        for c in dmp._INVALID_CHARS:
            if c in dialog_name:
                dialog_name = dialog_name.replace(c, dmp._settings['REPLACE_CHAR'])

        fn = '{}_{id}'.format('_'.join(dialog_name.split(' ')), id=did)
        for n in os.listdir(folder):
            if str(did) == n.split('.txt')[0].split('_')[-1]:
                if dmp._settings['KEEP_DIALOG_NAMES']:
                    fn = n.split('.txt')[0]
                else:
                    shutil.move(os.path.join(folder, n),
                                os.path.join(folder, '{}_{id}'.format('_'.join(dialog_name.split(' ')), id=did) + ('.txt' if '.txt' in n else '')))

        print('  Диалог: {}{nfn}'.format(dialog_name, nfn=(' (as {})'.format(fn) if ' '.join(fn.split('_')[:-1]) != dialog_name else '')))
        if pass_dialog is True:
            print('    [исключён]\n')
            continue

        at_folder = os.path.join(folder, fn)
        os.makedirs(at_folder, exist_ok=True)

        # PHOTO DUMP
        print('    [получение фото]', end='\r')
        photo = get_attachments(dmp._vk, did, 'photo')

        if photo['count'] > 0:
            af = os.path.join(at_folder, 'Фото')
            os.makedirs(af, exist_ok=True)

            print('\x1b[2K    [сохранение фото]')
            print('      .../{}'.format(photo['count']), end='\r')

            with Pool(dmp._settings['POOL_PROCESSES']) as pool:
                res = pool.starmap(dmp._download,
                                   zip(itertools.repeat(dmp.__class__),
                                       map(lambda t: sorted(t['attachment']['photo']['sizes'], key=itemgetter('width', 'height'))[-1]['url'], photo['items']),
                                       itertools.repeat(af)))

            print('\x1b[2K      {}/{} (total: {})'.format(sum(filter(None, res)),
                                                          len(photo['items']),
                                                          len(next(os.walk(af))[2])))
            del res
        else:
            print('    [фото отсутствуют]')
        del photo

        # VIDEO DUMP
        print('    [получение видео]', end='\r')
        video = get_attachments(dmp._vk, did, 'video')

        if video['count'] > 0:
            video_ids = []
            for v in video['items']:
                video_ids.append('{oid}_{id}{access_key}'.format(
                    oid=v['attachment']['video']['owner_id'],
                    id=v['attachment']['video']['id'],
                    access_key=('_'+v['attachment']['video']['access_key'] if 'access_key' in v['attachment']['video'] else '')
                ))
            video = dmp._vk_tools.get_all(
                method='video.get',
                max_count=200,
                values={
                    'videos': ','.join(video_ids),
                    'extended': 1
                }
            )

            af = os.path.join(at_folder, 'Видео')
            os.makedirs(af, exist_ok=True)

            print('\x1b[2K    [сохранение видео]')
            print('      .../{}'.format(video['count']), end='\r')

            try:
                with Pool(dmp._AVAILABLE_THREADS if dmp._settings['LIMIT_VIDEO_PROCESSES'] else dmp._settings['POOL_PROCESSES']) as pool:
                    res = pool.starmap(dmp._download_video,
                                       zip(itertools.repeat(dmp.__class__),
                                           video['items'],
                                           itertools.repeat(af)))
                    print('\x1b[2K      {}/{} (total: {})'.format(sum(filter(None, res)),
                                                                  len(video['items']),
                                                                  len(next(os.walk(af))[2])))
                    del res
            except MaybeEncodingError:
                print('\x1b[2K      ???/{} (total: {})'.format(len(video['items']), len(next(os.walk(af))[2])))

        else:
            print('    [видео отсутствуют]')
        del video

        # DOCS DUMP
        print('    [получение документов]', end='\r')
        docs = get_attachments(dmp._vk, did, 'doc')

        if docs['count'] > 0:
            af = os.path.join(at_folder, 'Документы')
            os.makedirs(af, exist_ok=True)

            print('\x1b[2K    [сохранение документов]')
            print('      .../{}'.format(docs['count']), end='\r')

            with Pool(dmp._settings['POOL_PROCESSES']) as pool:
                res = pool.starmap(dmp._download_doc,
                                   zip(itertools.repeat(dmp.__class__),
                                       map(lambda t: t['attachment']['doc'], docs['items']),
                                       itertools.repeat(af)))

            print('\x1b[2K      {}/{} (total: {})'.format(sum(filter(None, res)),
                                                          len(docs['items']),
                                                          len(next(os.walk(af))[2])))
            del res
        else:
            print('    [документы отсутствуют]')
        del docs

        print()

    with open('users.json', 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=4)

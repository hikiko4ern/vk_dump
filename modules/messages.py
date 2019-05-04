import os
import os.path
import time
import re
import json
import shutil
import itertools
from multiprocess import Pool
from multiprocess.pool import MaybeEncodingError
from operator import itemgetter

from vk_api.exceptions import VkToolsException

users = {}
if os.path.exists('users.json'):
    with open('users.json', 'r', encoding='utf-8') as f:
        users = json.load(f)


def time_handler(t):
    """
    Translates seconds_from_epoch to human-readable format

    t: seconds from epoch
    """
    m = {'january': 'января', 'february': 'февраля', 'march': 'марта',
         'april': 'апреля', 'may': 'мая', 'june': 'июня', 'july': 'июля',
         'august': 'августа', 'september': 'сентября', 'october': 'октября',
         'november': 'ноября', 'december': 'декабря'}
    t = time.strftime('%d %B %Y', time.gmtime(t)).lower().split(' ')
    t[1] = '{'+t[1]+'}'
    return ' '.join(t).format_map(m)


def users_add(vk, pid):
    """
    Gets user's info and add it to users object

    vk: vk_api
    pid: profile id
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
    except Exception:
        users[pid] = {'name': r'{unknown user}', 'length': 3}


def message_handler(dmp, msg, **kwargs):
    """
    Обработчик сообщений.
    Возвращает объект
        {
            "date": str, # [HH:MM]
            "messages": [...],
            "attachments": {
                "photos": [...],
                "video_ids": [...],
                "docs": [...]
            }
        }

    [документация API]
        [вложения]
            [сообщения]
                - vk.com/dev/objects/attachments_m
            [wall_reply]
                - vk.com/dev/objects/attachments_w
    """
    global users

    r = {
        'date': time.strftime('[%H:%M]', time.gmtime(msg['date'])),
        'messages': [],
        'attachments': {
            'photos': [],
            'video_ids': [],
            'docs': [],
            'audio_messages': []
        }
    }

    if msg.get('fwd_messages'):
        for fwd in msg['fwd_messages']:
            res = message_handler(dmp, fwd)

            if len(res['messages']) > 0:
                if fwd['from_id'] not in users:
                    users_add(dmp._vk, fwd['from_id'])
                r['messages'].append('{name}> {}'.format(
                    res['messages'][0], name=users.get(fwd['from_id'])['name']))
                for m in res['messages'][1:]:
                    r['messages'].append('{name}> {}'.format(
                        m, name=' ' * len(users.get(fwd['from_id'])['name'])))

            for tp in res['attachments']:
                for a in res['attachments'][tp]:
                    r['attachments'][tp].append(a)

    if msg.get('reply_message'):
        res = message_handler(dmp, msg['reply_message'])

        if len(res['messages']) > 0:
            if msg['reply_message']['from_id'] not in users:
                users_add(dmp._vk, msg['reply_message']['from_id'])

            r['messages'].append('{name}> {}'.format(
                res['messages'][0], name=users.get(msg['reply_message']['from_id'])['name']))
            for m in res['messages'][1:]:
                r['messages'].append('{name}> {}'.format(
                    m, name=' ' * len(users.get(msg['reply_message']['from_id'])['name'])))

        for tp in res['attachments']:
            for a in res['attachments'][tp]:
                r['attachments'][tp].append(a)

    if len(msg['text']) > 0:
        for line in msg['text'].split('\n'):
            r['messages'].append(line)

    if msg['attachments']:
        for at in msg['attachments']:
            tp = at['type']

            if tp == 'photo':
                if 'action' not in msg:
                    at[tp]['sizes'].sort(key=itemgetter('width', 'height'))
                    r['messages'].append('[фото: {}]'.format(at[tp]['sizes'][-1]['url']))
                    r['attachments']['photos'].append(at[tp]['sizes'][-1]['url'])
            elif tp == 'video':
                r['messages'].append('[видео: vk.com/video{oid}_{id}]'.format(
                    oid=at[tp]['owner_id'], id=at[tp]['id']))
                r['attachments']['video_ids'].append('{oid}_{id}{access_key}'.format(
                    oid=at[tp]['owner_id'],
                    id=at[tp]['id'],
                    access_key=('_'+at[tp]['access_key'] if 'access_key' in at[tp] else '')
                ))
            elif tp == 'audio':
                r['messages'].append('[аудио: {artist} - {title}]'.format(
                    artist=at[tp]['artist'], title=at[tp]['title']))
            elif tp == 'doc':
                r['messages'].append('[документ: vk.com/doc{oid}_{id}]'.format(
                    oid=at[tp]['owner_id'], id=at[tp]['id']))
                r['attachments']['docs'].append({
                    'url': at[tp]['url'],
                    'name': at[tp]['title'] + '_' + str(at[tp]['id']),
                    'ext': at[tp]['ext']
                })
            elif tp == 'link':
                r['messages'].append('[ссылка: {title} ({url})]'.format(
                    title=at[tp]['title'], url=at[tp]['url']))
            elif tp == 'market':
                r['messages'].append('[товар: {title} ({price}{cur}) [vk.com/market?w=product{owid}_{id}]]'.format(
                    title=at[tp]['title'],
                    owid=at[tp]['owner_id'],
                    id=at[tp]['id'],
                    price=at[tp]['price']['amount'],
                    cur=at[tp]['price']['currency']['name'].lower()))
            elif tp == 'market_album':
                r['messages'].append('[коллекция товаров: {}]'.format(at[tp]['title']))
            elif tp == 'wall':
                r['messages'].append('[пост: vk.com/wall{oid}_{id}]'.format(
                    oid=at[tp]['to_id'], id=at[tp]['id']))
            elif tp == 'wall_reply':
                if at[tp]['from_id'] not in users:
                    users_add(dmp._vk, at[tp]['from_id'])
                u = users.get(at[tp]['from_id'])
                r['messages'].append('[комментарий к посту от {user}: {msg} (vk.com/wall{oid}_{pid}?reply={id})]'.format(
                    user=u['name'],
                    msg=at[tp]['text'],
                    oid=at[tp]['owner_id'],
                    pid=at[tp]['post_id'],
                    id=at[tp]['id']))
            elif tp == 'sticker':
                r['messages'].append('[стикер: {}]'.format(at[tp]['images'][-1]['url']))
            elif tp == 'gift':
                r['messages'].append('[подарок: {}]'.format(at[tp]['id']))
            elif tp == 'graffiti':
                r['messages'].append('[граффити: {}]'.format(at[tp]['url']))
            elif tp == 'audio_message':
                r['messages'].append('[голосовое сообщение: {}]'.format(at[tp]['link_mp3']))
                r['attachments']['audio_messages'].append({
                    'url': at[tp]['link_mp3'],
                    'name': '{from_id}_{date}_{id}'.format(
                        from_id=str(msg['from_id']),
                        date=time.strftime('%Y_%m_%d', time.gmtime(msg['date'])),
                        id=str(at[tp]['id'])),
                    'ext': 'mp3'})
            else:
                r['messages'].append(f'[вложение с типом "{tp}": {json.dumps(at[tp])}]')

    if msg.get('action'):
        # member - совершающий действие
        # user - объект действия
        act = msg['action']
        tp = act['type']

        if ('member_id' in act) and (act['member_id'] > 0) and (act['member_id'] not in users):
            try:
                users_add(dmp._vk, act['member_id'])
            except Exception:
                users[act['member_id']] = {'name': '{unknown user}', 'length': 3}

        if tp == 'chat_photo_update':
            msg['attachments'][0]['photo']['sizes'].sort(key=itemgetter('width', 'height'))
            r['messages'].append('[{member} обновил фотографию беседы ({url})]'.format(
                member=users[msg['from_id']]['name'],
                url=msg['attachments'][0]['photo']['sizes'][-1]['url']
            ))
            r['attachments']['photos'].append(msg['attachments'][0]['photo']['sizes'][-1]['url'])
        elif tp == 'chat_photo_remove':
            r['messages'].append('[{member} удалил фотографию беседы]'.format(
                member=users[msg['from_id']]['name']
            ))
        elif tp == 'chat_create':
            r['messages'].append('[{member} создал чат "{chat_name}"]'.format(
                member=users[msg['from_id']]['name'],
                chat_name=act['text']
            ))
        elif tp == 'chat_title_update':
            r['messages'].append('[{member} изменил название беседы на «{chat_name}»]'.format(
                member=users[msg['from_id']]['name'],
                chat_name=act['text']
            ))
        elif tp == 'chat_invite_user':
            r['messages'].append('[{member} пригласил {user}]'.format(
                member=users[msg['from_id']]['name'],
                user=users[act['member_id']
                           ]['name'] if act['member_id'] > 0 else act['email'],
            ))
        elif tp == 'chat_kick_user':
            r['messages'].append('[{member} исключил {user}]'.format(
                member=users[msg['from_id']]['name'],
                user=users[act['member_id']
                           ]['name'] if act['member_id'] > 0 else act['email'],
            ))
        # TODO: полная обработка закреплённого сообщения
        elif tp == 'chat_pin_message':
            r['messages'].append('[{member} закрепил сообщение #{id}: "{message}"]'.format(
                member=users[msg['from_id']]['name'],
                id=act['conversation_message_id'],
                message=act['message'] if 'message' in act else ''
            ))
        elif tp == 'chat_unpin_message':
            r['messages'].append('[{member} открепил сообщение]'.format(
                member=users[msg['from_id']]['name']
            ))
        elif tp == 'chat_invite_user_by_link':
            r['messages'].append('[{user} присоединился по ссылке]'.format(
                user=users[msg['from_id']]['name']
            ))
    return r


def dump_messages(dmp, **kwargs):
    """Сообщения

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

        values = {
            'peer_id': con['conversation']['peer']['id'],
            'extended': 1,
            'fields': 'first_name, last_name'
        }

        append = {'use': dmp._settings['DIALOG_APPEND_MESSAGES'] and
                  os.path.exists(os.path.join(folder, f'{fn}.txt'))}
        try:
            if append['use']:
                with open(os.path.join(folder, f'{fn}.txt'), 'rb') as t:
                    t.seek(-2, 2)
                    while t.read(1) != b'\n':
                        t.seek(-2, 1)
                    last = t.readline().decode()

                    r = re.match('^\[last:[0-9]+\]$', last)
                    if r:
                        start_message_id = int(re.search(r'\d+', r.group(0)).group(0))
                        values['start_message_id'] = start_message_id

                        t.seek(-len(last.encode('utf-8'))-2, 1)
                        while True:
                            while t.read(1) != b'\n':
                                t.seek(-2, 1)
                            tmp = t.readline().decode()
                            r = re.match('^ {8}\[\d+ [а-я a-z]+ \d+\]$', tmp)
                            # TODO: получение last_id по последнему сообщению (???)
                            if r:
                                append['prev_date'] = re.search('\d+ [а-я a-z]+ \d+', r.group(0)).group(0)
                                break
                            else:
                                t.seek(-len(tmp.encode('utf-8'))-2, 1)
                    else:
                        values['rev'] = 1
                        append['use'] = False
            else:
                values['rev'] = 1
        except OSError:
            values['rev'] = 1
            append['use'] = False

        print('    [кэширование]')
        print('\x1b[2K      0/???', end='\r')

        try:
            history = dmp._vk_tools.get_all(
                method='messages.getHistory',
                max_count=200,
                values=values,
                negative_offset=append['use'])
            print('\x1b[2K      {}/{}'.format(len(history['items']),
                                              history['count']))
            if len(history['items']) == 0:
                print()
                continue
        except VkToolsException:
            print('\x1b[2K      0/0\n')
            continue

        if append['use']:
            def sortById(msg):
                return msg['id']
            history['items'].sort(key=sortById)

        attachments = {
            'photos': [],
            'video_ids': [],
            'docs': [],
            'audio_messages': []
        }

        if append['use']:
            tmp = ''
        else:
            f = open(os.path.join(folder, f'{fn}.txt'), 'w', encoding='utf-8')

        count = len(history['items'])
        print('    [сохранение сообщений]')
        print('      {}/{}'.format(0, count), end='\r')
        prev = None
        prev_date = None

        if append['use']:
            prev_date = append['prev_date']

        for i in range(count):
            m = history['items'][i]

            if m['from_id'] not in users:
                users_add(dmp._vk, m['from_id'])

            res = message_handler(dmp._vk, m)

            date = time_handler(m['date'])
            hold = ' ' * (users.get(m['from_id'])['length'] + 2)

            msg = res['date'] + ' '
            msg += hold if (prev and date and prev == m['from_id'] and prev_date == date) \
                        else users.get(m['from_id'])['name'] + ': '

            if res['messages']:
                msg += res['messages'][0] + '\n'
                for r in res['messages'][1:]:
                    msg += hold + ' '*8 + r + '\n'
            else:
                msg += '\n'

            for a in res['attachments']['audio_messages']:
                if a not in attachments['audio_messages']:
                    attachments['audio_messages'].append(a)

            if dmp._settings['SAVE_DIALOG_ATTACHMENTS']:
                for tp in res['attachments']:
                    for a in res['attachments'][tp]:
                        if a not in attachments[tp]:
                            attachments[tp].append(a)

            if prev_date != date:
                if prev_date:
                    if append['use']:
                        tmp += '\n'
                    else:
                        f.write('\n')
                if append['use']:
                    tmp += f'        [{date}]\n'
                else:
                    f.write(f'        [{date}]\n')
                prev_date = date

            if append['use']:
                tmp += msg
            else:
                f.write(msg)
            prev = m['from_id']
            print('\x1b[2K      {}/{}'.format(i+1, count), end='\r')

        if append['use']:
            import codecs

            orig_file = os.path.join(folder, f'{fn}.txt')
            tmp_file = os.path.join(folder, f'{fn}.new')

            try:
                with codecs.open(orig_file, 'r', encoding='utf-8') as fi,\
                     codecs.open(tmp_file, 'w', encoding='utf-8') as fo:

                    for line in fi:
                        if re.match('^\[last:[0-9]+\]$', line):
                            line = tmp+'[last:{}]\n'.format(history['items'][-1]['id'])
                        fo.write(line)
                os.remove(orig_file)
                os.rename(tmp_file, orig_file)
            except Exception:
                os.remove(tmp_file)
        else:
            f.write('[last:{}]\n'.format(history['items'][-1]['id']))
            f.close()
        print()

        if attachments['audio_messages']:
            at_folder = os.path.join(folder, fn)
            af = os.path.join(at_folder, 'Голосовые')
            os.makedirs(af, exist_ok=True)

            print('    [сохранение голосовых сообщений]')
            print('      .../{}'.format(len(attachments['audio_messages'])), end='\r')

            with Pool(dmp._settings['POOL_PROCESSES']) as pool:
                res = pool.starmap(dmp._download,
                                   zip(itertools.repeat(dmp.__class__),
                                       attachments['audio_messages'],
                                       itertools.repeat(af)))

            print('\x1b[2K      {}/{} (total: {})'.format(sum(filter(None, res)),
                                                          len(attachments['audio_messages']),
                                                          len(next(os.walk(af))[2])))

        if dmp._settings['SAVE_DIALOG_ATTACHMENTS']:
            at_folder = os.path.join(folder, fn)
            os.makedirs(at_folder, exist_ok=True)

            if attachments['photos']:
                af = os.path.join(at_folder, 'Фото')
                os.makedirs(af, exist_ok=True)

                print('    [сохранение фото]')
                print('      .../{}'.format(len(attachments['photos'])), end='\r')

                with Pool(dmp._settings['POOL_PROCESSES']) as pool:
                    res = pool.starmap(dmp._download,
                                       zip(itertools.repeat(dmp.__class__),
                                           attachments['photos'],
                                           itertools.repeat(af)))

                print('\x1b[2K      {}/{} (total: {})'.format(sum(filter(None, res)),
                                                              len(attachments['photos']),
                                                              len(next(os.walk(af))[2])))

            if attachments['video_ids']:
                af = os.path.join(at_folder, 'Видео')
                os.makedirs(af, exist_ok=True)

                videos = dmp._vk_tools.get_all(
                    method='video.get',
                    max_count=200,
                    values={
                        'videos': ','.join(attachments['video_ids']),
                        'extended': 1
                    }
                )

                print('    [сохранение видео]')
                print('      .../{}'.format(len(videos['items'])), end='\r')

                try:
                    with Pool(dmp._AVAILABLE_THREADS if dmp._settings['LIMIT_VIDEO_PROCESSES'] else dmp._settings['POOL_PROCESSES']) as pool:
                        res = pool.starmap(dmp._download_video,
                                           zip(itertools.repeat(dmp.__class__),
                                               videos['items'],
                                               itertools.repeat(af)))
                    print('\x1b[2K      {}/{} (total: {})'.format(sum(filter(None, res)),
                                                                  len(videos['items']),
                                                                  len(next(os.walk(af))[2])))
                except MaybeEncodingError:
                    print('\x1b[2K      ???/{} (total: {})'.format(len(videos['items']), len(next(os.walk(af))[2])))

            if attachments['docs']:
                af = os.path.join(at_folder, 'Документы')
                os.makedirs(af, exist_ok=True)

                print('    [сохранение документов]')
                print('      .../{}'.format(len(attachments['docs'])), end='\r')

                with Pool(dmp._settings['POOL_PROCESSES']) as pool:
                    res = pool.starmap(dmp._download,
                                       zip(itertools.repeat(dmp.__class__),
                                           attachments['docs'],
                                           itertools.repeat(af)))

                print('\x1b[2K      {}/{} (total: {})'.format(sum(filter(None, res)),
                                                              len(attachments['docs']),
                                                              len(next(os.walk(af))[2])))

    with open('users.json', 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=4)

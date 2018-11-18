#!/usr/bin/env python3

import argparse
from configparser import ConfigParser

from os import cpu_count, name as osname, get_terminal_size, makedirs, remove, walk
from os.path import exists, join as pjoin
from sys import stdout
from time import sleep

import urllib3
from urllib.request import urlopen
import requests
import shutil
from re import search as research

import itertools
from multiprocessing import Pool
from multiprocessing.pool import MaybeEncodingError

import vk_api
from jconfig.jconfig import Config
from jconfig.memory import MemoryConfig
from youtube_dl import YoutubeDL

NAME = 'VK Dump Tool'
VERSION = '0.7.2'
API_VERSION = '5.87'

parser = argparse.ArgumentParser(description=NAME)
parser.add_argument('--version', action='version', version=VERSION)
auth = parser.add_argument_group('Аутентификация')
auth.add_argument('-l', '--login', type=str, metavar='\b', help='логин')
auth.add_argument('-p', '--password', type=str, metavar='\b', help='пароль')
auth.add_argument('-t', '--token', type=str, metavar='\b', help='access_token')
dump = parser.add_argument_group('Дамп данных')
dump.add_argument('--dump', type=str, nargs='*',
                  choices=('photos', 'audio', 'video', 'docs', 'messages', 'attachments', 'liked_posts', 'all'),
                  help='Данные для сохранения.')

AVAILABLE_THREADS = cpu_count()

settings = {
    'MEMORY_CONFIG': True,  # сохранять конфиг в память вместо файла
    'REPLACE_SPACES': False,  # заменять пробелы на _
    'REPLACE_CHAR': '_',  # символ для замены запрещённых в Windows символов,
    'POOL_PROCESSES': 4*AVAILABLE_THREADS,  # макс. число создаваемых процессов
    'LIMIT_VIDEO_PROCESSES': True,  # ограничивать число процессов при загрузке видео
    'SAVE_DIALOG_ATTACHMENTS': True  # сохранять вложения из диалогов
}

settings_names = {
    'MEMORY_CONFIG': 'Сохранять конфиг vk_api в памяти вместо записи в файл',
    'REPLACE_SPACES': 'Заменять пробелы на символ "_"',
    'REPLACE_CHAR': 'Символ для замены запрещённых в имени файла',
    'POOL_PROCESSES': 'Количество процессов для мультипоточной загрузке',
    'LIMIT_VIDEO_PROCESSES': 'Ограничивать число процессов при загрузке видео',
    'SAVE_DIALOG_ATTACHMENTS': 'Сохранять вложения из диалогов'
}

INVALID_CHARS = ['\\', '/', ':', '*', '?', '<', '>', '|', '"']
INVALID_POSIX_CHARS = ['$']


#
def init():
    global args, w, h, colors, mods, settings, ANSI_AVAILABLE, INVALID_CHARS

    args = parser.parse_args()

    if osname == 'nt':
        from platform import platform
        if int(platform().split('-')[1]) < 10:
            import colorama
            colorama.init()
            ANSI_AVAILABLE = False
        else:
            from subprocess import call
            call('', shell=True)
            ANSI_AVAILABLE = True
    elif osname == 'posix':
        INVALID_CHARS += INVALID_POSIX_CHARS
        ANSI_AVAILABLE = True

    config = ConfigParser()
    if not config.read('settings.ini'):
        with open('settings.ini', 'w') as cf:
            config['SETTINGS'] = settings
            config.write(cf)
    else:
        for s in config['SETTINGS']:
            c = config['SETTINGS'][s]
            try:
                settings[s.upper()] = int(c)
            except ValueError:
                settings[s.upper()] = True if c == 'True' else \
                    False if c == 'False' else \
                    c

    w, h = get_terminal_size()
    colors = {
        'red': '\x1b[31m',
        'green': '\x1b[32m',
        'yellow': '\x1b[33m',
        'blue': '\x1b[34m' if ANSI_AVAILABLE else '\x1b[36m',
        'purple': '\x1b[35m',
        'cyan': '\x1b[36m',
        'white': '\x1b[37m',
    }
    mods = {
        'nc': '\x1b[0m',
        'bold': '\x1b[1m'
    }
    makedirs('dump', exist_ok=True)


def settings_save():
    global settings

    config = ConfigParser()

    with open('settings.ini', 'w') as cf:
        config['SETTINGS'] = settings
        config.write(cf)

    if settings['MEMORY_CONFIG']:
        if exists('vk_config.v2.json'):
            remove('vk_config.v2.json')


def log(*msg):
    global login, vk_session, vk, vk_tools, account

    if not args.dump:
        clear()
        cprint(msg[0] if msg else '[для продолжения необходимо войти]',
               color='red', mod='bold', offset=2, delay=1/50)

    try:
        if args.token:
            vk_session = vk_api.VkApi(token=args.token, app_id=6631721,
                                      auth_handler=auth_handler, api_version=API_VERSION)
        else:
            if args.login and args.password:
                login = args.login
                password = args.password
            else:
                login = input('    login: {clr}'.format(clr=colors['cyan'] if ANSI_AVAILABLE else ''))
                print(mods['nc'], end='')
                password = input('    password: {clr}'.format(
                    clr=colors['cyan'] if ANSI_AVAILABLE else ''))
                print(mods['nc'], end='')
            vk_session = vk_api.VkApi(login, password,
                                      config=(
                                          MemoryConfig if settings['MEMORY_CONFIG'] else Config),
                                      app_id=6631721,
                                      api_version=API_VERSION,
                                      auth_handler=auth_handler,
                                      captcha_handler=captcha_handler)
            vk_session.auth(token_only=True, reauth=True)
        vk = vk_session.get_api()
        vk_tools = vk_api.VkTools(vk)
        account = vk.account.getProfileInfo()
    except KeyboardInterrupt:
        goodbye()
    except vk_api.exceptions.ApiError:
        log('Произошла ошибка при попытке авторизации.')
    except vk_api.exceptions.BadPassword:
        log('Неправильный пароль.')
    except vk_api.exceptions.Captcha:
        log('Необходим ввод капчи.')
    except Exception as e:
        raise e


def auth_handler():
    key = input('Введите код двухфакторой аутентификации: ')
    remember_device = True
    return key, remember_device


def captcha_handler(captcha):
    key = input('Введите капчу ({}): '.format(captcha.get_url())).strip()
    return captcha.try_again(key)


def download(obj, folder, **kwargs):
    if not obj:
        return False

    if isinstance(obj, str):
        url = obj
        del obj
    elif isinstance(obj, dict):
        url = obj.pop('url')
        kwargs = obj

    if 'name' in kwargs:
        fn = '_'.join(kwargs['name'].split(' ')) if settings['REPLACE_SPACES'] else kwargs['name']
        if 'ext' in kwargs:
            if fn.split('.')[-1] != kwargs['ext']:
                fn += '.{}'.format(kwargs['ext'])
    else:
        fn = url.split('/')[-1]

    if 'prefix' in kwargs:
        fn = str(kwargs['prefix']) + '_' + fn

    if 'access_key' in kwargs:
        url = '{}?access_key={ak}'.format(url, ak=kwargs['access_key'])

    for c in INVALID_CHARS:
        fn = fn.replace(c, settings['REPLACE_CHAR'])

    if not exists(pjoin(folder, fn)):
        try:
            r = requests.get(url, stream=True, timeout=(30, 5))
            with open(pjoin(folder, fn), 'wb') as f:
                shutil.copyfileobj(r.raw, f)
        except requests.exceptions.ConnectionError:
            return False
        except requests.exceptions.ReadTimeout:
            return False
        except urllib3.exceptions.ReadTimeoutError:
            return False
        except Exception as e:
            raise e


def download_video(v, folder):
    if 'platform' in v:
        # if v['platform'] in ('YouTube', 'Coub', 'Vimeo'):
        return download_external(v['player'], folder)
    else:
        if not 'player' in v:
            return False
        if 'height' not in v:
            v['height'] = 480 if 'photo_800' in v else \
                360 if 'photo_320' in v else \
                240

        url = v['player'] if not 'access_key' in v else '{}?access_key={ak}'.format(
            v['player'], ak=v['access_key'])
        data = urlopen(url).read()
        try:
            download(
                research(b'https://cs.*vkuservideo.*' +
                         str(min(v['height'], v['width']) if 'width' in v else v['height']).encode()+b'.mp4', data).group(0).decode(),
                folder,
                name=v['title']+'_'+str(v['id']),
                ext='mp4'
            )
        except AttributeError:
            return False


def download_external(url, folder):
    if not url:
        return False

    try:
        YoutubeDL({
            'outtmpl': pjoin(folder, '%(title)s_%(id)s.%(ext)s'),
            'nooverwrites': True,
            'no_warnings': True,
            'ignoreerros': True,
            'quiet': True
        }).download((url,))
        return True
    except Exception:
        return False


# Dump funcs
def dump_photos():
    makedirs(pjoin('dump', 'photos'), exist_ok=True)
    albums = vk.photos.getAlbums(need_system=1)

    print('Сохранение фото:')

    for al in albums['items']:
        print('  Альбом "{}":'.format(al['title']))
        folder = pjoin('dump', 'photos', '_'.join(al['title'].split(' ')))
        makedirs(folder, exist_ok=True)

        photos = vk_tools.get_all(
            method='photos.get',
            max_count=1000,
            values={
                'album_id': al['id'],
                'photo_sizes': 1
            })

        if photos['count'] == 0:
            print('    0/0')
        else:
            objs = []
            for p in photos['items']:
                objs.append(p['sizes'][-1]['url'])

            print('    .../{}'.format(photos['count']), end='\r')
            with Pool(settings['POOL_PROCESSES']) as pool:
                pool.starmap(download, zip(objs, itertools.repeat(folder)))
            print('\x1b[2K    {}/{}'.format(len(next(walk(folder))[2]), photos['count']))


def dump_audio():
    global folder
    import vk_api.audio

    print('[получение списка аудио]')
    tracks = vk_api.audio.VkAudio(vk_session).get()

    folder = pjoin('dump', 'audio')
    makedirs(folder, exist_ok=True)

    print('\nСохранение аудио:')

    if len(tracks) == 0:
        print('  0/0')
    else:
        audios = []
        for a in tracks:
            audios.append({
                'url': a['url'],
                'name': '{artist} - {title}_{id}'.format(artist=a['artist'], title=a['title'], id=a['id']),
                'ext': 'mp3'
            })

        print('  .../{}'.format(len(tracks)), end='\r')
        with Pool(settings['POOL_PROCESSES']) as pool:
            pool.starmap(download, zip(audios, itertools.repeat(folder)))
        print('\x1b[2K  {}/{}'.format(len(next(walk(folder))[2]), len(tracks)))


def dump_video():
    folder = pjoin('dump', 'video')
    makedirs(folder, exist_ok=True)

    print('Сохранение видео:')

    albums = vk_tools.get_all(
        method='video.getAlbums',
        max_count=100,
        values={
            'need_system': 1
        })

    for al in albums['items']:
        print('  Альбом "{}":'.format(al['title']))
        folder = pjoin('dump', 'video', '_'.join(al['title'].split(' ')))
        makedirs(folder, exist_ok=True)

        video = vk_tools.get_all(
            method='video.get',
            max_count=200,
            values={
                'album_id': al['id']
            })

        if video['count'] == 0:
            print('    0/0')
        else:
            objs = []
            for v in video['items']:
                objs.append(v)

            print('    .../{}'.format(video['count']), end='\r')
            with Pool(settings['POOL_PROCESSES'] if not settings['LIMIT_VIDEO_PROCESSES'] else AVAILABLE_THREADS) as pool:
                pool.starmap(download_video, zip(objs, itertools.repeat(folder)))
            print('\x1b[2K    {}/{}'.format(len(next(walk(folder))[2]), video['count']))


def dump_docs():
    folder = pjoin('dump', 'docs')
    makedirs(folder, exist_ok=True)

    print('[получение списка документов]')

    docs = vk.docs.get()

    print('Сохраненние документов:')

    if docs['count'] == 0:
        print('  0/0')
    else:
        objs = []
        for d in docs['items']:
            objs.append({
                'url': d['url'],
                'name': d['title']+'_'+str(d['id']),
                'ext': d['ext']
            })

        print('  .../{}'.format(docs['count']), end='\r')
        with Pool(settings['POOL_PROCESSES']) as pool:
            pool.starmap(download, zip(objs, itertools.repeat(folder)))
        print('\x1b[2K  {}/{}'.format(len(next(walk(folder))[2]), docs['count']))


def dump_messages(**kwargs):
    def users_add(id):
        try:
            if id > 0:
                # User: {..., first_name, last_name, id, ...} => {id:{name: 'first_name + last_name', length: len(name)}
                u = vk.users.get(user_ids=id)[0]
                if ('deactivated' in u) and (u['deactivated'] == 'deleted') and (u['first_name'] == 'DELETED'):
                    name = 'DELETED'
                    users[u['id']] = {'name': name, 'length': len(name)}
                else:
                    name = u['first_name'] + ' ' + u['last_name']
                    users[u['id']] = {'name': name, 'length': len(name)}

            elif id < 0:
                # Groups: {..., name, id, ...} => {-%id%: {name: 'name', length: len(name) }
                g = vk.messages.getConversationsById(peer_ids=id, extended=1)['groups'][0]
                name = g['name']
                users[-g['id']] = {'name': name, 'length': len(name)}

        except Exception:
            users[id] = {'name': r'{unknown user}', 'length': 3}

    def message_handler(msg, **kwargs):
        """
            Обработчик сообщений.
            Возвращает объект
                {
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
        r = {
            'messages': [],
            'attachments': {
                'photos': [],
                'video_ids': [],
                'docs': []
            }
        }

        if ('fwd_messages' in msg) and msg['fwd_messages']:
            for fwd in msg['fwd_messages']:
                res = message_handler(fwd)

                if 'attachments_only' not in kwargs:
                    if len(res['messages']) > 0:
                        if fwd['from_id'] not in users:
                            users_add(fwd['from_id'])

                        r['messages'].append('{name}> {}'.format(
                            res['messages'][0], name=users.get(fwd['from_id'])['name']))
                        for m in res['messages'][1:]:
                            r['messages'].append('{name}> {}'.format(
                                m, name=' '*len(users.get(fwd['from_id'])['name'])))

                for a in res['attachments']['photos']:
                    r['attachments']['photos'].append(a)
                for a in res['attachments']['video_ids']:
                    r['attachments']['video_ids'].append(a)
                for a in res['attachments']['docs']:
                    r['attachments']['docs'].append(a)


        if len(msg['text']) > 0:
            for line in msg['text'].split('\n'):
                r['messages'].append(line)

        if msg['attachments']:
            for at in msg['attachments']:
                tp = at['type']

                if 'attachments_only' not in kwargs:
                    if tp == 'photo':
                        if 'action' not in msg:
                            r['messages'].append('[фото: {url}]'.format(url=at[tp]['sizes'][-1]['url']))
                            r['attachments']['photos'].append(at[tp]['sizes'][-1]['url'])
                    elif tp == 'video':
                        r['messages'].append(
                            '[видео: vk.com/video{owid}_{id}]'.format(owid=at[tp]['owner_id'], id=at[tp]['id']))
                        r['attachments']['video_ids'].append('{oid}_{id}{access_key}'.format(
                            oid=at[tp]['owner_id'],
                            id=at[tp]['id'],
                            access_key='_' +
                            at[tp]['access_key'] if 'access_key' in at[tp] else ''
                        ))
                    elif tp == 'audio':
                        r['messages'].append('[аудио: {artist} - {title}]'.format(artist=at[tp]
                                                                                  ['artist'], title=at[tp]['title']))
                    elif tp == 'doc':
                        r['messages'].append(
                            '[документ: vk.com/doc{owid}_{id}]'.format(owid=at[tp]['owner_id'], id=at[tp]['id']))
                        r['attachments']['docs'].append({
                            'url': at[tp]['url'],
                            'name': at[tp]['title']+'_'+str(at[tp]['id']),
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
                    # TODO: доделать market_album
                    elif tp == 'market_album':
                        r['messages'].append(
                            '[коллекция товаров: {title}]'.format(title=at[tp]['title']))
                    elif tp == 'wall':
                        r['messages'].append(
                            '[пост: vk.com/wall{owid}_{id}]'.format(owid=at[tp]['to_id'], id=at[tp]['id']))
                    # TODO: доделать wall_reply: добавить поддержку вложений (а надо ли?)
                    elif tp == 'wall_reply':
                        if at[tp]['from_id'] not in users:
                            users_add(at[tp]['from_id'])
                        u = users.get(at[tp]['from_id'])
                        r['messages'].append('[комментарий к посту от {user}: {text} (vk.com/wall{owid}_{pid}?reply={id})]'.format(
                            user=u['name'],
                            text=at[tp]['text'],
                            owid=at[tp]['owner_id'],
                            pid=at[tp]['post_id'],
                            id=at[tp]['id']))
                    elif tp == 'sticker':
                        r['messages'].append('[стикер: {url}]'.format(url=at[tp]['images'][-1]['url']))
                    elif tp == 'gift':
                        r['messages'].append('[подарок: {id}]'.format(id=at[tp]['id']))
                    elif tp == 'graffiti':
                        r['messages'].append('[граффити: {url}]'.format(url=at[tp]['url']))
                    elif tp == 'audio_message':
                        r['messages'].append(
                            '[голосовое сообщение: {url}]'.format(url=at[tp]['link_mp3']))
                    else:
                        r['messages'].append('[вложение с типом "{tp}"]'.format(tp=tp))

                else:
                    if tp == 'photo':
                        r['attachments']['photos'].append(at[tp]['sizes'][-1]['url'])
                    elif tp == 'video':
                        r['attachments']['video_ids'].append('{oid}_{id}{access_key}'.format(
                            oid=at[tp]['owner_id'],
                            id=at[tp]['id'],
                            access_key='_' +
                            at[tp]['access_key'] if 'access_key' in at[tp] else ''
                        ))
                    elif tp == 'doc':
                        r['attachments']['docs'].append({
                            'url': at[tp]['url'],
                            'name': at[tp]['title']+'_'+str(at[tp]['id']),
                            'ext': at[tp]['ext']
                        })

        if 'action' in msg and msg['action']:
            """
                member - совершающий действие
                user - объект действия
            """
            act = msg['action']
            tp = act['type']

            if 'attachments_only' not in kwargs:
                if ('member_id' in act) and (act['member_id'] > 0) and (act['member_id'] not in users):
                    try:
                        users_add(act['member_id'])
                    except Exception:
                        users[act['member_id']] = {'name': r'{unknown user}', 'length': 3}

                if tp == 'chat_photo_update':
                    r['messages'].append('[{member} обновил фотографию беседы ({url})]'.format(
                        member=users[msg['from_id']]['name'],
                        url=msg['attachments'][0]['photo']['sizes'][-1]['url']
                    ))
                    r['attachments']['photos'].append(
                        msg['attachments'][0]['photo']['sizes'][-1]['url'])
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
                        user=users[act['member_id']]['name'] if act['member_id'] > 0 else act['email'],
                    ))
                elif tp == 'chat_kick_user':
                    r['messages'].append('[{member} исключил {user}]'.format(
                        member=users[msg['from_id']]['name'],
                        user=users[act['member_id']]['name'] if act['member_id'] > 0 else act['email'],
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
            else:
                if tp == 'chat_photo_update':
                    r['attachments']['photos'].append(
                        msg['attachments'][0]['photo']['sizes'][-1]['url'])

        return r

    folder = pjoin('dump', 'dialogs')
    makedirs(folder, exist_ok=True)

    print('[получение диалогов...]')
    print('\x1b[2K  0/???', end='\r')

    conversations = vk_tools.get_all(
        method='messages.getConversations',
        max_count=200,
        values={
            'extended': 1,
            'fields': 'first_name, last_name, name'
        })

    print('\x1b[2K  {}/{}'.format(len(conversations['items']), conversations['count']))

    users = {}

    print('Сохранение диалогов:')
    for con in conversations['items']:
        did = con['conversation']['peer']['id']

        if con['conversation']['peer']['type'] == 'user':
            if did not in users:
                users_add(did)
            dialog_name = users.get(did)['name']
        elif con['conversation']['peer']['type'] == 'group':
            if did not in users:
                users_add(did)
            dialog_name = users.get(did)['name']
        elif con['conversation']['peer']['type'] == 'chat':
            dialog_name = con['conversation']['chat_settings']['title']
        else:
            dialog_name = r'{unknown}'

        print('  Диалог: {}'.format(dialog_name))
        print('    [кэширование]')
        print('\x1b[2K      0/???', end='\r')

        history = vk_tools.get_all(
            method='messages.getHistory',
            max_count=200,
            values={
                'peer_id': con['conversation']['peer']['id'],
                'rev': 1,
                'extended': 1,
                'fields': 'first_name, last_name'
            })
        print('\x1b[2K      {}/{}'.format(len(history['items']), history['count']))

        for c in INVALID_CHARS:
            dialog_name = dialog_name.replace(c, settings['REPLACE_CHAR'])

        attachments = {
            'photos': [],
            'video_ids': [],
            'docs': []
        }

        if 'attachments_only' not in kwargs:
            with open(pjoin('dump', 'dialogs', '{}_{id}.txt'.format('_'.join(dialog_name.split(' ')), id=did)), 'w', encoding='utf-8') as f:
                count = len(history['items'])
                print('    [сохранение сообщений]')
                print('      {}/{}'.format(0, count), end='\r')
                prev = None

                for i in range(count):
                    m = history['items'][i]

                    if m['from_id'] not in users:
                        users_add(m['from_id'])

                    hold = ' '*(users.get(m['from_id'])['length']+2)
                    msg = hold if (prev and prev == m['from_id']) else users.get(
                        m['from_id'])['name']+': '

                    res = message_handler(m)
                    if res['messages']:
                        msg += res['messages'][0] + '\n'
                        for r in res['messages'][1:]:
                            msg += hold + r + '\n'
                    else:
                        msg += '\n'

                    if settings['SAVE_DIALOG_ATTACHMENTS']:
                        for a in res['attachments']['photos']:
                            if a not in attachments['photos']:
                                attachments['photos'].append(a)
                        for a in res['attachments']['video_ids']:
                            if a not in attachments['video_ids']:
                                attachments['video_ids'].append(a)
                        for a in res['attachments']['docs']:
                            if a not in attachments['docs']:
                                attachments['docs'].append(a)

                    f.write(msg)
                    prev = m['from_id']
                    print('\x1b[2K      {}/{}'.format(i, count), end='\r')
        else:
            count = len(history['items'])
            print('    [обработка сообщений]')
            print('      {}/{}'.format(0, count), end='\r')

            for i in range(count):
                res = message_handler(history['items'][i], attachments_only=True)

                for a in res['attachments']['photos']:
                    if a not in attachments['photos']:
                        attachments['photos'].append(a)
                for a in res['attachments']['video_ids']:
                    if a not in attachments['video_ids']:
                        attachments['video_ids'].append(a)
                for a in res['attachments']['docs']:
                    if a not in attachments['docs']:
                        attachments['docs'].append(a)

                print('\x1b[2K      {}/{}'.format(i, count), end='\r')

        if settings['SAVE_DIALOG_ATTACHMENTS'] or ('attachments_only' in kwargs and kwargs['attachments_only']):
            at_folder = pjoin(folder, '{}_{id}'.format(
                '_'.join(dialog_name.split(' ')), id=did))
            makedirs(at_folder, exist_ok=True)

            print()

            if attachments['photos']:
                af = pjoin(at_folder, 'Фото')
                makedirs(af, exist_ok=True)

                print('    [сохранение фото]')
                print('      .../{}'.format(len(attachments['photos'])), end='\r')

                with Pool(settings['POOL_PROCESSES']) as pool:
                    pool.starmap(download, zip(
                        attachments['photos'], itertools.repeat(af)))

                print('\x1b[2K      {}/{}'.format(len(next(walk(af))[2]),
                                                  len(attachments['photos'])))

            if attachments['video_ids']:
                af = pjoin(at_folder, 'Видео')
                makedirs(af, exist_ok=True)

                videos = vk_tools.get_all(
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
                    with Pool(settings['POOL_PROCESSES'] if not settings['LIMIT_VIDEO_PROCESSES'] else AVAILABLE_THREADS) as pool:
                        pool.starmap(download_video, zip(
                            videos['items'], itertools.repeat(af)))
                except MaybeEncodingError:
                    None

                print('\x1b[2K      {}/{}'.format(len(next(walk(af))[2]), len(videos['items'])))

            if attachments['docs']:
                af = pjoin(at_folder, 'Документы')
                makedirs(af, exist_ok=True)

                print('    [сохранение документов]')
                print('      .../{}'.format(len(attachments['docs'])), end='\r')

                with Pool(settings['POOL_PROCESSES']) as pool:
                    pool.starmap(download, zip(
                        attachments['docs'], itertools.repeat(af)))

                print('\x1b[2K      {}/{}'.format(len(next(walk(af))[2]),
                                                  len(attachments['docs'])))

        print()
        print()


def dump_attachments_only():
    dump_messages(attachments_only=True)


def dump_liked_posts():
    folder_photos = pjoin('dump', 'photos', 'Понравившиеся')
    makedirs(folder_photos, exist_ok=True)
    folder_videos = pjoin('dump', 'video', 'Понравившиеся')
    makedirs(folder_videos, exist_ok=True)
    folder_docs = pjoin('dump', 'docs', 'Понравившиеся')
    makedirs(folder_docs, exist_ok=True)

    print('[получение постов]')

    posts = vk.execute.posts(basic_offset=0)
    i = 0
    for i in range(posts[0]//1000):
        res = vk.execute.posts(basic_offset=(i+1)*1000)
        posts[1].extend(res[1])
        del res

    filtered_posts = []
    for i in range(len(posts[1])):
        for p in posts[1][i]:
            filtered_posts.append(p)
    posts = filtered_posts
    del filtered_posts

    photos = []
    video_ids = []
    videos = []
    docs = []

    for p in posts:
        if 'attachments' in p:
            for at in p['attachments']:
                if at['type'] == 'photo':
                    obj = {
                        'url': at['photo']['sizes'][-1]['url'],
                        'prefix': '{}_{}'.format(p['owner_id'], p['id'])}
                    if 'access_key' in at['photo']:
                        obj.update({'access_key': at['photo']['access_key']})
                    photos.append(obj)
                elif at['type'] == 'video':
                    video_ids.append('{oid}_{id}{access_key}'.format(
                        oid=at['video']['owner_id'],
                        id=at['video']['id'],
                        access_key='_' +
                        at['video']['access_key'] if 'access_key' in at['video'] else ''
                    ))
                elif at['type'] == 'doc':
                    obj = {
                        'url': at['doc']['url'],
                        'prefix': '{}_{}'.format(p['owner_id'], p['id']),
                        'name': at['doc']['title'] + '_' + str(at['doc']['id']),
                        'ext': at['doc']['ext']}
                    if 'access_key' in at['doc']:
                        obj.update({'access_key': at['doc']['access_key']})
                    docs.append(obj)

    if video_ids:
        videos = vk_tools.get_all(
            method='video.get',
            max_count=200,
            values={
                'videos': ','.join(video_ids),
                'extended': 1
            }
        )

    print('Сохранение ({} вложений из {} постов):'.format(
        sum([len(photos), len(videos), len(docs)]), len(posts)))

    try:
        if photos:
            print('  [фото ({})]'.format(len(photos)))
            with Pool(settings['POOL_PROCESSES']) as pool:
                pool.starmap(download, zip(photos, itertools.repeat(folder_photos)))
    except MaybeEncodingError:
        None

    try:
        if videos:
            print('  [видео ({}/{})]'.format(len(videos['items']), len(video_ids)))
            with Pool(settings['POOL_PROCESSES'] if not settings['LIMIT_VIDEO_PROCESSES'] else AVAILABLE_THREADS) as pool:
                pool.starmap(download_video, zip(videos['items'], itertools.repeat(folder_videos)))
    except MaybeEncodingError:
        None

    try:
        if docs:
            print('  [документы ({})]'.format(len(docs)))
            with Pool(settings['POOL_PROCESSES']) as pool:
                pool.starmap(download, zip(docs, itertools.repeat(folder_docs)))
    except MaybeEncodingError:
        None


def dump_all():
    for d in (dump_photos, dump_audio, dump_video, dump_docs, dump_messages, dump_attachments_only, dump_liked_posts):
        d()
        print()

# GUI funcs
def clear(): return print('\x1b[2J', '\x1b[1;1H', sep='', end='', flush=True)


def lprint(*args, **kwargs):
    print('\x1b[?25l' if ANSI_AVAILABLE else '')
    for s in args:
        if (s.find('\x1b') == -1) and ('slow' in kwargs) and (kwargs['slow']):
            for ch in s:
                stdout.write(ch)
                stdout.flush()
                sleep(kwargs['delay'] if 'delay' in kwargs else 1/50)
        else:
            print(s, end='')
    print('\x1b[?25h' if ANSI_AVAILABLE else '')


def cprint(msg, **kwargs):
    if isinstance(msg, list):
        for i in range(len(msg)):
            if not 'offset' in kwargs:
                kwargs['offset'] = 0
            kwargs['color'][i] = colors[kwargs['color'][i]] if (
                'color' in kwargs and kwargs['color'][i]) else mods['nc']
            if 'mod' in kwargs and kwargs['mod'][i]:
                kwargs['color'][i] += mods[kwargs['mod'][i]]
            lprint(kwargs['color'][i]+'\x1b[{y};{x}H'.format(x=int(w/2-len(msg[i])/2),
                                                             y=int(h/2-len(msg)/2+i)+1-kwargs['offset']),
                   msg[i], mods['nc'], **kwargs)

    else:
        if not 'offset' in kwargs:
            kwargs['offset'] = 0
        kwargs['color'] = colors[kwargs['color']] if 'color' in kwargs else mods['nc']
        if 'mod' in kwargs:
            kwargs['color'] += mods[kwargs['mod']]

        lprint(kwargs['color']+'\x1b[{y};{x}H'.format(x=int(w/2-len(msg)/2),
                                                      y=int(h/2-(len(msg.split('\n'))/2)+1-kwargs['offset'])),
               msg, mods['nc'], **kwargs)


def welcome():
    ANSI_AVAILABLE and stdout.write('\x1b]0;{}\x07'.format(NAME))
    clear()
    cprint([NAME, 'v'+VERSION],
           color=['green', None],
           mod=['bold', None],
           slow=True, delay=1/50)

    print('\x1b[?25l' if ANSI_AVAILABLE else '')
    sleep(2)
    print('\x1b[?25h' if ANSI_AVAILABLE else '')


def goodbye():
    clear()
    cprint(['Спасибо за использование скрипта :з', '', 'Made with ♥ by hikiko4ern'],
           color=['green', None, 'red'], mod=['bold', None, 'bold'], offset=-1)
    ANSI_AVAILABLE and print('\x1b[?25h')
    raise SystemExit


def logInfo():
    global account, args

    log_info = [
        'Login: \x1b[1;36m{}\x1b[0m'.format(account['phone'] if args.token else login),
        'Name: \x1b[1;36m{fn} {ln}\x1b[0m'.format(fn=account['first_name'], ln=account['last_name'])
    ]
    ln = 0
    for l in log_info:
        ln = max(len(l), ln)

    print('\x1b[1;31m'+'-'*(ln-7), end='\x1b[0m\n')
    for l in log_info:
        print('\x1b[31m>\x1b[0m '+l)
    print('\x1b[1;31m'+'-'*(ln-7), end='\x1b[0m\n')


def menu():
    global args

    clear()
    logInfo()
    print()

    actions = [
        'Фото (по альбомам)', dump_photos,
        'Аудио', dump_audio,
        'Видео (по альбомам)', dump_video,
        'Документы', dump_docs,
        'Сообщения', dump_messages,
        'Вложения диалогов', dump_attachments_only,
        'Данные понравившихся постов', dump_liked_posts
    ]

    if args.token:
        actions.pop(actions.index(dump_audio)-1)
        actions.pop(actions.index(dump_audio))

    print('Дамп данных:\n')

    for i in range(int(len(actions)/2)):
        print('{clr}[{ind}]{nc} {name}'.format(
            ind=i+1, name=actions[i*2], clr=colors['blue'], nc=mods['nc']))
    print('\n{clr}[F]{nc} Все данные'.format(clr=colors['blue'], nc=mods['nc']))
    print('\n{clr}[S]{nc} Настройки'.format(clr=colors['blue'], nc=mods['nc']))
    print('{clr}[Q]{nc} Выход'.format(clr=colors['blue'], nc=mods['nc']))

    print()
    try:
        choice = input('> ').lower()

        if isinstance(choice, str):
            if choice == 'q':
                choice = exit
            elif choice == 's':
                choice = settings_screen
            elif choice == 'f':
                choice = [actions[i] for i in range(len(actions)) if i % 2 == 1]
            else:
                if int(choice) not in range(1, len(actions)+1):
                    raise IndexError
                choice = actions[(int(choice)-1)*2+1]

        if choice is exit:
            goodbye()
        elif isinstance(choice, list):
            for c in choice:
                c()
                print()
            menu()
        elif callable(choice):
            choice()
            if choice is not settings_screen:
                print('\n{clr}Сохранение завершено :з{nc}'.format(
                    clr=colors['green'], nc=mods['nc']))
                input('\n[нажмите {clr}Enter{nc} для продолжения]'.format(
                    clr=colors['cyan']+mods['bold'], nc=mods['nc']))
            menu()
        else:
            raise IndexError
    except IndexError:
        cprint('Выберите действие из доступных', color='red', mode='bold')
        sleep(2)
        clear()
        menu()
    except ValueError:
        menu()
    except KeyboardInterrupt:
        goodbye()


def settings_screen():
    clear()
    logInfo()
    print()
    print('Настройки:\n')

    i = 0
    for s in settings:
        value = settings[s]

        if isinstance(value, bool):
            color = colors['green'] if value else colors['red']
            value = 'Да' if value else 'Нет'

        print('{ind_clr}[{ind}]{nc} {name}: {clr}{value}{nc}'.format(
            ind=i+1,
            name=settings_names[s],
            value=value,
            ind_clr=colors['blue'],
            clr=color if 'color' in locals() else colors['yellow'],
            nc=mods['nc']
        ))
        i += 1

        if 'color' in locals():
            del color

    print('\n{clr}[0]{nc} В меню'.format(clr=colors['blue'], nc=mods['nc']))

    try:
        choice = int(input('> '))
        if choice == 0:
            menu()
        elif choice not in range(1, len(settings)+1):
            raise IndexError()
        else:
            s = [s for s in settings][choice-1]
            new = None
            if isinstance(settings[s], bool):
                settings[s] = not settings[s]
            else:
                while (type(new) is not type(settings[s])) or (s == 'REPLACE_CHAR' and new in INVALID_CHARS):
                    try:
                        new = input('\nВведите новое значение для {clr}{}{nc} ({type_clr}{type}{nc})\n> '.format(
                            s,
                            clr=colors['red'],
                            type_clr=colors['yellow'],
                            nc=mods['nc'],
                            type=type(settings[s])))
                        if not new:
                            new = settings[s]
                            break
                        if isinstance(settings[s], int):
                            new = int(new)
                    except ValueError:
                        continue
                settings[s] = new
            settings_save()

        settings_screen()
    except IndexError:
        cprint('Выберите одну из доступных настроек', color='red', mode='bold')
        sleep(2)
        clear()
        settings_screen()
    except ValueError:
        settings_screen()
    except KeyboardInterrupt:
        goodbye()


if __name__ == '__main__':
    from pprint import pprint
    init()
    if args.verbose:
        for a in vars(args):
            print(a+':', (colors['green']+'ON'+mods['nc'] if getattr(args, a) else colors['red']+'OFF'+mods['nc']) if isinstance(getattr(args, a), bool) else getattr(args, a))
        sleep(5)

    if args.dump:
        if (not args.login or not args.password) and (not args.token):
            print('|--------------------------------------------------------|')
            print('|  Необходимо передать либо логин и пароль, либо токен.  |')
            print('|--------------------------------------------------------|')
        else:
            log()
            for d in args.dump:
                # DUMPS[d]()
                if d == 'photos':
                    dump_photos()
                elif d == 'audio':
                    dump_audio()
                elif d == 'video':
                    dump_video()
                elif d == 'docs':
                    dump_docs()
                elif d == 'messages':
                    dump_messages()
                elif d == 'attachments':
                    dump_attachments_only()
                elif d == 'liked_posts':
                    dump_liked_posts()
                elif d == 'all':
                    dump_all()
                print()
    else:
        welcome()
        log()
        menu()

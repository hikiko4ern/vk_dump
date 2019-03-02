#!/usr/bin/env python3
import argparse
from configparser import ConfigParser
import logging

import os
import os.path
from sys import stdout
import time

import urllib3
from urllib.request import urlopen
import requests
import shutil
from re import search as research

import itertools
from multiprocessing import Pool
from multiprocessing.pool import MaybeEncodingError

import vk_api
from youtube_dl import YoutubeDL

NAME = 'VK Dump Tool'
VERSION = '0.8.10'
DESCRIPTION = 'Let\'s hope for the best'
API_VERSION = '5.92'

logger = logging.Logger(name='youtube-dl', level=logging.FATAL)

parser = argparse.ArgumentParser(description=NAME)
parser.add_argument('--version', action='version', version=VERSION)
parser.add_argument('--update', action='store_true', help='update only')
auth = parser.add_argument_group('Аутентификация')
auth.add_argument('-l', '--login', type=str, metavar='\b', help='логин')
auth.add_argument('-p', '--password', type=str, metavar='\b', help='пароль')
auth.add_argument('-t', '--token', type=str, metavar='\b', help='access_token')
dump = parser.add_argument_group('Дамп данных')
dump.add_argument('--dump', type=str, nargs='*',
                  choices=('photos', 'docs', 'messages', 'attachments',
                           'fave_posts', 'fave_photos', 'all'),
                  help='Данные для сохранения.')

AVAILABLE_THREADS = os.cpu_count()

settings = {
    'UPDATE_CHANNEL': True,  # канал для получения обновлений; true - GitHub, false - GitLab

    'SHOW_ANNOUNCEMENTS': True,  # показывать экран / выводить сообщения
    'MEMORY_CONFIG': True,  # сохранять конфиг в память вместо файла

    'REPLACE_SPACES': False,  # заменять пробелы на _
    'REPLACE_CHAR': '_',  # символ для замены запрещённых в Windows символов,

    'POOL_PROCESSES': 4*AVAILABLE_THREADS,  # макс. число создаваемых процессов

    'DIALOG_APPEND_MESSAGES': False,  # дописывать новые сообщения в файл вместо полной перезаписи
    'KEEP_DIALOG_NAMES': True,  # сохранять имена файлов в случае изменения имени диалога
    'SAVE_DIALOG_ATTACHMENTS': True  # сохранять вложения из диалогов
}

settings_names = {
    'UPDATE_CHANNEL': 'Канал обновлений (GitHub / GitLab)',

    'SHOW_ANNOUNCEMENTS': 'Показывать объявления',
    'MEMORY_CONFIG': 'Сохранять конфиг vk_api в памяти вместо записи в файл',

    'REPLACE_SPACES': 'Заменять пробелы на символ "_"',
    'REPLACE_CHAR': 'Символ для замены запрещённых в имени файла',

    'POOL_PROCESSES': 'Число создаваемых процессов при мультипоточной загрузке',

    'DIALOG_APPEND_MESSAGES': 'Дописывать новые сообщения в файл вместо полной перезаписи',
    'KEEP_DIALOG_NAMES': 'Сохранять название диалога в случае его изменения',
    'SAVE_DIALOG_ATTACHMENTS': 'Сохранять вложения из диалогов',
}

EXCLUDED_DIALOGS = []

INVALID_CHARS = ['\\', '/', ':', '*', '?', '<', '>', '|', '"']
INVALID_POSIX_CHARS = ['$']


def update(**kwargs):
    quite = 'quite' in kwargs and kwargs['quite']
    if quite:
        print('Проверка на наличие обновлений...')
    else:
        clear()
        print_center([f'{NAME} [{VERSION}]', '', 'Проверка на наличие обновлений...'],
                     color=['green', None, 'yellow'])

    from requests import get

    if settings['UPDATE_CHANNEL']:
        res = get('https://api.github.com/repos/hikiko4ern/vk_dump/releases/latest').json()
    else:
        res = get('https://gitlab.com/api/v4/projects/10503487/releases').json()[0]
    if 'tag_name' in res:
        cv = [int(i) for i in VERSION.split('.')]
        nv = [int(i) for i in res['tag_name'].split('v')[1].split('.')]
        if (nv[0]>cv[0]) or (nv[0]==cv[0] and nv[1]>cv[1]) or (nv[0]==cv[0] and nv[1]==cv[1] and nv[2]>cv[2]):
            for a in (res['assets'] if settings['UPDATE_CHANNEL'] else res['assets']['links']):
                if 'name' in a and a['name'] == 'dump.py':
                    if quite:
                        print('Найдена новая версия ({})'.format(res['tag_name']))
                    else:
                        print_center('Найдена новая версия ({})'.format(
                                     res['tag_name']), color='green', mod='bold', offset=-2)
                    if download((a['browser_download_url'] if settings['UPDATE_CHANNEL'] else a['url']), os.getcwd(), force=True, text_mode=True):
                        if quite:
                            print('Обновление успешно!\nПерезапустите программу вручную :3')
                        else:
                            print_center(['Обновление успешно!', 'Перезапустите программу вручную :3'],
                                         color=['green', 'yellow'], mod=['bold', 'bold'], offset=-5)
                        raise SystemExit
                    else:
                        if quite:
                            print('Не удалось обновить\nСкачайте и замените dump.py вручную\nhttps://github.com/hikiko4ern/vk_dump/releases/latest')
                        else:
                            print_center(['Не удалось обновить', 'Скачайте и замените dump.py вручную', 'https://github.com/hikiko4ern/vk_dump/releases/latest'],
                                         color=['red', 'yellow', None], mod=['bold', 'bold', None], offset=-3)
                        raise SystemExit
        else:
            if quite:
                print('Обновлений не найдено')


def init():
    global args, settings, Config, ANSI_AVAILABLE, INVALID_CHARS, w, h, colors, mods

    args = parser.parse_args()

    if os.name == 'nt':
        from platform import platform
        if int(platform().split('-')[1]) < 10:
            import colorama
            colorama.init()
            ANSI_AVAILABLE = False
        else:
            from subprocess import call
            call('', shell=True)
            ANSI_AVAILABLE = True
    elif os.name == 'posix':
        INVALID_CHARS += INVALID_POSIX_CHARS
        ANSI_AVAILABLE = True

    ANSI_AVAILABLE and stdout.write('\x1b]0;{}\x07'.format(NAME))

    config = ConfigParser()
    if not config.read('settings.ini'):
        with open('settings.ini', 'w') as cf:
            config['SETTINGS'] = settings
            config['EXCLUDED_DIALOGS'] = {'id':','.join([str(i) for i in EXCLUDED_DIALOGS])}
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
        if len(config['EXCLUDED_DIALOGS']['id'])>0:
            for id in config['EXCLUDED_DIALOGS']['id'].split(','):
                try:
                    EXCLUDED_DIALOGS.append(int(id))
                except ValueError:
                    if id[0] == 'c':
                        EXCLUDED_DIALOGS.append(2000000000+int(id[1:]))


    if settings['MEMORY_CONFIG']:
        from jconfig.memory import MemoryConfig as Config
    else:
        from jconfig.jconfig import Config

    w, h = os.get_terminal_size()
    colors = {
        'red': '\x1b[31m',
        'green': '\x1b[32m',
        'yellow': '\x1b[33m',
        'blue': '\x1b[34m' if ANSI_AVAILABLE else '\x1b[36m',
        'purple': '\x1b[35m',
        'cyan': '\x1b[36m',
        'white': '\x1b[37m'
    }
    mods = {
        'nc': '\x1b[0m',
        'bold': '\x1b[1m'
    }
    os.makedirs('dump', exist_ok=True)


def settings_save():
    global settings

    config = ConfigParser()

    with open('settings.ini', 'w') as cf:
        config['SETTINGS'] = settings
        config['EXCLUDED_DIALOGS'] = {'id':','.join([str(i) for i in EXCLUDED_DIALOGS])}
        config.write(cf)

    if settings['MEMORY_CONFIG']:
        if os.path.exists('vk_config.v2.json'):
            os.remove('vk_config.v2.json')


def log(*msg):
    global login, vk_session, vk, vk_tools, account

    if not args.dump:
        clear()
        print_center(msg[0] if msg else '[для продолжения необходимо войти]',
                     color='red', mod='bold', offset=2, delay=1 / 50)

    try:
        if args.token:
            vk_session = vk_api.VkApi(token=args.token, app_id=6631721,
                                      auth_handler=auth_handler, api_version=API_VERSION)
        else:
            if args.login and not msg:
                login = args.login
                password = args.password if args.password else ''
                vk_session = vk_api.VkApi(login, password,
                                          config=(Config),
                                          app_id=6631721,
                                          api_version=API_VERSION,
                                          scope=2+4+8+65536+131072,
                                          auth_handler=auth_handler,
                                          captcha_handler=captcha_handler)
            else:
                login = input('    login: {clr}'.format(
                    clr=colors['cyan'] if ANSI_AVAILABLE else ''))
                print(mods['nc'], end='')
                password = input('    password: {clr}'.format(
                    clr=colors['cyan'] if ANSI_AVAILABLE else ''))
                print(mods['nc'], end='')

                vk_session = vk_api.VkApi(login, password,
                                          config=(Config),
                                          app_id=6631721,
                                          api_version=API_VERSION,
                                          scope=2+4+8+65536+131072,
                                          auth_handler=auth_handler,
                                          captcha_handler=captcha_handler)
                vk_session.auth(token_only=True, reauth=True)
        vk = vk_session.get_api()
        vk_tools = vk_api.VkTools(vk)
        account = vk.account.getProfileInfo()
        vk.stats.trackVisitor()
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

    if not os.path.exists(os.path.join(folder, fn)) or ('force' in kwargs and kwargs['force']):
        try:
            if 'text_mode' in kwargs and kwargs['text_mode']:
                r = requests.get(url, timeout=(30, 5))
                with open(os.path.join(folder, fn), 'w') as f:
                    f.write(r.text)
            else:
                r = requests.get(url, stream=True, timeout=(30, 5))
                with open(os.path.join(folder, fn), 'wb') as f:
                    shutil.copyfileobj(r.raw, f)
            return True
        except requests.exceptions.ConnectionError:
            return False
        except requests.exceptions.ReadTimeout:
            return False
        except urllib3.exceptions.ReadTimeoutError:
            return False
        except Exception as e:
            raise e


# V means Vendetta


def download_external(url, folder):
    if not url:
        return False

    YoutubeDL({
        'logger': logger,
        'outtmpl': os.path.join(folder, '%(title)s_%(id)s.%(ext)s'),
        'nooverwrites': True,
        'fixup': 'detect_or_warn'
    }).download((url,))


def dump_photos():
    os.makedirs(os.path.join('dump', 'photos'), exist_ok=True)
    albums = vk.photos.getAlbums(need_system=1)

    print('Сохранение фото:')

    for al in albums['items']:
        print('  Альбом "{}":'.format(al['title']))
        folder = os.path.join('dump', 'photos', '_'.join(al['title'].split(' ')))
        os.makedirs(folder, exist_ok=True)

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
            print(
                '\x1b[2K    {}/{}'.format(len(next(os.walk(folder))[2]), photos['count']))


# Audi was here


# Vanadium 23


def dump_docs():
    folder = os.path.join('dump', 'docs')
    os.makedirs(folder, exist_ok=True)

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
                'name': d['title'] + '_' + str(d['id']),
                'ext': d['ext']
            })

        print('  .../{}'.format(docs['count']), end='\r')
        with Pool(settings['POOL_PROCESSES']) as pool:
            pool.starmap(download, zip(objs, itertools.repeat(folder)))
        print('\x1b[2K  {}/{}'.format(len(next(os.walk(folder))[2]), docs['count']))


def dump_messages(**kwargs):
    def users_add(id):
        try:
            if id > 0:
                # User: {..., first_name, last_name, id, ...} -> {id:{name: 'first_name + last_name', length: len(name)}
                u = vk.users.get(user_ids=id)[0]
                if ('deactivated' in u) and (u['deactivated'] == 'deleted') and (u['first_name'] == 'DELETED'):
                    name = 'DELETED'
                    users[u['id']] = {'name': name, 'length': len(name)}
                else:
                    name = u['first_name'] + ' ' + u['last_name']
                    users[u['id']] = {'name': name, 'length': len(name)}

            elif id < 0:
                # Group: {..., name, id, ...} -> {-%id%: {name: 'name', length: len(name) }
                g = vk.messages.getConversationsById(
                    peer_ids=id, extended=1)['groups'][0]
                name = g['name']
                users[-g['id']] = {'name': name, 'length': len(name)}

        except Exception:
            users[id] = {'name': r'{unknown user}', 'length': 3}

    def time_handler(t):
        # seconds -> human-readable format
        m = {'january': 'января', 'february': 'февраля', 'march': 'марта', 'april': 'апреля', 'may': 'мая', 'june': 'июня',
             'july': 'июля', 'august': 'августа', 'september': 'сентября', 'october': 'октября', 'november': 'ноября', 'december': 'декабря'}
        t = time.strftime('%d %B %Y', time.gmtime(t)).lower().split(' ')
        t[1] = '{'+t[1]+'}'
        return ' '.join(t).format_map(m)

    def message_handler(msg, **kwargs):
        """
        Обработчик сообщений.
        Возвращает объект
            {
                date: str, # [HH:MM]
                "messages": [...],
                "attachments": {
                    "photos": [...],
                    "docs": [...],
                    "audio_messages": [...]
                }
            }
        """"""
        [документация API]
            [вложения]
                [сообщения]
                    - vk.com/dev/objects/attachments_m
                [wall_reply]
                    - vk.com/dev/objects/attachments_w
        """
        r = {
            'date': time.strftime('[%H:%M]', time.gmtime(msg['date'])),
            'messages': [],
            'attachments': {
                'photos': [],
                'docs': [],
                'audio_messages': []
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
                                m, name=' ' * len(users.get(fwd['from_id'])['name'])))

                for tp in res['attachments']:
                    for a in res['attachments'][tp]:
                        r['attachments'][tp].append(a)

        if ('reply_message' in msg) and msg['reply_message']:
            res = message_handler(msg['reply_message'])

            if 'attachments_only' not in kwargs:
                if len(res['messages']) > 0:
                    if msg['reply_message']['from_id'] not in users:
                        users_add(msg['reply_message']['from_id'])

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

                if 'attachments_only' not in kwargs:
                    if tp == 'photo':
                        if 'action' not in msg:
                            r['messages'].append('[фото: {url}]'.format(
                                url=at[tp]['sizes'][-1]['url']))
                            r['attachments']['photos'].append(
                                at[tp]['sizes'][-1]['url'])
                    elif tp == 'video':
                        r['messages'].append(
                            '[видео: vk.com/video{owid}_{id}]'.format(owid=at[tp]['owner_id'], id=at[tp]['id']))
                    elif tp == 'audio':
                        r['messages'].append('[аудио: {artist} - {title}]'.format(artist=at[tp]
                                                                                  ['artist'], title=at[tp]['title']))
                    elif tp == 'doc':
                        r['messages'].append(
                            '[документ: vk.com/doc{owid}_{id}]'.format(owid=at[tp]['owner_id'], id=at[tp]['id']))
                        r['attachments']['docs'].append({
                            'url': at[tp]['url'],
                            'name': at[tp]['title'] + '_' + str(at[tp]['id']),
                            'ext': at[tp]['ext']
                        })
                    elif tp == 'link':
                        r['messages'].append('[ссылка: {title} ({url})]'.format(
                            title=at[tp]['title'], url=at[tp]['url']))
                    elif tp == 'market':
                        r['messages']\
                            .append('[товар: {title} ({price}{cur}) [vk.com/market?w=product{owid}_{id}]]'.format(
                                title=at[tp]['title'],
                                owid=at[tp]['owner_id'],
                                id=at[tp]['id'],
                                price=at[tp]['price']['amount'],
                                cur=at[tp]['price']['currency']['name'].lower()))
                    elif tp == 'market_album':
                        r['messages'].append(
                            '[коллекция товаров: {title}]'.format(title=at[tp]['title']))
                    elif tp == 'wall':
                        r['messages'].append(
                            '[пост: vk.com/wall{owid}_{id}]'.format(owid=at[tp]['to_id'], id=at[tp]['id']))
                    elif tp == 'wall_reply':
                        if at[tp]['from_id'] not in users:
                            users_add(at[tp]['from_id'])
                        u = users.get(at[tp]['from_id'])
                        r['messages']\
                            .append('[комментарий к посту от {user}: {msg} (vk.com/wall{oid}_{pid}?reply={id})]'.format(
                                user=u['name'],
                                msg=at[tp]['text'],
                                oid=at[tp]['owner_id'],
                                pid=at[tp]['post_id'],
                                id=at[tp]['id']))
                    elif tp == 'sticker':
                        r['messages'].append('[стикер: {url}]'.format(
                            url=at[tp]['images'][-1]['url']))
                    elif tp == 'gift':
                        r['messages'].append(
                            '[подарок: {id}]'.format(id=at[tp]['id']))
                    elif tp == 'graffiti':
                        r['messages'].append(
                            '[граффити: {url}]'.format(url=at[tp]['url']))
                    elif tp == 'audio_message':
                        r['messages'].append(
                            '[голосовое сообщение: {url}]'.format(url=at[tp]['link_mp3']))
                        r['attachments']['audio_messages'].append({
                            'url': at[tp]['link_mp3'],
                            'name': '{from_id}_{date}_{id}'.format(
                                from_id=str(msg['from_id']),
                                date=time.strftime('%Y_%m_%d', time.gmtime(msg['date'])),
                                id=str(at[tp]['id'])),
                            'ext': 'mp3'})
                    else:
                        r['messages'].append(
                            '[вложение с типом "{tp}"]'.format(tp=tp))
                else:
                    if tp == 'photo':
                        r['attachments']['photos'].append(
                            at[tp]['sizes'][-1]['url'])
                    # 1.08V
                    elif tp == 'doc':
                        r['attachments']['docs'].append({
                            'url': at[tp]['url'],
                            'name': at[tp]['title'] + '_' + str(at[tp]['id']),
                            'ext': at[tp]['ext']
                        })
                    elif tp == 'audio_message':
                        r['attachments']['audio_messages'].append({
                            'url': at[tp]['link_mp3'],
                            'name': '{from_id}_{date}_{id}'.format(
                                from_id=str(msg['from_id']),
                                date=time.strftime('%Y_%m_%d', time.gmtime(msg['date'])),
                                id=str(at[tp]['id'])),
                            'ext': 'mp3'})

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
                        users[act['member_id']] = {
                            'name': r'{unknown user}', 'length': 3}

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
            else:
                if tp == 'chat_photo_update':
                    r['attachments']['photos'].append(
                        msg['attachments'][0]['photo']['sizes'][-1]['url'])

        return r

    folder = os.path.join('dump', 'dialogs')
    os.makedirs(folder, exist_ok=True)

    print('[получение диалогов...]')
    print('\x1b[2K  0/???', end='\r')

    conversations = vk_tools.get_all(
        method='messages.getConversations',
        max_count=200,
        values={
            'extended': 1,
            'fields': 'first_name, last_name, name'
        })

    print('\x1b[2K  {}/{}'.format(len(conversations['items']),
                                  conversations['count']))
    print('[будет исключено диалогов: {}]'.format(len(EXCLUDED_DIALOGS)), end='\n\n')

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

        for c in INVALID_CHARS:
            dialog_name = dialog_name.replace(c, settings['REPLACE_CHAR'])

        fn = '{}_{id}'.format('_'.join(dialog_name.split(' ')), id=did)
        for n in os.listdir(folder):
            if str(did) == n.split('.txt')[0].split('_')[-1]:
                if settings['KEEP_DIALOG_NAMES']:
                    fn = n.split('.txt')[0]
                else:
                    shutil.move(os.path.join(folder, n), os.path.join(folder, '{}_{id}'.format('_'.join(dialog_name.split(' ')),
                                                                                 id=did) + ('.txt' if '.txt' in n else '')))

        print('  Диалог: {}{nfn}'.format(dialog_name, nfn=(' (as {})'.format(fn) if ' '.join(fn.split('_')[:-1]) != dialog_name else '')))
        if did in EXCLUDED_DIALOGS:
            print('    [исключён]\n')
            continue

        values={
            'peer_id': con['conversation']['peer']['id'],
            'extended': 1,
            'fields': 'first_name, last_name'
        }

        append = {'use': not ('attachments_only' in kwargs and kwargs['attachments_only']) and settings['DIALOG_APPEND_MESSAGES'] and os.path.exists(os.path.join(folder, f'{fn}.txt'))}
        try:
            if append['use']:
                # [last:{id}]
                import re
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
                            # TODO: обработка в случае отсутствия даты (???)
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
            history = vk_tools.get_all(
                method='messages.getHistory',
                max_count=200,
                values=values,
                negative_offset=append['use'])
            print('\x1b[2K      {}/{}'.format(len(history['items']), history['count']))
        except vk_api.exceptions.VkToolsException:
            print('\x1b[2K      0/0')

        if not history['count']:
            print()
            continue

        if append['use']:
            def sortById(msg):
                return msg['id']
            history['items'].sort(key=sortById)

        attachments = {
            'photos': [],
            'docs': [],
            'audio_messages': []
        }

        if ('attachments_only' not in kwargs) or (kwargs['attachments_only'] == False):
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
                    users_add(m['from_id'])

                res = message_handler(m)

                date = time_handler(m['date'])
                hold = ' ' * (users.get(m['from_id'])['length'] + 2)

                msg = res['date'] + ' '
                msg += hold if (prev and date and prev == m['from_id'] and prev_date == date) else users.get(
                    m['from_id'])['name'] + ': '

                if res['messages']:
                    msg += res['messages'][0] + '\n'
                    for r in res['messages'][1:]:
                        msg += hold + ' '*8 + r + '\n'
                else:
                    msg += '\n'

                for a in res['attachments']['audio_messages']:
                    if a not in attachments['audio_messages']:
                        attachments['audio_messages'].append(a)

                if settings['SAVE_DIALOG_ATTACHMENTS']:
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
                if settings['DIALOG_APPEND_MESSAGES']:
                    f.write('[last:{}]\n'.format(history['items'][-1]['id']))
                f.close()
            print()
        else:
            count = len(history['items'])
            print('    [обработка сообщений]')
            print('      {}/{}'.format(0, count), end='\r')

            for i in range(count):
                res = message_handler(history['items'][i], attachments_only=True)

                for tp in res['attachments']:
                    for a in res['attachments'][tp]:
                        if a not in attachments[tp]:
                            attachments[tp].append(a)

                print('\x1b[2K      {}/{}'.format(i+1, count), end='\r')
            print()

        if attachments['audio_messages']:
            at_folder = os.path.join(folder, fn)
            af = os.path.join(at_folder, 'Голосовые')
            os.makedirs(af, exist_ok=True)

            print('    [сохранение голосовых сообщений]')
            print('      .../{}'.format(len(attachments['audio_messages'])), end='\r')

            with Pool(settings['POOL_PROCESSES']) as pool:
                pool.starmap(download, zip(
                    attachments['audio_messages'], itertools.repeat(af)))

            print('\x1b[2K      {}/{}'.format(len(next(os.walk(af))[2]),
                                              len(attachments['audio_messages'])))

        if settings['SAVE_DIALOG_ATTACHMENTS'] or ('attachments_only' in kwargs and kwargs['attachments_only']):
            at_folder = os.path.join(folder, fn)
            os.makedirs(at_folder, exist_ok=True)

            if attachments['photos']:
                af = os.path.join(at_folder, 'Фото')
                os.makedirs(af, exist_ok=True)

                print('    [сохранение фото]')
                print('      .../{}'.format(len(attachments['photos'])), end='\r')

                with Pool(settings['POOL_PROCESSES']) as pool:
                    pool.starmap(download, zip(
                        attachments['photos'], itertools.repeat(af)))

                print('\x1b[2K      {}/{}'.format(len(next(os.walk(af))[2]),
                                                  len(attachments['photos'])))

            # 3.3V

            if attachments['docs']:
                af = os.path.join(at_folder, 'Документы')
                os.makedirs(af, exist_ok=True)

                print('    [сохранение документов]')
                print('      .../{}'.format(len(attachments['docs'])), end='\r')

                with Pool(settings['POOL_PROCESSES']) as pool:
                    pool.starmap(download, zip(
                        attachments['docs'], itertools.repeat(af)))

                print('\x1b[2K      {}/{}'.format(len(next(os.walk(af))[2]),
                                                  len(attachments['docs'])))
        print()


def dump_attachments_only():
    dump_messages(attachments_only=True)


def dump_fave_posts():
    folder_photos = os.path.join('dump', 'photos', 'Понравившиеся')
    os.makedirs(folder_photos, exist_ok=True)
    # 5V
    folder_docs = os.path.join('dump', 'docs', 'Понравившиеся')
    os.makedirs(folder_docs, exist_ok=True)

    print('[получение постов]')

    posts = vk.execute.posts(basic_offset=0)
    for i in range(posts[0] // 1000):
        res = vk.execute.posts(basic_offset=(i + 1) * 1000)
        posts[1].extend(res[1])
        del res

    filtered_posts = []
    for i in range(len(posts[1])):
        for p in posts[1][i]:
            filtered_posts.append(p)
    posts = filtered_posts
    del filtered_posts

    photos = []
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
                # 9V
                elif at['type'] == 'doc':
                    obj = {
                        'url': at['doc']['url'],
                        'prefix': '{}_{}'.format(p['owner_id'], p['id']),
                        'name': at['doc']['title'] + '_' + str(at['doc']['id']),
                        'ext': at['doc']['ext']}
                    if 'access_key' in at['doc']:
                        obj.update({'access_key': at['doc']['access_key']})
                    docs.append(obj)

    # 12V

    print('Сохранение ({} вложений из {} постов):'.format(
        sum([len(photos), len(docs)]), len(posts)))

    try:
        if photos:
            print('  [фото ({})]'.format(len(photos)))
            with Pool(settings['POOL_PROCESSES']) as pool:
                pool.starmap(download, zip(
                    photos, itertools.repeat(folder_photos)))
    except MaybeEncodingError:
        None

    # 24V

    try:
        if docs:
            print('  [документы ({})]'.format(len(docs)))
            with Pool(settings['POOL_PROCESSES']) as pool:
                pool.starmap(download, zip(
                    docs, itertools.repeat(folder_docs)))
    except MaybeEncodingError:
        None


def dump_fave_photos():
    folder = os.path.join('dump', 'photos', 'Понравившиеся')
    os.makedirs(folder, exist_ok=True)

    print('[получение понравившихся фото]')

    photos = vk_tools.get_all(
        method='fave.getPhotos',
        max_count=50,
        values={
            'photo_sizes': 1
        })

    print('Сохранение понравившихся фото:')

    if photos['count'] == 0:
        print('  0/0')
    else:
        objs = []
        for p in photos['items']:
            objs.append(p['sizes'][-1]['url'])

        print('  .../{}'.format(photos['count']), end='\r')
        with Pool(settings['POOL_PROCESSES']) as pool:
            pool.starmap(download, zip(objs, itertools.repeat(folder)))
        print(
            '\x1b[2K  {}/{}'.format(len(next(os.walk(folder))[2]), photos['count']))


# V-list inf


def dump_all():
    for d in (dump_photos, dump_docs, dump_messages, dump_fave_posts, dump_fave_photos):
        d()
        print()


def clear(): return print('\x1b[2J', '\x1b[1;1H', sep='', end='', flush=True)


def print_slow(*args, **kwargs):
    print('\x1b[?25l' if ANSI_AVAILABLE else '')
    for s in args:
        if (s.find('\x1b') == -1) and ('slow' in kwargs) and (kwargs['slow']):
            for ch in s:
                stdout.write(ch)
                stdout.flush()
                time.sleep(kwargs['delay'] if 'delay' in kwargs else 1 / 50)
        else:
            print(s, end='')
    print('\x1b[?25h' if ANSI_AVAILABLE else '')


def print_center(msg, **kwargs):
    if isinstance(msg, list):
        for i in range(len(msg)):
            if not 'offset' in kwargs:
                kwargs['offset'] = 0
            kwargs['color'][i] = colors[kwargs['color'][i]] if (
                'color' in kwargs and kwargs['color'][i]) else mods['nc']
            if 'mod' in kwargs and kwargs['mod'][i]:
                kwargs['color'][i] += mods[kwargs['mod'][i]]
            print_slow(kwargs['color'][i] + '\x1b[{y};{x}H'.format(x=int(w / 2 - len(msg[i]) / 2),
                                                                   y=int(h / 2 - len(msg) / 2 + i) + 1 - kwargs['offset']),
                       msg[i], mods['nc'], **kwargs)

    else:
        if 'offset' not in kwargs:
            kwargs['offset'] = 0
        kwargs['color'] = colors[kwargs['color']
                                 ] if 'color' in kwargs else mods['nc']
        if 'mod' in kwargs:
            kwargs['color'] += mods[kwargs['mod']]

        print_slow(kwargs['color'] + '\x1b[{y};{x}H'.format(x=int(w / 2 - len(msg) / 2),
                                                            y=int(h / 2 - (len(msg.split('\n')) / 2) + 1 - kwargs['offset'])),
                   msg, mods['nc'], **kwargs)


def welcome():
    ANSI_AVAILABLE and stdout.write('\x1b]0;{}\x07'.format(NAME))
    clear()
    print_center([NAME, 'v' + VERSION, '', DESCRIPTION],
                 color=['green', None, None, 'yellow'],
                 mod=['bold', None, None, None],
                 slow=True, delay=1 / 50)

    ANSI_AVAILABLE and print('\x1b[?25l')
    time.sleep(2)
    ANSI_AVAILABLE and print('\x1b[?25h')


def announcement():
    if settings['SHOW_ANNOUNCEMENTS']:
        if not (args.dump or args.update):
            clear()
            print_center(['Внимание!', '15 февраля ВКонтакте закрывает доступ к API сообщений.',
                          'Прохождение модерации в процессе.',
                          'Дальнейшая судьба скрипта неизвестна, но стоит надеяться на лучшее :з', '',
                          'Если будут новости по сложившейся ситуации - они появятся в README репозитория.', '',
                          'Спасибо за прочтение. Показ этой информации можно отключить в настройках.',
                          'Нажмите Enter для продолжения...'],
                          color=['red', 'yellow', 'yellow', 'yellow', None, 'cyan', None, 'white', 'white'])
            ANSI_AVAILABLE and print('\x1b[?25l')
            input()
            ANSI_AVAILABLE and print('\x1b[?25h')
        else:
            print()
            print('Внимание!', '15 февраля ВКонтакте закрывает доступ к API сообщений.',
                  'Возможно, удастся пройти модерацию, или же будет придуман обход.',
                  'Дальнейшая судьба скрипта неизвестна, но стоит надеяться на лучшее :з',
                  sep='\n')
            print()


def goodbye():
    clear()
    print_center(['Спасибо за использование скрипта :з', '', 'Made with ♥ by hikiko4ern'],
                 color=['green', None, 'red'], mod=['bold', None, 'bold'], offset=-1)
    ANSI_AVAILABLE and print('\x1b[?25h')
    raise SystemExit


def logInfo():
    global account, args

    log_info = [
        'Login: \x1b[1;36m{}\x1b[0m'.format(
            account['phone'] if args.token else login),
        'Name: \x1b[1;36m{fn} {ln}\x1b[0m'.format(
            fn=account['first_name'], ln=account['last_name'])
    ]
    ln = 0
    for l in log_info:
        ln = max(len(l), ln)

    print('\x1b[1;31m' + '-' * (ln - 7), end='\x1b[0m\n')
    for l in log_info:
        print('\x1b[31m>\x1b[0m ' + l)
    print('\x1b[1;31m' + '-' * (ln - 7), end='\x1b[0m\n')


def menu():
    global args

    clear()
    logInfo()
    print()

    actions = [
        'Фото (по альбомам)', dump_photos,
        'Документы', dump_docs,
        'Сообщения', dump_messages,
        'Вложения диалогов', dump_attachments_only,
        'Понравившиеся вложения', menu_dump_fave
    ]

    # Audi was here too

    print('Дамп данных:\n')

    for i in range(int(len(actions) / 2)):
        print('{clr}[{ind}]{nc} {name}'.format(
              ind=i + 1, name=actions[i * 2], clr=colors['blue'], nc=mods['nc']))
    print('\n{clr}[F]{nc} Все данные'.format(
          clr=colors['blue'], nc=mods['nc']))
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
                choice = dump_all
            else:
                if int(choice) not in range(1, len(actions) + 1):
                    raise IndexError
                choice = actions[(int(choice) - 1) * 2 + 1]

        if choice is exit:
            goodbye()
        elif callable(choice):
            choice()
            if choice is not settings_screen:
                print('\n{clr}Сохранение завершено :з{nc}'.format(
                      clr=colors['green'], nc=mods['nc']))
                print('\n[нажмите {clr}Enter{nc} для продолжения]'.format(
                      clr=colors['cyan'] + mods['bold'], nc=mods['nc']), end='')
                input()
            menu()
        else:
            raise IndexError
    except IndexError:
        print_center('Выберите действие из доступных', color='red', mode='bold')
        time.sleep(2)
        clear()
        menu()
    except ValueError:
        menu()
    except KeyboardInterrupt:
        goodbye()


def menu_dump_fave():
    global args

    clear()
    logInfo()
    print()

    actions = [
        'Вложения понравившихся постов (фото, документы)', dump_fave_posts,
        'Фото (отдельно)', dump_fave_photos
    ]

    print('Дамп понравившихся вложений:\n')

    for i in range(int(len(actions) / 2)):
        print('{clr}[{ind}]{nc} {name}'.format(
              ind=i + 1, name=actions[i * 2], clr=colors['blue'], nc=mods['nc']))
    print('\n{clr}[0]{nc} В меню'.format(clr=colors['blue'], nc=mods['nc']))

    print()
    try:
        choice = int(input('> '))
        if choice == 0:
            menu()

        if choice not in range(1, len(actions) + 1):
            raise IndexError

        choice = actions[(choice - 1) * 2 + 1]

        if callable(choice):
            choice()
            print('\n{clr}Сохранение завершено :з{nc}'.format(
                  clr=colors['green'], nc=mods['nc']))
            print('\n[нажмите {clr}Enter{nc} для продолжения]'.format(
                  clr=colors['cyan'] + mods['bold'], nc=mods['nc']), end='')
            input()
            menu_dump_fave()
        else:
            raise IndexError
    except IndexError:
        print_center('Выберите действие из доступных', color='red', mode='bold')
        time.sleep(2)
        clear()
        menu_dump_fave()
    except ValueError:
        menu_dump_fave()
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
            ind=i + 1,
            name=settings_names[s],
            value=(('GitHub' if settings[s] else 'GitLab') if (s == 'UPDATE_CHANNEL') else value),
            ind_clr=colors['blue'],
            clr=color if 'color' in locals() else colors['yellow'],
            nc=mods['nc']
        ))
        i += 1

        if 'color' in locals():
            del color

    print('\n{clr}[0]{nc} В меню'.format(clr=colors['blue'], nc=mods['nc']))

    print()
    try:
        choice = int(input('> '))
        if choice == 0:
            menu()
        elif choice not in range(1, len(settings) + 1):
            raise IndexError()
        else:
            s = [s for s in settings][choice - 1]
            new = None
            if isinstance(settings[s], bool):
                settings[s] = not settings[s]
            else:
                while (type(new) is not type(settings[s])) or (s == 'REPLACE_CHAR' and new in INVALID_CHARS):
                    try:
                        print('\nВведите новое значение для {clr}{}{nc} ({type_clr}{type}{nc})\n> '.format(
                            s,
                            clr=colors['red'],
                            type_clr=colors['yellow'],
                            nc=mods['nc'],
                            type=type(settings[s])), end='')
                        new = input()
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
        print_center('Выберите одну из доступных настроек',
                     color='red', mode='bold')
        time.sleep(2)
        clear()
        settings_screen()
    except ValueError:
        settings_screen()
    except KeyboardInterrupt:
        goodbye()


if __name__ == '__main__':
    init()
    update(quite=(args.dump or args.update))

    announcement()

    if args.update:
        raise SystemExit

    if args.dump:
        if (not args.login or not args.password) and (not args.token):
            print('|--------------------------------------------------------|')
            print('|  Необходимо передать либо логин и пароль, либо токен.  |')
            print('|--------------------------------------------------------|')
        else:
            log()
            vk.stats.trackVisitor()
            for d in args.dump:
                if d == 'photos':
                    dump_photos()
                elif d == 'docs':
                    dump_docs()
                elif d == 'messages':
                    dump_messages()
                elif d == 'attachments':
                    dump_attachments_only()
                elif d == 'fave_posts':
                    dump_fave_posts()
                elif d == 'fave_photos':
                    dump_fave_photos()
                elif d == 'all':
                    dump_all()
                print()
    else:
        welcome()
        log()
        menu()

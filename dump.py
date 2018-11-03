#!/usr/bin/env python3

### Imports
from math import ceil
from os import get_terminal_size, makedirs, walk, name as osname
from os.path import exists, join as pjoin
from sys import stdout
from time import sleep
from urllib.request import urlopen
import itertools
from multiprocessing import Pool
from configparser import ConfigParser

import vk_api


NAME = 'VK Dump Tool'
VERSION = '0.5.2'
API_VERSION = '5.87'

settings = {
  'REPLACE_SPACES': False, # заменять пробелы на _
  'REPLACE_CHAR': '_' # символ для замены запрещённых в Windows символов
}

settings_names = {
  'REPLACE_SPACES': 'Заменять пробелы на символ "_"',
  'REPLACE_CHAR': 'Символ для замены запрещённых в имени файла'
}

INVALID_CHARS = ['\\', '/', ':', '*', '?', '<', '>', '|', '"']
INVALID_POSIX_CHARS = ['$']

### Dump funcs

def init():
  global w, h, colors, mods, settings, INVALID_CHARS

  if osname == 'posix':
    INVALID_CHARS += INVALID_POSIX_CHARS

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
    'blue': '\x1b[34m',
    'purple': '\x1b[35m',
    'cyan': '\x1b[36m',
    'white': '\x1b[37m',
  }
  mods = {
    'nrm': '\x1b[0m',
    'bold': '\x1b[1m'
  }
  makedirs('dump', exist_ok=True)

def settings_save():
  global settings

  config = ConfigParser()
  with open('settings.ini', 'w') as cf:
    config['SETTINGS'] = settings
    config.write(cf)

def log(*msg):
  clear()
  global login, vk_session, vk, account
  cprint(msg[0] if msg else '[для продолжения необходимо войти]', color='red', mod='bold', offset=2, delay=1/50)
  try:
    login = input('  login: \x1b[1;36m'); print('\x1b[0m',end='')
    password = input('  password: \x1b[1;36m'); print('\x1b[0m',end='')
    vk_session = vk_api.VkApi(login, password, app_id=6631721, auth_handler=auth_handler, api_version=API_VERSION)
    vk_session.auth(token_only=True, reauth=True)
    vk = vk_session.get_api()
    account = vk.account.getProfileInfo()
  except KeyboardInterrupt as kbi:
    goodbye()
  except vk_api.exceptions.ApiError as ae:
    log('Произошла ошибка при попытке авторизации.')
  except vk_api.exceptions.BadPassword as vk_bp:
    log('Неправильный пароль.')
  except vk_api.exceptions.Captcha as vk_captch:
    log('Необходим ввод капчи.')
  except Exception as e:
    raise e

def auth_handler():
  key = input('Введите код двухфакторой аутентификации: ')
  remember_device = True
  return key, remember_device

def download(url, folder, *args):
  kwargs = args[0] if (len(args) == 1 and isinstance(args[0], dict)) else {}

  if 'name' in kwargs:
    fn = '_'.join(kwargs['name'].split(' ')) if settings['REPLACE_SPACES'] else kwargs['name']
    if 'ext' in kwargs:
      if fn.split('.')[-1] != kwargs['ext']:
        fn += '.{}'.format(kwargs['ext'])
  else:
    fn = url.split('/')[-1]

  for c in INVALID_CHARS:
    fn = fn.replace(c, settings['REPLACE_CHAR'])

  if not exists(pjoin(folder, fn)):
    try:
      with open(pjoin(folder, fn), 'wb') as bf:
        bf.write(urlopen(url).read())
    except Exception as e:
      pass



def dump_photos():
  makedirs(pjoin('dump', 'photos'), exist_ok=True)
  albums = vk.photos.getAlbums(need_system=1)

  print('Сохранение фото:')

  for al in albums['items']:
    print('  Альбом "{}":'.format(al['title']))
    folder = pjoin('dump', 'photos', '_'.join(al['title'].split(' '))); makedirs(folder, exist_ok=True)
    photos = vk.photos.get(album_id=al['id'], photo_sizes=1, count=1000)
    count = photos['count']
    if count == 0:
      print('    0/0')
    else:
      for r in range(ceil(count/1000)):
        photos['items'] += vk.photos.get(album_id=al['id'], photo_sizes=1, count=1000, offset=(r+1)*1000)['items']
      urls = []
      for p in photos['items']:
        urls.append(p['sizes'][-1]['url'])
      with Pool() as pool:
        pool.starmap(download, zip(urls, itertools.repeat(folder)))
      print('\r\x1b[2K    {}/{}'.format(len(next(walk(folder))[2]), count))



def dump_audio():
  global folder
  import vk_api.audio

  print('[получение списка аудио]')
  tracks = vk_api.audio.VkAudio(vk_session).get()

  print()

  folder = pjoin('dump', 'audio'); makedirs(folder, exist_ok=True)

  print('Сохранение аудио:')
  count = len(tracks)

  if count == 0:
    print('  0/0')
  else:
    urls = []
    kwargs = []
    for a in tracks:
      urls.append(a['url'])
      kwargs.append({'name': '{artist} - {title}'.format(artist=a['artist'], title=a['title'], id=a['id']), 'ext': 'mp3'})

    with Pool() as pool:
      pool.starmap(download, zip(urls, itertools.repeat(folder), kwargs))
    print('\r\x1b[2K  {}/{}'.format(len(next(walk(folder))[2]), count))



def dump_video():
  from re import search as research

  folder = pjoin('dump', 'video')
  makedirs(folder, exist_ok=True)

  print('Сохранение видео:')

  albums = vk.video.getAlbums(count=100, need_system=1)
  albumsCount = albums['count']

  for ar in range(ceil((albumsCount-100)/100)):
    albums['items'] += vk.video.getAlbums(count=100, need_system=1, offset=(ar+1)*100)['items']

  for al in albums['items']:
    print('  Альбом "{}":'.format(al['title']))
    folder = pjoin('dump', 'video', '_'.join(al['title'].split(' '))); makedirs(folder, exist_ok=True)
    video = vk.video.get(album_id=al['id'], count=200)
    videoCount = video['count']
    if videoCount == 0:
      print('    0/0')
    else:
      for vr in range(ceil((videoCount-200)/200)):
        video['items'] += vk.video.get(album_id=al['id'], count=200, offset=(vr+1)*200)['items']

      urls = []
      kwargs = []
      for v in video['items']:
        urls.append(research(b'https://cs.*vkuservideo.*'+str(v['height']).encode()+b'.mp4', urlopen(v['player']).read()).group(0).decode())
        kwargs.append({'name': v['title']+'_'+str(v['id']), 'ext': 'mp4'}) # во избежание конфликта имён к имени файла добавляется его ID
      with Pool() as pool:
        pool.starmap(download, zip(urls, itertools.repeat(folder), kwargs))
      print('\r\x1b[2K    {}/{}'.format(len(next(walk(folder))[2]), videoCount))



def dump_docs():
  folder = pjoin('dump', 'docs')
  makedirs(folder, exist_ok=True)

  docs = vk.docs.get()

  print('Сохраненние документов:')
  count = docs['count']

  if count == 0:
    print('  0/0')
  else:
    urls = []
    kwargs = []
    for d in docs['items']:
      urls.append(d['url'])
      kwargs.append({'name': d['title']+'_'+str(d['id']), 'ext': d['ext']}) # во избежание конфликта имён к имени файла добавляется его ID
    with Pool() as pool:
      pool.starmap(download, zip(urls, itertools.repeat(folder), kwargs))
    print('\r\x1b[2K  {}/{}'.format(len(next(walk(folder))[2]), count))



def dump_messages():
  def add_user(u):
    if ('deactivated' in u) and (u['deactivated'] == 'deleted') and (u['first_name'] == 'DELETED'):
      name = 'DELETED'
      users[u['id']] = {'name': name, 'length': len(name)}
    else:
      name = u['first_name'] + ' ' + u['last_name']
      users[u['id']] = {'name': name, 'length': len(name)}

  def add_group(g):
    name = g['name']
    users[-g['id']] = {'name': name, 'length': len(name)}


  def message_handler(msg):
    """
      Обработчик сообщений.
      Возвращает массив строк.

      [документация API]
        [вложения]
          [сообщения]
            - vk.com/dev/objects/attachments_m
          [wall_reply]
            - vk.com/dev/objects/attachments_w
    """
    r = []

    if ('fwd_messages' in msg) and msg['fwd_messages']:
      for fwd in msg['fwd_messages']:
        res = message_handler(fwd)
        if len(res) > 0:
          if fwd['from_id'] not in users:
            try:
              add_user(vk.users.get(user_ids=fwd['from_id'])[0])
            except Exception as e:
              users[fwd['from_id']] = {'name': r'{unknown user}', 'length': 3}

          r.append('{name}> {}'.format(res[0], name=users.get(fwd['from_id'])['name']))
          for m in res[1:]:
            r.append('{name}> {}'.format(m, name=' '*len(users.get(fwd['from_id'])['name'])))

    if len(msg['text']) > 0:
      for line in msg['text'].split('\n'):
        r.append(line)

    if msg['attachments']:
      for at in msg['attachments']:
        tp = at['type']
        if tp == 'photo':
          if 'action' not in msg:
            r.append('[фото: {url}]'.format(url=at[tp]['sizes'][-1]['url']))
        elif tp == 'video':
          r.append('[видео: vk.com/video{owid}_{id}]'.format(owid=at[tp]['owner_id'], id=at[tp]['id']))
        elif tp == 'audio':
          r.append('[аудио: {artist} - {title}]'.format(artist=at[tp]['artist'], title=at[tp]['title']))
        elif tp == 'doc':
          r.append('[документ: vk.com/doc{owid}_{id}]'.format(owid=at[tp]['owner_id'], id=at[tp]['id']))
        elif tp == 'link':
          r.append('[ссылка: {title} ({url})]'.format(title=at[tp]['title'], url=at[tp]['url']))
        elif tp == 'market':
          r.append('[товар: {title} ({price}{cur}) [vk.com/market?w=product{owid}_{id}]]'.format(
            title=at[tp]['title'],
            owid=at[tp]['owner_id'],
            id=at[tp]['id'],
            price=at[tp]['price']['amount'],
            cur=at[tp]['price']['currency']['name'].lower()))
        # TODO: доделать market_album
        elif tp == 'market_album':
          r.append('[коллекция товаров: {title}]'.format(title=at[tp]['title']))
        elif tp == 'wall':
          r.append('[пост: vk.com/wall{owid}_{id}]'.format(owid=at[tp]['to_id'], id=at[tp]['id']))
        # TODO: доделать wall_reply: добавить поддержку вложений (а надо ли?)
        elif tp == 'wall_reply':
          if at[tp]['from_id'] not in users:
            add_user(vk.users.get(user_ids=at[tp]['from_id'])[0])
          u = users.get(at[tp]['from_id'])
          r.append('[комментарий к посту от {user}: {text} (vk.com/wall{owid}_{pid}?reply={id})]'.format(
            user=u['name'],
            text=at[tp]['text'],
            owid=at[tp]['owner_id'],
            pid=at[tp]['post_id'],
            id=at[tp]['id']))
        elif tp == 'sticker':
          r.append('[стикер: {url}]'.format(url=at[tp]['images'][-1]['url']))
        elif tp == 'gift':
          r.append('[подарок: {id}]'.format(id=at[tp]['id']))
        elif tp == 'graffiti':
          r.append('[граффити: {url}]'.format(url=at[tp]['url']))
        elif tp == 'audio_message':
          r.append('[голосовое сообщение: {url}]'.format(url=at[tp]['link_mp3']))
        else:
          r.append('[вложение с типом "{tp}"]'.format(tp=tp))

    if 'action' in msg and msg['action']:
      """
        member - совершающий действие
        user - объект действия
      """
      act = msg['action']
      tp = act['type']

      if ('member_id' in act) and (act['member_id'] > 0) and (act['member_id'] not in users):
        try:
          add_user(vk.users.get(user_ids=act['member_id'])[0])
        except Exception as e:
          users[act['member_id']] = {'name': r'{unknown user}', 'length': 3}

      if tp == 'chat_photo_update':
        r.append('[{member} обновил фотографию беседы ({url})]'.format(
          member = users[msg['from_id']]['name'],
          url = msg['attachments'][0]['photo']['sizes'][-1]['url']
        ))
      elif tp == 'chat_photo_remove':
        r.append('[{member} удалил фотографию беседы]'.format(
          member = users[msg['from_id']]['name']
        ))
      elif tp == 'chat_create':
        r.append('[{member} создал чат "{chat_name}"]'.format(
          member = users[msg['from_id']]['name'],
          chat_name = act['text']
        ))
      elif tp == 'chat_title_update':
        r.append('[{member} изменил название беседы на «{chat_name}»]'.format(
          member = users[msg['from_id']]['name'],
          chat_name = act['text']
        ))
      elif tp == 'chat_invite_user':
        r.append('[{member} пригласил {user}]'.format(
          member = users[msg['from_id']]['name'],
          user = users[act['member_id']]['name'] if act['member_id'] > 0 else act['email'],
        ))
      elif tp == 'chat_kick_user':
        r.append('[{member} исключил {user}]'.format(
          member = users[msg['from_id']]['name'],
          user = users[act['member_id']]['name'] if act['member_id'] > 0 else act['email'],
        ))
      elif tp == 'chat_pin_message':
        r.append('[{member} закрепил сообщение #{id}: "{message}"]'.format(
          member = users[msg['from_id']]['name'],
          id = act['conversation_message_id'],
          message = act['message'] if 'message' in act else ''
        ))
      elif tp == 'chat_unpin_message':
        r.append('[{member} открепил сообщение]'.format(
          member = users[msg['from_id']]['name']
        ))
      elif tp == 'chat_invite_user_by_link':
        r.append('[{user} присоединился по ссылке]'.format(
          user = users[msg['from_id']]['name']
        ))

    return r


  folder = pjoin('dump', 'dialogs')
  makedirs(folder, exist_ok=True)

  # get conversations
  print('[получение диалогов...]')
  print('\x1b[2K  0/???', end='\r')
  conversations = vk.messages.getConversations(count=200, extended=1, fields='first_name, last_name, name')
  if 'groups' not in conversations: conversations['groups'] = []
  i, count = len(conversations['items']), conversations['count']
  print('\x1b[2K  {}/{}'.format(i, count), end='\r')
  if i < count:
    for i in range(ceil((conversations['count']-200)/200)):
      tmp = vk.messages.getConversations(count=200, offset=(i+1)*200, extended=1, fields='first_name, last_name, name')
      conversations['items'] += tmp['items']
      if 'profiles' in tmp:
        for p in tmp['profiles']:
          if p not in conversations['profiles']:
            conversations['profiles'] += tmp['profiles']
      if 'groups' in tmp:
        for p in tmp['groups']:
          if p not in conversations['groups']:
            conversations['groups'] += tmp['groups']
      i = len(conversations['items'])
      count = conversations['count'] = tmp['count']
      print('\x1b[2K  {}/{}'.format(i, count), end='\r')
    print()


  users = {}
  for u in conversations['profiles']:
    add_user(u)
  for g in conversations['groups']:
    add_group(g)

  print('Сохранение диалогов:')
  for con in conversations['items']:
    did = con['conversation']['peer']['id']

    if con['conversation']['peer']['type'] == 'user':
      if did not in users:
        add_user(vk.users.get(user_ids=did)[0])
      dialog_name = users.get(did)['name']
    elif con['conversation']['peer']['type'] == 'group':
      dialog_name = users.get(did)['name']
    elif con['conversation']['peer']['type'] == 'chat':
      dialog_name = con['conversation']['chat_settings']['title']
    else:
      dialog_name = r'{unknown}'

    print('  Диалог: {}'.format(dialog_name))
    print('    [кэширование]')
    print('\x1b[2K      0/???', end='\r')
    history = vk.messages.getHistory(peer_id=con['conversation']['peer']['id'], count=200, rev=1, extended=1, fields='first_name,last_name')
    i, count = len(history['items']), history['count']
    print('\x1b[2K      {}/{}'.format(i, count), end='\r')
    if 'profiles' not in history: history['profiles'] = []
    for i in range(ceil((history['count']-200)/200)):
      tmp = vk.messages.getHistory(peer_id=con['conversation']['peer']['id'], offset=(i+1)*200, count=200, rev=1, extended=1, fields='first_name,last_name')
      history['items'] += tmp['items']
      if 'profiles' in tmp:
        for p in tmp['profiles']:
          if p not in history['profiles']:
            history['profiles'] += tmp['profiles']
      i = len(history['items'])
      count = history['count'] = tmp['count']
      print('\x1b[2K      {}/{}'.format(i, count), end='\r')
    print()

    # [..., {first_name, last_name, id} ...] => {%id%: {name: 'first_name + last_name', length: len(name) }
    for u in history['profiles']:
      if u['id'] not in users:
        add_user(u)

    # write history to .txt file
    for c in INVALID_CHARS:
      dialog_name = dialog_name.replace(c, settings['REPLACE_CHAR'])

    with open(pjoin('dump', 'dialogs', '{}_{id}.txt'.format('_'.join(dialog_name.split(' ')), id=did)), 'w', encoding='utf-8') as f:
      count = len(history['items'])
      print('    [сохранение]')
      print('\x1b[2K      {}/{}'.format(0, count), end='\r')
      prev = None
      for i in range(count):
        m = history['items'][i]
        hold = ' '*(users.get(m['from_id'])['length']+2)
        msg = hold if (prev and prev == m['from_id']) else users.get(m['from_id'])['name']+': '

        res = message_handler(m)
        if res:
          msg += res[0] + '\n'
          for r in res[1:]:
            msg += hold + r + '\n'

        f.write(msg)
        prev = m['from_id']
        print('\x1b[2K      {}/{}'.format(i+1, count), end='\r')
    print(); print()



### GUI funcs

clear = lambda: print('\x1b[2J', '\x1b[1;1H', end='', flush=True)

def lprint(*args, **kwargs):
  print('\x1b[?25l')
  for s in args:
    if (s.find('\x1b') == -1) and ('slow' in kwargs):
      for ch in s:
        stdout.write(ch); stdout.flush()
        sleep(kwargs['delay'] if 'delay' in kwargs else 1/30)
    else:
      print(s, end='')
  print('\x1b[?25h')

def cprint(msg, **kwargs):
  if not 'offset' in kwargs: kwargs['offset'] = 0
  kwargs['color'] = colors[kwargs['color']] if 'color' in kwargs else mods['nrm']
  if 'mod' in kwargs: kwargs['color'] += mods[kwargs['mod']]

  lprint(kwargs['color']+'\x1b[{y};{x}H'.format(x=int(w/2-len(msg)/2), y=int(h/2-(len(msg.split('\n'))/2)+1-kwargs['offset'])), msg, mods['nrm'], **kwargs)

def welcome():
  clear()
  msg = [
    '\x1b[1;32m', NAME,
    '\x1b[0m', 'v'+VERSION
  ]
  for i in range(len(msg[::2])):
    lprint(msg[i*2]+'\x1b[{y};{x}H'.format(x=int(w/2-len(msg[i*2+1])/2), y=int(h/2-(len(msg)/2)+i+2)), msg[i*2+1], slow=True)
  print('\x1b[?25l')
  sleep(2)
  print('\x1b[?25h')

def goodbye():
  clear()
  msg = ['\x1b[1;32m', 'Спасибо за использование скрипта :з']
  for i in range(len(msg[::2])):
    lprint(msg[i*2]+'\x1b[{y};{x}H'.format(x=int(w/2-len(msg[i*2+1])/2), y=int(h/2-(len(msg)/2)+i+1)), msg[i*2+1], delay=1/50, slow=True)
  raise SystemExit

def logInfo():
  global account

  log_info = [
    'Login: \x1b[1;36m{}\x1b[0m'.format(login),
    'Name: \x1b[1;36m{fn} {ln}\x1b[0m'.format(fn=account['first_name'], ln=account['last_name'])
  ]
  ln = 0
  for l in log_info:
    ln = max(len(l), ln)

  print('\x1b[1;31m'+'-'*(ln-7), end='\x1b[0m\n')
  for l in log_info:
    print('\x1b[31m>\x1b[0m '+l)
  print('\x1b[1;31m'+'-'*(ln-7), end='\x1b[0m\n')

def settings_screen():
    clear(); logInfo(); print()
    print('Настройки:\n')

    i = 0
    for s in settings:
      print('\x1b[34m[{ind}]\x1b[0m {name}: {clr}{value}{nrm}'.format(ind=i+1, name=settings_names[s], value=settings[s], clr=colors['yellow'], nrm=mods['nrm']))
      i += 1

    print('\n\x1b[34m[0]\x1b[0m В меню')

    try:
      choice = int(input('> '))
      if choice == 0:
        menu()
      elif choice not in range(1, len(settings)+1):
        raise IndexError()
      else:
        s = [s for s in settings][choice-1]; new = None
        if isinstance(settings[s], bool):
          settings[s] = not settings[s]
        else:
          while (type(new) is not type(settings[s])) or (s == 'REPLACE_CHAR' and new in INVALID_CHARS):
            new = input('\nВведите новое значение для {clr}{}{nrm} ({tclr}{type}{nrm})\n> '.format(s, clr=colors['red'], tclr=colors['yellow'], nrm=mods['nrm'], type=type(settings[s])))
          settings[s] = new
        settings_save()

      settings_screen()
    except IndexError as ie:
      cprint('Выберите одну из доступных настроек', color='red', mode='bold'); sleep(2); clear(); settings_screen()
    except ValueError as ve:
      settings_screen()
    except KeyboardInterrupt as kbi:
      goodbye()

def menu():
  clear(); logInfo(); print()

  actions = [
    'Фото (по альбомам)', dump_photos,
    'Аудио', dump_audio,
    'Видео (по альбомам)', dump_video,
    'Документы', dump_docs,
    'Сообщения', dump_messages
  ]

  print('Дамп данных:\n')

  for i in range(int(len(actions)/2)):
    print('\x1b[34m[{ind}]\x1b[0m {name}'.format(ind=i+1, name=actions[i*2]))
  print('\n\x1b[34m[8]\x1b[0m Все данные')
  print('\n\x1b[34m[9]\x1b[0m Настройки')
  print('\x1b[34m[0]\x1b[0m Выход')

  print()
  try:
    choice = int(input('> '))
    if choice == 0:
      choice = exit
    elif choice == 9:
      choice = settings_screen
    elif choice == 8:
      choice = [actions[i] for i in range(len(actions)) if i % 2 == 1]
    else:
      choice = actions[(choice-1)*2+1]

    if choice is exit:
      goodbye()
    elif isinstance(choice, list):
      for c in choice:
        c(); print()
    else:
      choice()
      if choice is not settings_screen:
        print('\n\x1b[32mСохранение успешно завершено :з\x1b[0m')
        input('\n[нажмите {clr}Enter{nrm} для продолжения]'.format(clr=colors['cyan']+mods['bold'], nrm=mods['nrm']))
      menu()
  except IndexError as ie:
    cprint('Выберите действие из доступных', color='red', mode='bold'); sleep(2); clear(); menu()
  except ValueError as ve:
    menu()
  except KeyboardInterrupt as kbi:
    goodbye()


if __name__ == '__main__':
  stdout.write('\x1b]0;{}\x07'.format(NAME))
  init()
  welcome()
  log()
  menu()

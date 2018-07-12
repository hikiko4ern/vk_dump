### Imports

from time import sleep
from os import makedirs, get_terminal_size
from os.path import exists, join as pjoin
from sys import stdout
from urllib.request import urlretrieve, urlopen
from math import ceil

import vk_api

VERSION = '0.3'

### Dump funcs

def init():
  global w, h, colors, mods
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

def log(*msg):
  clear()
  global login, password, vk
  cprint(msg[0] if msg else '[для продолжения необходимо войти]', color='red', mod='bold', offset=2, delay=1/50)
  try:
    login = input('  login: \x1b[1;36m'); print('\x1b[0m',end='')
    password = input('  password: \x1b[1;36m'); print('\x1b[0m',end='')
    vk_session = vk_api.VkApi(login, password, app_id=6631721, auth_handler=auth_handler)
    vk_session.auth(token_only=True)
    vk = vk_session.get_api()
  except KeyboardInterrupt as kbi:
    goodbye()
  except Exception as e:
    if e.args[0] == 'Bad password':
      log('Неверный пароль. Попробуйте ещё раз.')
    else:
      raise e

def auth_handler():
  key = input('Введите код двухфакторой аутентификации: ')
  remember_device = True
  return key, remember_device

def download(url, folder, **kwargs):
  if 'name' in kwargs:
    fn = '_'.join(kwargs['name'].split(' '))
    if 'ext' in kwargs:
      if fn.split('.')[-1] != kwargs['ext']:
        fn += '.{}'.format(kwargs['ext'])
  else:
    fn = url.split('/')[-1]
  
  if not exists(pjoin(folder, fn)):
    urlretrieve(url, pjoin(folder, fn))


def dump_photos():
  makedirs(pjoin('dump', 'photos'), exist_ok=True)
  albums = vk.photos.getAlbums(need_system=1)

  print('Сохранение фото:')

  for al in albums['items']:
    print('  Альбом "{}":'.format(al['title']))
    folder = pjoin('dump', 'photos', '_'.join(al['title'].split(' '))); makedirs(folder, exist_ok=True)
    photos = vk.photos.get(album_id=al['id'], photo_sizes=1, count=1000)
    i, count = 1, photos['count']
    if count == 0:
      print('\r    0/0')
    else:
      for r in range(ceil(count/1000)):
        for p in photos['items']:
          print('\r    {}/{}'.format(i, count), end='')
          download(p['sizes'][-1]['src'], folder)
          i += 1
        photos = vk.photos.get(album_id=al['id'], photo_sizes=1, count=1000, offset=(r+1)*1000)
      print()
  print('\x1b[32mСохранение успешно завершено :з\x1b[0m')
  input('\n[нажмите {clr}Enter{nrm} для продолжения]'.format(clr=colors['cyan']+mods['bold'], nrm=mods['nrm']))


def dump_video():
  from urllib.request import urlopen
  from re import search as research

  folder = pjoin('dump', 'video')
  makedirs(folder, exist_ok=True)

  print('Сохранение видео:')

  albums = vk.video.getAlbums(count=100, need_system=1)
  albumsCount = albums['count']

  for ar in range(ceil(albumsCount/100)):
    for al in albums['items']:
      print('  Альбом "{}":'.format(al['title']))
      folder = pjoin('dump', 'video', '_'.join(al['title'].split(' '))); makedirs(folder, exist_ok=True)
      video = vk.video.get(album_id=al['id'], count=200)
      i, videoCount = 1, video['count']
      if videoCount == 0:
        print('\r    0/0')
      else:
        for vr in range(ceil(videoCount/200)):
          for v in video['items']:
            print('\r    {}/{}'.format(i, videoCount), end='')
            download(
              research(b'https://cs.*vkuservideo.*'+str(v['height']).encode()+b'.mp4', urlopen(v['player']).read()).group(0).decode(),
              folder, name=v['title']+'_'+str(v['id']), ext='mp4')
              # во избежание конфликта имён к имени файла добавляется его ID
            i += 1
          video = vk.video.get(album_id=al['id'], count=200, offset=(vr+1)*200)
    albums = vk.video.getAlbums(count=100, need_system=1, offset=(ar+1)*100)
  print()
  print('\x1b[32mСохранение успешно завершено :з\x1b[0m')
  input('\n[нажмите {clr}Enter{nrm} для продолжения]'.format(clr=colors['cyan']+mods['bold'], nrm=mods['nrm']))



def dump_docs():
  folder = pjoin('dump', 'docs')
  makedirs(folder, exist_ok=True)
  docs = vk.docs.get()
  print('Сохраненние документов:')
  i, count = 1, docs['count']
  if count == 0:
    print('\r  0/0')
  else:
    for d in docs['items']:
      print('\r  {}/{}'.format(i, count), end='')
      download(d['url'], folder, name=d['title']+'_'+str(d['id']), ext=d['ext'])
      # во избежание конфликта имён к имени файла добавляется его ID
      i += 1
  print()
  print('\x1b[32mСохранение успешно завершено :з\x1b[0m')
  input('\n[нажмите {clr}Enter{nrm} для продолжения]'.format(clr=colors['cyan']+mods['bold'], nrm=mods['nrm']))



### GUI funcs

clear = lambda: print('\x1b[2J', '\x1b[1;1H', end='', flush=True)

def lprint(*args, **kwargs):
  for s in args:
    if s.find('\x1b') == -1:
      for ch in s:
        stdout.write(ch); stdout.flush()
        sleep(kwargs['delay'] if 'delay' in kwargs else 1/30)
    else:
      print(s, end='')
  print()

def cprint(msg, **kwargs):
  if not 'offset' in kwargs: kwargs['offset'] = 0
  kwargs['color'] = colors[kwargs['color']] if 'color' in kwargs else mods['nrm']
  if 'mod' in kwargs: kwargs['color'] += mods[kwargs['mod']]
  
  lprint(kwargs['color']+'\x1b[{y};{x}H'.format(x=int(w/2-len(msg)/2), y=int(h/2-(len(msg.split('\n'))/2)+1-kwargs['offset'])), msg, mods['nrm'], **kwargs)

def welcome():
  clear()
  msg = [
    '\x1b[1;32m', 'VK Dump Tool',
    '\x1b[0m', 'v'+VERSION
  ]
  for i in range(len(msg[::2])):
    lprint(msg[i*2]+'\x1b[{y};{x}H'.format(x=int(w/2-len(msg[i*2+1])/2), y=int(h/2-(len(msg)/2)+i+2)), msg[i*2+1])
  print('\x1b[?25l')
  sleep(2)
  print('\x1b[?25h')

def goodbye():
  clear()
  msg = ['\x1b[1;32m', 'Спасибо за использование скрипта :з']
  for i in range(len(msg[::2])):
    lprint(msg[i*2]+'\x1b[{y};{x}H'.format(x=int(w/2-len(msg[i*2+1])/2), y=int(h/2-(len(msg)/2)+i+1)), msg[i*2+1], delay=1/50)
  exit()

def logInfo():
  account = vk.account.getProfileInfo()
  log = [
    'Login: \x1b[1;36m{}\x1b[0m'.format(login),
    'Name: \x1b[1;36m{fn} {ln}\x1b[0m'.format(fn=account['first_name'], ln=account['last_name'])
  ]
  ln = 0
  for l in log:
    ln = max(len(l), ln)

  print('\x1b[1;31m'+'-'*(ln-7), end='\x1b[0m\n')
  for l in log:
    print('\x1b[31m>\x1b[0m '+l)
  print('\x1b[1;31m'+'-'*(ln-7), end='\x1b[0m\n')

def menu():
  clear(); logInfo(); print()

  actions = [
    'Фото (по альбомам)', dump_photos,
    'Видео (по альбомам)', dump_video,
    'Документы', dump_docs
  ]

  print('Дамп данных:\n')

  for i in range(int(len(actions)/2)):
    print('\x1b[34m[{ind}]\x1b[0m {name}'.format(ind=i+1, name=actions[i*2]))
  print('\n\x1b[34m[0]\x1b[0m Выход')

  print()
  try:
    choice = int(input('> ')); choice = exit if choice == 0 else actions[(choice-1)*2+1]
    if choice is exit:
      goodbye()
    else:
      choice(); menu()
  except IndexError as ie:
    cprint('Выберите действие из доступных', '\x1b[1;31m'); sleep(2); clear(); menu()
  except KeyboardInterrupt as kbi:
    goodbye()


if __name__ == '__main__':
  init()
  welcome()
  log()
  menu()

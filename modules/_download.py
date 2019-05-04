import logging

import os
import os.path
import requests
import shutil
import urllib3

from urllib.request import urlopen
from re import search as research

from youtube_dl import YoutubeDL

logger = logging.Logger(name='youtube-dl', level=logging.FATAL)


def _download(dmp, obj, folder, **kwargs):
    """
    dmp: Dumper class

    possible kwargs:
        name: force filename
        ext: force file extension
        prefix: {prefix}_...
        access_key: get request with access_key
        force: overwrite file if it exists
        text_mode: write in text mode
    """
    if not obj:
        return False

    if isinstance(obj, str):
        url = obj
        del obj
    elif isinstance(obj, dict):
        url = obj.get('url')
        # obj -> kwargs
        for prop in ('name', 'ext', 'prefix', 'access_key',
                     'force', 'text_mode'):
            kwargs.update({
                prop: obj.get(prop) or kwargs.get(prop)
            })

    if kwargs.get('name'):
        fn = '_'.join(kwargs['name'].split(' ')) if dmp._settings['REPLACE_SPACES'] else kwargs['name']
        if 'ext' in kwargs:
            if fn.split('.')[-1] != kwargs['ext']:
                fn += '.{}'.format(kwargs['ext'])
    else:
        fn = url.split('/')[-1]

    if kwargs.get('prefix'):
        fn = str(kwargs['prefix']) + '_' + fn

    if kwargs.get('access_key'):
        url = '{}?access_key={ak}'.format(url, ak=kwargs['access_key'])

    for c in dmp._INVALID_CHARS:
        fn = fn.replace(c, dmp._settings['REPLACE_CHAR'])

    if len(os.path.join(folder, fn).encode('utf-8')) > 255:
        ext = fn.split('.')[-1]
        while len(os.path.join(folder, fn).encode('utf-8')) > 255:
            fn = fn[:len(fn)-len(ext)-1][:-1] + f'.{ext}'

    if not os.path.exists(os.path.join(folder, fn)) or kwargs.get('force'):
        try:
            if kwargs.get('text_mode'):
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
    else:
        return True


def _download_doc(dmp, d, folder):
    return _download(
        dmp,
        d,
        folder,
        name=f'{d.get("title")}_{d.get("id")}',
        ext=d.get('ext')
    )


def _download_video(dmp, v, folder):
    """
    dmp: Dumper class
    """
    if 'platform' in v:
        return _download_external(v['player'], folder)
    else:
        if 'player' not in v:
            return False
        if 'height' not in v:
            v['height'] = 480 if 'photo_800' in v else \
                          360 if 'photo_320' in v else \
                          240

        url = v['player'] if ('access_key' not in v) else f"{v['player']}?access_key={v['access_key']}"
        data = urlopen(url).read()
        try:
            return _download(dmp,
                             research(b'https://cs.*vkuservideo.*'
                                      + str(min(v['height'], v['width']) if ('width' in v) else v['height']).encode()
                                      + b'.mp4', data).group(0).decode(),
                             folder,
                             name=v['title'] + '_' + str(v['id']),
                             ext='mp4')
        except AttributeError:
            return False


def _download_external(url, folder):
    def hook(i):
        nonlocal r
        if i['status'] == 'finished':
            r = True
            return r
        elif i['status'] == 'error':
            r = False
            return r

    if not url:
        return False

    r = None
    if not YoutubeDL({
                      'logger': logger,
                      'outtmpl': os.path.join(folder, '%(title)s_%(id)s.%(ext)s'),
                      'nooverwrites': True,
                      'fixup': 'detect_or_warn',
                      'progress_hooks': (hook,)
                    }).download((url,)):
        return r

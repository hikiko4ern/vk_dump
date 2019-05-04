import os
import os.path
import itertools
from multiprocess import Pool


def dump_docs(dmp):
    """Документы

    dmp: Dumper object
    """
    folder = os.path.join('dump', 'docs')
    os.makedirs(folder, exist_ok=True)

    print('[получение списка документов]')

    docs = dmp._vk.docs.get()

    print('Сохраненние документов:')

    if docs['count'] == 0:
        print('    0/0 (total: {})'.format(len(next(os.walk(folder))[2])))
    else:
        objs = []
        for d in docs['items']:
            objs.append({
                'url': d['url'],
                'name': d['title'] + '_' + str(d['id']),
                'ext': d['ext']
            })

        print('  .../{}'.format(docs['count']), end='\r')
        with Pool(dmp._settings['POOL_PROCESSES']) as pool:
            res = pool.starmap(dmp._download,
                               zip(itertools.repeat(dmp.__class__),
                                   objs,
                                   itertools.repeat(folder)))

        print('\x1b[2K    {}/{} (total: {})'.format(sum(filter(None, res)),
                                                    len(objs),
                                                    len(next(os.walk(folder))[2])))

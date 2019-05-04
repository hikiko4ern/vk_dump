def get_attachments(vk, peer_id, media_fave_type):
    """
    Return object {count: int, items: array of objects},
        where items - {media_fave_type} attachments

    vk: vk_api
    peer_id: int
    media_fave_type: str (photo, video, doc)
    """
    def generate_code(peer_id, media_fave_type, start_from=0):
        code = '''
            var res = API.messages.getHistoryAttachments({"start_from": {arg_start_from}, "peer_id": {arg_peer_id}, "media_type": "{arg_media_fave_type}", "count": 200, "photo_sizes": 1});
            var ans = [res.items];

            var len = res.items.length;
            var next = res.next_from;

            delete res;

            var i = 1;

            while ((len > 0) && (i < 25)) {
                var tmp = API.messages.getHistoryAttachments({"start_from": next, "peer_id": {arg_peer_id}, "media_type": "{arg_media_fave_type}", "count": 200, "photo_sizes": 1});

                len = tmp.items.length;
                if (len > 0) {
                    next = tmp.next_from;
                    ans.push(tmp.items);
                    i = i+1;
                }
            }

            if (len>0) return {"next_from": next, "items": ans};
            else return {"items": ans};
        '''.replace('{arg_start_from}', str(start_from)) \
           .replace('{arg_peer_id}', str(peer_id)) \
           .replace('{arg_media_fave_type}', media_fave_type)
        return code

    res = {'count': 0, 'items': []}
    start_from = 0
    while True:
        tmp = vk.execute(code=generate_code(peer_id, media_fave_type, start_from))
        for t in tmp['items']:
            res['items'].extend(t)
        start_from = tmp.get('next_from')
        if not start_from:
            break
    res['count'] = len(res['items'])
    return res


def get_fave(vk, fave_type):
    """
    Returns object {count: int, items: array of objects},
        items - fave items of {fave_type}

    vk: vk_api
    fave_type: str (posts, photos, videos)
    """
    def generate_code(fave_type, count):
        code = '''
            var cnt = {arg_count};

            var res = API.fave.{arg_fave_type}({"count": cnt});
            var ans = [res.items];

            var len = res.items.length;

            delete res;

            var i = 1;
            var offset = len;

            while ((len > 0) && (i < 25)) {
                var tmp = API.fave.{arg_fave_type}({"count": cnt, "offset": offset});

                len = tmp.items.length;
                if (len > 0) {
                    offset = offset + cnt;
                    ans.push(tmp.items);
                    i = i+1;
                }
            }

            if (len>0) return {"offset": offset, "items": ans};
            else return {"items": ans};
        '''.replace('{arg_fave_type}', fave_type).replace('{arg_count}', str(count))
        return code

    if fave_type == 'posts':
        fave_type = 'getPosts'
        count = 100
    elif fave_type == 'photos':
        fave_type = 'getPhotos'
        count = 500
    elif fave_type == 'videos':
        fave_type = 'getVideos'
        count = 500
    else:
        return ValueError('Incorret value of "fave_type"')

    res = {'count': 0, 'items': []}
    offset = 0
    while True:
        tmp = vk.execute(code=generate_code(fave_type, count))
        for t in tmp['items']:
            res['items'].extend(t)
        offset = tmp.get('offset')
        if not offset:
            break
    res['count'] = len(res['items'])
    return res

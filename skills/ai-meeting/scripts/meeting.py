import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def message_page(data, after, offset, max_bytes):
    max_bytes -= 2  # Reserve the Windows stdout line ending.
    messages = data.get('messages', [])
    meta = data.get('meta', {})
    page = {'meta': {k: meta[k] for k in ('title', 'closed') if k in meta},
            'messages': [], 'last_seq': after, 'next_offset': offset,
            'latest_seq': data['last_seq'], 'has_more': bool(messages)}
    if len(encode(page).encode('utf-8')) > max_bytes:
        raise ValueError('會議標題過長，請先用 snapshot 保存完整紀錄。')
    for index, message in enumerate(messages):
        text = message.get('text', '')
        start = offset if index == 0 else 0
        if not 0 <= start <= len(text):
            raise ValueError('訊息位移超出範圍，請核對上頁 next_offset 與 last_seq。')

        def candidate(end):
            complete = end == len(text)
            item = {k: message[k] for k in ('seq', 'who', 'at', 'imgs') if k in message}
            item.update(text=text[start:end], text_offset=start, text_complete=complete)
            return {**page, 'messages': page['messages'] + [item],
                    'last_seq': message['seq'] if complete else page['last_seq'],
                    'next_offset': 0 if complete else end,
                    'has_more': not complete or index + 1 < len(messages)}

        whole = candidate(len(text))
        if len(encode(whole).encode('utf-8')) <= max_bytes:
            page = whole
            continue
        low, high = start, len(text) - 1
        end = None
        while low <= high:
            middle = (low + high) // 2
            if len(encode(candidate(middle)).encode('utf-8')) <= max_bytes:
                end = middle
                low = middle + 1
            else:
                high = middle - 1
        if end is not None and end > start:
            page = candidate(end)
        elif not page['messages']:
            raise ValueError('訊息附件或欄位超出輸出上限，請用 snapshot 保存完整紀錄。')
        return page
    return page


def request(base, path, body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(base + path, data=data,
                                 headers={'Content-Type': 'application/json', 'Origin': base})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def main():
    p = argparse.ArgumentParser(description='Codex 會議主持：指定會議、分頁讀取與有界等待。')
    p.add_argument('--base', required=True)
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('rooms')
    for cmd in ('read', 'say', 'watch', 'snapshot'):
        q = sub.add_parser(cmd)
        q.add_argument('room')
        if cmd == 'say':
            q.add_argument('--file', required=True)
        elif cmd == 'snapshot':
            q.add_argument('--out', required=True)
        else:
            q.add_argument('--after', type=int, default=0)
            q.add_argument('--offset', type=int, default=0)
            q.add_argument('--max-bytes', type=int, default=6000)
        if cmd == 'watch':
            q.add_argument('--seconds', type=int, choices=range(1, 46), default=45)
    a = p.parse_args()
    if a.cmd in ('read', 'watch') and (a.after < 0 or a.offset < 0 or not 2048 <= a.max_bytes <= 12000):
        p.error('序號與位移不可為負數；輸出上限須介於 2048 與 12000 位元組。')
    base = a.base.rstrip('/')
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.path not in ('', '/'):
        p.error('--base 須為 http(s) 主機網址，不可含子路徑。')
    if a.cmd == 'rooms':
        result = request(base, '/api/rooms')
    else:
        path = '/api/rooms/' + urllib.parse.quote(a.room, safe='') + '/messages'
        if a.cmd == 'snapshot':
            data = request(base, path + '?after=0')
            output = Path(a.out).expanduser()
            output.mkdir(parents=True, exist_ok=True)
            messages = data.get('messages', [])
            cursor = {'base': base, 'room': a.room, 'last_seq': data['last_seq'],
                      'message_count': len(messages)}
            transcript = '# ' + data.get('meta', {}).get('title', a.room) + '\n\n'
            for msg in messages:
                transcript += '## #' + str(msg['seq']) + ' ' + msg['who'] + ' ' + msg.get('at', '') + '\n\n' + msg['text'] + '\n\n'
                if msg.get('imgs'):
                    transcript += '附件：' + ', '.join(msg['imgs']) + '\n\n'
            files = {'room_snapshot.json': json.dumps(data, ensure_ascii=False, indent=2),
                     'transcript.md': transcript,
                     'cursor.json': json.dumps(cursor, ensure_ascii=False, indent=2)}
            for name, content in files.items():
                temp = output / (name + '.tmp')
                temp.write_text(content, encoding='utf-8')
                temp.replace(output / name)
            result = {'snapshot_dir': str(output.resolve()), **cursor}
        elif a.cmd == 'say':
            content = Path(a.file).read_text(encoding='utf-8-sig').strip()
            if not content:
                p.error('發言檔案不可為空白。')
            if not content.startswith('【Codex主持】'):
                content = '【Codex主持】\n' + content
            result = request(base, path, {'who': 'Codex主持', 'text': content})
        else:
            deadline = time.monotonic() + (a.seconds if a.cmd == 'watch' else 0)
            while True:
                result = request(base, path + '?after=' + str(a.after))
                if a.cmd == 'read' or result.get('messages') or result.get('meta', {}).get('closed'):
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(3, remaining))
            try:
                result = message_page(result, a.after, a.offset, a.max_bytes)
            except ValueError as error:
                p.error(str(error))
    print(encode(result))


if __name__ == '__main__':
    main()

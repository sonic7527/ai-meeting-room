import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path


def request(base, path, body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(base + path, data=data,
                                 headers={'Content-Type': 'application/json', 'Origin': base})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def main():
    p = argparse.ArgumentParser(description='Codex meeting host: explicit room, incremental messages, bounded waits.')
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
        if cmd == 'watch':
            q.add_argument('--seconds', type=int, choices=range(1, 46), default=45)
    a = p.parse_args()
    base = a.base.rstrip('/')
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.path not in ('', '/'):
        p.error('--base must be an http(s) origin')
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
                    transcript += 'Attachments: ' + ', '.join(msg['imgs']) + '\n\n'
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
                p.error('message file is empty')
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
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()

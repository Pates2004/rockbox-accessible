#!/usr/bin/python3
import hashlib
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


root = Path(os.environ['R1_FAKE_ROOT']).resolve(strict=True)
command, *arguments = sys.argv[1:]
with (root / 'commands.jsonl').open('a', encoding='utf-8') as receipt:
    fcntl.flock(receipt, fcntl.LOCK_EX)
    receipt.seek(0, os.SEEK_END)
    receipt.write(json.dumps([command, *arguments]) + '\n')
    receipt.flush()
if command == os.environ.get('R1_FAKE_FAIL'):
    sys.exit(77)


def confined(value):
    candidate = Path(value)
    if not candidate.is_absolute() or not candidate.resolve().is_relative_to(root):
        raise RuntimeError('Fake utility refused access outside private fixture: ' + value)
    return candidate


if command == 'dd':
    options = dict(argument.split('=', 1) for argument in arguments)
    if set(options) - {'if', 'of', 'bs', 'count', 'conv'}:
        raise RuntimeError('Unexpected dd option')
    limit = int(options.get('bs', '512')) * int(options.get('count', '1'))
    if limit > 65536 or int(options.get('count', '1')) != 1:
        raise RuntimeError('Unbounded diagnostic read')
    if 'if' in options:
        with confined(options['if']).open('rb') as source:
            content = source.read(limit)
    else:
        content = sys.stdin.buffer.read(limit)
    if 'of' in options:
        with confined(options['of']).open('r+b') as destination:
            destination.write(content)
    else:
        sys.stdout.buffer.write(content)
elif command == 'sha256sum':
    with confined(arguments[0]).open('rb') as source:
        checksum = hashlib.file_digest(source, 'sha256').hexdigest()
    print(checksum + '  ' + arguments[0])
elif command == 'mktemp':
    template = confined(arguments[1])
    print(tempfile.mkdtemp(prefix=template.name.replace('XXXXXX', ''), dir=template.parent))
elif command == 'cp':
    shutil.copyfile(confined(arguments[0]), confined(arguments[1]))
elif command == 'chmod':
    confined(arguments[1]).chmod(int(arguments[0], 8))
elif command == 'rm':
    for argument in arguments[1:]:
        confined(argument).unlink(missing_ok=True)
elif command == 'rmdir':
    confined(arguments[0]).rmdir()
elif command == 'readlink':
    path = confined(arguments[0])
    mapping = root / 'links.json'
    links = json.loads(mapping.read_text()) if mapping.exists() else {}
    if str(path) in links:
        print(links[str(path)])
    else:
        print(os.readlink(path))
elif command == 'stat':
    confined(arguments[-1]).stat()
    print('type=character special file mode=600 major=a minor=f2')
elif command == 'ls':
    if arguments[0] != '-ldn':
        raise RuntimeError('Unexpected ls invocation')
    confined(arguments[1]).stat()
    print('crw------- 1 0 0 10, 242 Jan 1 00:00 ' + arguments[1])
elif command == 'timeout':
    if arguments == ['--help']:
        print('timeout [-s SIG] SECS PROG ARGS')
    elif arguments[:3] == ['-s', 'KILL', '3'] and arguments[4:] == ['show']:
        confined(arguments[3])
        print('Controller fixture-controller Powered: no')
    else:
        raise RuntimeError('Unexpected timeout invocation')
else:
    raise RuntimeError('Fake utility refused command: ' + command)

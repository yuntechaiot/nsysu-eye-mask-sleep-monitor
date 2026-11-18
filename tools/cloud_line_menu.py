"""Publish the shared cloud binding menu; preview by default, no backend startup.

Only the known legacy Demo owner's personal override is removed. Existing menu
objects and a private checkpoint are retained for --restore CHECKPOINT.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import uuid

from live_line_menu import ROOT, binding_rich_menu, read_json, render_menu, save_json
import requests


def access_token(directory):
    token = os.environ.get('NSYSU_LINE_CHANNEL_ACCESS_TOKEN')
    if token:
        return token
    for line in (directory / 'secrets.env').read_text(encoding='utf-8-sig').splitlines():
        key, separator, value = line.partition('=')
        if separator and key.strip() == 'NSYSU_LINE_CHANNEL_ACCESS_TOKEN':
            return value.strip()
    raise RuntimeError('Private cloud LINE token missing')


def publish(directory, image, restore=None):
    token = access_token(directory)

    def api(method, path, *, content=False, missing=False, binary=False, **kwargs):
        origin = 'https://api-data.line.me' if content else 'https://api.line.me'
        headers = {'Authorization': 'Bearer ' + token, **kwargs.pop('headers', {})}
        response = requests.request(method, origin + '/v2/bot/' + path, headers=headers,
                                    timeout=20, allow_redirects=False, **kwargs)
        if missing and response.status_code == 404:
            return None
        if not 200 <= response.status_code < 300:
            raise RuntimeError('LINE menu request refused (HTTP ' + str(response.status_code) + ')')
        if binary:
            return response.content
        return json.loads(response.content) if response.content else {}

    if api('GET', 'info').get('basicId') != '@823bciot':
        raise RuntimeError('Official account mismatch')
    if restore:
        saved = read_json(restore)
        if api('GET', 'user/all/richmenu', missing=True) != {'richMenuId': saved['created_menu']}:
            raise RuntimeError('Default menu changed since checkpoint; restore refused')
        user_path = 'user/' + saved['legacy_owner'] + '/richmenu'
        current = api('GET', user_path, missing=True)
        if current not in (None, {'richMenuId': saved['created_menu']}, saved['previous_owner_menu']):
            raise RuntimeError('Personal menu changed since checkpoint; restore refused')
        prior = saved['previous_default_menu']
        api('POST', 'user/all/richmenu/' + prior['richMenuId']) if prior else api('DELETE', 'user/all/richmenu')
        if saved['previous_owner_menu']:
            api('POST', user_path + '/' + saved['previous_owner_menu']['richMenuId'])
        if api('GET', 'user/all/richmenu', missing=True) != prior:
            raise RuntimeError('Default restore readback mismatch')
        if api('GET', user_path, missing=True) != saved['previous_owner_menu']:
            raise RuntimeError('Personal restore readback mismatch')
        return {'restored_previous_default_and_owner': True}

    owner = read_json(ROOT / 'private/live-demo/config.json')['allowed_line_user']
    user_path = 'user/' + owner + '/richmenu'
    previous_owner = api('GET', user_path, missing=True)
    known = read_json(ROOT / 'private/live-demo/menu-current.json')['rich_menu_id']
    if previous_owner and previous_owner.get('richMenuId') != known:
        raise RuntimeError('Owner personal menu is not the known legacy Demo menu')
    saved = {'official_account': '@823bciot', 'legacy_owner': owner,
             'previous_default_menu': api('GET', 'user/all/richmenu', missing=True),
             'previous_owner_menu': previous_owner, 'created_menu': None}
    checkpoint = directory / 'backups' / ('default-menu-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8] + '.json')
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    save_json(checkpoint, saved)
    definition = binding_rich_menu()
    api('POST', 'richmenu/validate', json=definition)
    menu = api('POST', 'richmenu', json=definition)['richMenuId']
    saved['created_menu'] = menu
    save_json(checkpoint, saved)
    picture = image.read_bytes()
    api('POST', 'richmenu/' + menu + '/content', content=True,
        data=picture, headers={'Content-Type': 'image/png'})
    downloaded = api('GET', 'richmenu/' + menu + '/content', content=True, binary=True)
    if hashlib.sha256(downloaded).digest() != hashlib.sha256(picture).digest():
        raise RuntimeError('Uploaded menu image readback mismatch')
    actual = api('GET', 'richmenu/' + menu)
    if any(actual.get(key) != value for key, value in definition.items()):
        raise RuntimeError('Menu action readback mismatch')
    api('POST', 'user/all/richmenu/' + menu)
    if api('GET', 'user/all/richmenu', missing=True) != {'richMenuId': menu}:
        raise RuntimeError('Default menu readback mismatch')
    if previous_owner:
        if api('GET', user_path, missing=True) != previous_owner:
            raise RuntimeError('Owner personal menu changed during publication')
        api('DELETE', user_path)
    if api('GET', user_path, missing=True) not in (None, {'richMenuId': menu}):
        raise RuntimeError('Old personal menu still takes precedence')
    save_json(directory / 'default-menu-current.json', {'checkpoint': str(checkpoint), 'rich_menu_id': menu, 'verified': True})
    return {'default_menu_for_all_followers': True, 'legacy_owner_override_removed': bool(previous_owner),
            'image_and_actions_verified': True, 'checkpoint_created': True, 'messages_sent': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=ROOT / 'private/cloud-line')
    parser.add_argument('--font-directory', type=Path, default=Path('C:/Windows/Fonts'))
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--apply', action='store_true')
    group.add_argument('--restore', type=Path)
    args = parser.parse_args()
    output = ROOT / 'artifacts/cloud-line-acceptance/binding-menu.png'
    render_menu(output, args.font_directory, footer='睡眠日誌・研究帳號管理')
    if not args.apply and not args.restore:
        print({'preview': str(output), 'network_changes': False})
        return
    print(publish(args.directory, output, args.restore))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Cloud menu operation failed; inspect private checkpoint/settings. No credentials logged.') from None

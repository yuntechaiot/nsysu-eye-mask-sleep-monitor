"""Preview/apply a rich menu ONLY to the confirmed local Demo recipient.

No default/all-followers mutation. Preserve the previous per-user association
before linking; --restore CHECKPOINT restores it without deleting other menus.
"""
import argparse
from datetime import datetime
from pathlib import Path
import sys
import uuid

from PIL import Image, ImageDraw, ImageFont
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from nsysu.line_menu import binding_rich_menu  # noqa: E402
from nsysu.live_demo import DemoRuntime, read_json, save_json  # noqa: E402


def render_menu(path, font_directory):
    # Palette and type follow the existing quiet blue/white binding page.
    image = Image.new('RGB', (2500, 843), '#f5f5f7')
    draw = ImageDraw.Draw(image)
    def regular(size):
        return ImageFont.truetype(str(font_directory / 'msjh.ttc'), size)

    def bold(size):
        return ImageFont.truetype(str(font_directory / 'msjhbd.ttc'), size)
    for index, (label, ink) in enumerate([
        ('開始綁定', '#0071e3'),
        ('重新綁定', '#0071e3'),
        ('取消綁定', '#953b3b')]):
        left, right = [(0, 833), (833, 1667), (1667, 2500)][index]
        center = (left + right) // 2
        draw.rectangle((left, 0, right, 843), fill='#ffffff' if index != 1 else '#f2f7fd')
        if index:
            draw.line((left, 100, left, 743), fill='#d2d2d7', width=3)
        # Simple line icons, no decorative imagery competing with the actions.
        x, y = center, 230
        if index == 0:
            draw.rounded_rectangle((x-61, y-67, x+61, y+67), radius=22, outline=ink, width=7)
            draw.line((x-31, y, x+31, y), fill=ink, width=7)
            draw.line((x, y-31, x, y+31), fill=ink, width=7)
        elif index == 1:
            draw.arc((x-67, y-67, x+67, y+67), 20, 310, fill=ink, width=8)
            draw.line((x+35, y-68, x+50, y-45, x+20, y-43), fill=ink, width=8)
        else:
            draw.rounded_rectangle((x-61, y-67, x+61, y+67), radius=22, outline=ink, width=7)
            draw.line((x-30, y, x+30, y), fill=ink, width=7)
        draw.text((center, 480), label, anchor='mm', font=bold(176), fill=ink)
    draw.text((1250, 747), '睡眠研究・本機 Demo', anchor='mm', font=regular(60), fill='#6e6e73')
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, default=ROOT / 'private/live-demo')
    parser.add_argument('--font-directory', type=Path, default=Path('C:/Windows/Fonts'))
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--apply', action='store_true')
    group.add_argument('--restore', type=Path)
    args = parser.parse_args()
    output = ROOT / 'artifacts/live-line-demo/binding-menu.png'
    render_menu(output, args.font_directory)
    definition = binding_rich_menu()
    if not args.apply and not args.restore:
        print({'preview': str(output), 'network_changes': False})
        return
    runtime = DemoRuntime(args.directory)
    runtime.service()  # Check the same private single-recipient boundary.
    cfg = runtime.config()
    owner = cfg['allowed_line_user']
    token = read_json(runtime.directory / 'secrets.json')['access_token']

    def api(method, path, *, content=False, missing=False, **kwargs):
        origin = 'https://api-data.line.me' if content else 'https://api.line.me'
        headers = {'Authorization': 'Bearer ' + token, **kwargs.pop('headers', {})}
        response = requests.request(method, origin + '/v2/bot/' + path, headers=headers,
                                    timeout=20, allow_redirects=False, **kwargs)
        if missing and response.status_code == 404:
            return None
        if not 200 <= response.status_code < 300:
            raise RuntimeError('LINE menu API refused the operation (HTTP ' + str(response.status_code) + ')')
        return response.json() if response.content else {}

    user_path = 'user/' + owner + '/richmenu'
    if args.restore:
        saved = read_json(args.restore)
        current = api('GET', user_path, missing=True)
        if saved['recipient'] != owner or not current or current.get('richMenuId') != saved['created_menu']:
            raise RuntimeError('Current menu differs from this checkpoint; refusing to overwrite')
        prior = saved['previous_user_menu']
        if prior:
            api('POST', user_path + '/' + prior['richMenuId'])
        else:
            api('DELETE', user_path)
        actual = api('GET', user_path, missing=True)
        if actual != prior:
            raise RuntimeError('Restore verification did not match checkpoint')
        print({'restored_previous_user_menu': True, 'default_menu_changed': False})
        return
    saved = {'recipient': owner, 'previous_user_menu': api('GET', user_path, missing=True),
             'previous_default_menu': api('GET', 'user/all/richmenu', missing=True), 'created_menu': None}
    backup = runtime.directory / 'backups' / ('menu-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8] + '.json')
    backup.parent.mkdir(exist_ok=True)
    save_json(backup, saved)
    api('POST', 'richmenu/validate', json=definition)
    menu = api('POST', 'richmenu', json=definition)['richMenuId']
    saved['created_menu'] = menu
    save_json(backup, saved)
    api('POST', 'richmenu/' + menu + '/content', content=True, data=output.read_bytes(), headers={'Content-Type': 'image/png'})
    api('POST', user_path + '/' + menu)
    verified = api('GET', user_path).get('richMenuId') == menu
    unchanged = api('GET', 'user/all/richmenu', missing=True) == saved['previous_default_menu']
    if not verified or not unchanged:
        raise RuntimeError('Menu readback did not match; use the private checkpoint to restore')
    save_json(runtime.directory / 'menu-current.json', {'checkpoint': str(backup), 'rich_menu_id': menu, 'verified': True})
    print({'menu_linked_to_demo_owner': True, 'default_menu_changed': False, 'checkpoint_created': True})


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Demo menu operation failed. Check private settings/network; no credentials logged.') from None

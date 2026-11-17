"""Three explicit chat actions; no credentials or automatic unlink in a menu."""


def binding_rich_menu():
    columns = [(0, 833, 'start', '開始綁定'), (833, 834, 'rebind', '重新綁定'), (1667, 833, 'cancel', '取消綁定')]
    return {'size': {'width': 2500, 'height': 843}, 'selected': True,
            'name': '睡眠研究帳號管理', 'chatBarText': '研究帳號選單',
            'areas': [{'bounds': {'x': x, 'y': 0, 'width': width, 'height': 843},
                       'action': {'type': 'postback', 'label': label, 'data': 'binding:' + action, 'displayText': label}}
                      for x, width, action, label in columns]}

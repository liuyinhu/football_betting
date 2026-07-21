"""中超球队的中英文名称映射。

把常见中文队名(及别名)映射到 data/apifootball_raw 数据集使用的英文名。
predict.py 使用它, 让用户可以直接输入中文队名。

注意：本表与训练数据(API-Football)的队名保持一致。API-Football 对部分
球队沿用旧译名(如 Shandong Luneng=山东泰山、SHANGHAI SIPG=上海海港)。
"""
from __future__ import annotations

# 英文(API-Football) -> 中文名/别名列表
_EN_TO_ZH = {
    "Beijing Guoan":            ["北京国安", "国安"],
    "Changchun Yatai":          ["长春亚泰", "亚泰"],
    "Chengdu Better City":      ["成都蓉城", "成都", "蓉城"],
    "Chongqing Tongliang Long": ["重庆铜梁龙", "重庆", "铜梁龙"],
    "Dalian Zhixing":           ["大连智行", "大连英博", "大连"],
    "Hangzhou Greentown":       ["杭州绿城", "浙江队", "浙江绿城", "绿城"],
    "Henan Jianye":             ["河南建业", "河南队", "河南嵩山龙门", "建业"],
    "Meizhou Kejia":            ["梅州客家", "梅州"],
    "Nantong Zhiyun":           ["南通支云", "南通"],
    "Qingdao Jonoon":           ["青岛中能", "中能"],
    "Qingdao Youth Island":     ["青岛青春岛", "青春岛"],
    "SHANGHAI SIPG":            ["上海海港", "海港", "上海上港", "上港"],
    "Shandong Luneng":          ["山东泰山", "泰山", "山东鲁能", "鲁能"],
    "Shanghai Shenhua":         ["上海申花", "申花"],
    "Shenyang Urban":           ["沈阳城市", "沈阳"],
    "Shijiazhuang Y. J.":       ["石家庄永昌", "石家庄功夫", "石家庄"],
    "Sichuan Jiuniu":           ["四川九牛", "九牛"],
    "Tianjin Teda":             ["天津泰达", "泰达", "天津津门虎", "津门虎"],
    "Wuhan Three Towns":        ["武汉三镇", "三镇"],
    "Yunnan Yukun":             ["云南玉昆", "玉昆"],
}

# 构建反向映射: 中文 -> 英文
_ZH_TO_EN = {}
for en, zh_list in _EN_TO_ZH.items():
    for zh in zh_list:
        _ZH_TO_EN[zh] = en


def zh_to_en(name: str) -> str | None:
    """输入中文队名, 返回对应的英文队名; 找不到返回 None。"""
    name = name.strip()
    if name in _ZH_TO_EN:
        return _ZH_TO_EN[name]
    # 部分匹配: 任一别名包含于输入中, 或输入包含于别名
    for zh, en in _ZH_TO_EN.items():
        if zh in name or name in zh:
            return en
    return None


def en_to_zh(name: str) -> str | None:
    """输入英文队名, 返回主要的中文名。"""
    zh_list = _EN_TO_ZH.get(name)
    return zh_list[0] if zh_list else None

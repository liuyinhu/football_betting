"""中超球队的中英文名称映射。

把常见中文队名(及别名)映射到 openfootball 数据集使用的英文名。
predict.py 使用它, 让用户可以直接输入中文队名。
"""
from __future__ import annotations

# 英文(openfootball) -> 中文名/别名列表
_EN_TO_ZH = {
    "Beijing Guoan":          ["北京国安", "国安"],
    "Cangzhou Mighty Lions":  ["沧州雄狮", "沧州"],
    "Changchun Yatai":        ["长春亚泰", "亚泰"],
    "Chengdu Rongcheng":      ["成都蓉城", "成都"],
    "Dalian Pro":             ["大连人", "大连一方"],
    "Dalian Yingbo":          ["大连英博", "大连鲲城"],
    "Henan FC":               ["河南队", "河南嵩山龙门", "河南建业", "建业"],
    "Meizhou Hakka":          ["梅州客家", "梅州"],
    "Nantong Zhiyun":         ["南通支云", "南通"],
    "Qingdao Hainiu":         ["青岛海牛", "海牛"],
    "Qingdao West Coast":     ["青岛西海岸", "西海岸"],
    "Shandong Taishan":       ["山东泰山", "泰山", "山东鲁能"],
    "Shanghai Port FC":       ["上海海港", "海港", "上海上港", "上港"],
    "Shanghai Shenhua":       ["上海申花", "申花"],
    "Shenzhen FC":            ["深圳队", "深圳佳兆业"],
    "Shenzhen Peng City":     ["深圳新鹏城", "深圳鹏城", "鹏城"],
    "Tianjin Jinmen Tiger":   ["天津津门虎", "津门虎", "天津泰达", "泰达"],
    "Wuhan Three Towns":      ["武汉三镇", "三镇"],
    "Yunnan Yukun":           ["云南玉昆", "玉昆"],
    "Zhejiang Professional":  ["浙江队", "浙江职业", "浙江绿城"],
    # 较早的球队(若用 2018-2022 训练仍有用)
    "Guangzhou Evergrande":   ["广州恒大", "恒大", "广州队"],
    "Guangzhou R&F":          ["广州富力", "富力"],
    "Jiangsu Suning":         ["江苏苏宁", "苏宁", "江苏舜天"],
    "Tianjin Quanjian FC":    ["天津权健", "权健"],
    "Tianjin Tianhai":        ["天津天海", "天海"],
    "Hebei China Fortune":    ["河北华夏幸福", "华夏幸福", "河北队"],
    "Wuhan Zall":             ["武汉卓尔", "卓尔"],
    "Beijing Renhe":          ["北京人和", "人和"],
    "Chongqing Lifan":        ["重庆力帆", "重庆当代", "重庆两江竞技"],
    "Shanghai SIPG":          ["上海上港"],
    "Guizhou Hengfeng":       ["贵州恒丰"],
    "Wuhan FC":               ["武汉队"],
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

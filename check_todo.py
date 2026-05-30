import json
import sys
import os
from pathlib import Path

"""
        [
            [
                "敏捷提升",
                "攻击提升",
                "残暴"
            ],
            {
                "best_score": 0,
                "have_match_weapon": 0,
                "lv": [
                    0,
                    0,
                    0
                ]
            }
        ],
"""

TARGET_SEC = 0
TARGET_SKILL = 0


TARGET_SEC = {"攻击提升"}
# TARGET_SKILL = {"强攻", "压制", "巧技", "残暴", "附术", "迸发", "夜幕", "效益"}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        path = '.\\dist\\endfield-essence-recognizer\\logs\\FiveCollections_last.json'        
    else:
        path = sys.argv[1]
    print(f"path = {path}")
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise Exception("path not exist")
    data = json.loads(path.read_text(encoding="utf-8"))
    out_path = path.with_suffix(".TODO.md")
    out_txt = []
    if TARGET_SEC:
        out_txt.append(f"# 带有 <font color=\"red\">{TARGET_SEC}</font> 的待刷取基质")
    else:
        out_txt.append(f"# 待刷取基质")
    out_txt.append("||||||")
    out_txt.append("|----|----|----|----|----|")
    todo_list = data["todo"]
    todo_list = list(todo_list)

    def sort_func(o):
        return (
            o[1]["best_score"],
            o[0][1],
            1-o[1]["have_match_weapon"],
            o[0][0],
            o[0][2],
            )

    todo_list.sort(key=sort_func)
    for it in todo_list:
        stats: tuple[str,str,str] = it[0]
        info: dict = it[1]
        if TARGET_SEC and len(TARGET_SEC.intersection(stats)) == 0:
            continue
        if TARGET_SKILL and len(TARGET_SKILL.intersection(stats)) == 0:
            continue
        have_match_weapon = info["have_match_weapon"]
        weaponmatch = "有" if have_match_weapon else "无"
        weaponmatch += "匹配武器"
        weaponmatch = f"<font color=\"{"green" if have_match_weapon else "red"}\">{weaponmatch}</font>"
        if info["best_score"] == 0:
            cur_best = "没有刷到"
        else:
            cur_best = f"**{info["lv"]}**"
        out_txt.append(f"|{stats[0]}|{stats[1]}|{stats[2]}|{weaponmatch}|{cur_best}|")

    out_txt = "\n".join(out_txt)
    out_path.write_text(out_txt,encoding="utf8")

    

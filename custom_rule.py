from dataclasses import dataclass, field
from enum import StrEnum

from endfield_essence_recognizer.utils.log import logger
from endfield_essence_recognizer.core.path import get_logs_dir
import sys

MODE_SCAN = 1  # True: scan   False: act

KEEP_RARE5_SKILL3 = 0


def get_scanner():
    f = sys._getframe(2)
    scanner = None
    for i in range(10):
        if not f:
            break
        if "self" in f.f_locals and "ScannerEngine" in f.f_locals["self"].__class__.__name__:
            scanner = f.f_locals["self"]
            break
        f = f.f_back
    return scanner

scanner = get_scanner()

def fix_drag_pos():
    logger.warning("修改拖拽起点")
    try:
        if scanner._profile.DRAG_START_POS.y == 870:
            p = scanner._profile.DRAG_START_POS
            p2 = p.__class__(x=p.x, y=878)
            scanner._profile.__class__.DRAG_START_POS = property(fget=lambda self: p2)
    except Exception as e:
        logger.warning(f"修改拖拽起点失败 {e}")
    else:
        logger.warning("修改拖拽起点成功")

fix_drag_pos()

type WeaponId = str
type StatId = str


class StatType(StrEnum):
    ATTRIBUTE = "ATTRIBUTE"
    """基质类型：主属性"""
    SECONDARY = "SECONDARY"
    """基质类型：次属性"""
    SKILL = "SKILL"
    """基质类型：技能"""


class EssenceQuality(StrEnum):
    """Enumeration of identified essence qualities."""

    TREASURE = "treasure"
    """Identified as a valuable item based on user settings."""

    TRASH = "trash"
    """Identified as junk or unwanted item."""

    SKIP = "skip"
    """Item should be ignored by automatic actions."""


class ActionTarget(StrEnum):
    DEFAULT = "default"
    LOCK = "lock"
    ABANDON = "abandon"
    NONE = "none"


class RarityLabel(StrEnum):
    """Labels for weapon essence rarity recognition."""

    FIVE = "5"
    FOUR = "4"
    OTHER = "other"


class AbandonStatusLabel(StrEnum):
    """Labels for weapon essence abandon status recognition."""

    ABANDONED = "已弃用"
    NOT_ABANDONED = "未弃用"
    MAYBE_ABANDONED = "不知道是否已弃用"


class LockStatusLabel(StrEnum):
    """Labels for weapon essence lock status recognition."""

    LOCKED = "已锁定"
    NOT_LOCKED = "未锁定"
    MAYBE_LOCKED = "不知道是否已锁定"


@dataclass
class EssenceData:
    """Raw recognition data for a single essence."""

    stats: list[StatId | None]
    """List of identified attribute IDs on the essence."""

    levels: list[int | None]
    """List of identified attribute levels/enhancement values."""

    rarity: RarityLabel
    """The identified rarity of the essence."""

    abandon_label: AbandonStatusLabel
    """The identified 'abandon' (deprecate) button state."""

    lock_label: LockStatusLabel
    """The identified 'lock' button state."""


@dataclass
class EvaluationResult:
    """The judgement result of an essence after evaluation against user settings."""

    quality: EssenceQuality
    """The overall judged quality (Treasure or Trash)."""

    log_message: str
    """The formatted log message to show to the user (contains color tags)."""

    matched_weapons: set[WeaponId] = field(default_factory=set)
    """Set of weapon IDs that this essence is suitable for."""

    is_high_level: bool = False
    """Whether any attribute on the essence exceeded a high-level threshold."""

    action_target: ActionTarget = ActionTarget.DEFAULT
    """Target lock/abandon status"""


@dataclass(frozen=True, slots=True)
class EssenceStatV2:
    """表示单个基质项或子状态/技能。"""

    stat_id: StatId
    """主键、基质的唯一标识符"""
    name: str
    """基质效果的中文显示名称"""
    type: StatType
    """基质类型：主属性、次属性或技能"""


def modify_result(result: EvaluationResult, new_quality: EssenceQuality, new_log: str, action_target:ActionTarget|None=None):
    result.quality = new_quality
    if action_target is not None:
        result.action_target = action_target
    result.log_message = f"【自定义规则: {new_log}】【原始结果: {result.log_message}】"


USEFUL_SECONDARY = (
    "gat_passive_attr_heal",
    "gat_passive_attr_hp",
    "gat_passive_attr_physpell",
    "gat_passive_attr_usp",
)  # 有用的副属性词条：治疗 生命 源石技艺 大招充能


attr_lv_to_score = (0, 1, 30, 90, 210, 450, 900)
skill_lv_to_score = (0, 1, 120, 420)

def calc_ess_score(ess: "EssenceObj"):
    return (attr_lv_to_score[ess.highest_attribute_level] + attr_lv_to_score[ess.highest_secondary_level] + skill_lv_to_score[ess.highest_skill_level], *ess.data.levels)


# ===================================================================================================================





import copy
STAT_ID_TO_NAME = {}
STAT_NAME_TO_ID = {}

StaticGameData = None
Settings = None


def gen_stats_map(data: EssenceData, static_game_data):
    stats_attribute = {}
    stats_secondary = {}
    stats_skill = {}
    _type_to_stats_map = {
        StatType.ATTRIBUTE: stats_attribute,
        StatType.SECONDARY: stats_secondary,
        StatType.SKILL: stats_skill,
    }

    for stat_id, level in zip(data.stats, data.levels, strict=True):
        if stat_id is not None and level is not None:
            stat: EssenceStatV2 = static_game_data.get_stat(stat_id)
            stats_map = _type_to_stats_map[stat.type]
            stats_map[stat.stat_id] = (stat, level)
    return _type_to_stats_map


def get_essence_string(data: EssenceData):
    rets = [f"{STAT_ID_TO_NAME[stat_id]}+{level}" for stat_id, level in zip(data.stats, data.levels, strict=True)]
    return f"< {', '.join(rets)} >"



class EssenceObj:
    rare4_unique_id_cursor = 0
    rare5_unique_id_cursor = 10000

    def __init__(self, data: EssenceData, info: dict, id_=None):
        if id_ is None:
            if data.rarity == RarityLabel.FOUR:
                EssenceObj.rare4_unique_id_cursor += 1
                self.unique_id = EssenceObj.rare4_unique_id_cursor
            elif data.rarity == RarityLabel.FIVE:
                EssenceObj.rare5_unique_id_cursor += 1
                self.unique_id = EssenceObj.rare5_unique_id_cursor
            else:
                raise Exception("rarity 3 treasure?")
        else:
            self.unique_id = id_
        self._cache_str = None
        # =============
        self.data = data
        self.info = info
        self.original_info = copy.deepcopy(info)
        self.is_useful = len(self.info) > 0
        # ===================
        type_to_stats_map = gen_stats_map(data, StaticGameData)
        main_attrs = type_to_stats_map.get(StatType.ATTRIBUTE)
        sec_attrs = type_to_stats_map.get(StatType.SECONDARY)
        skills = type_to_stats_map.get(StatType.SKILL)
        def get_highest_stat_level(stats):
            return max(t[1] for t in stats.values()) if stats else 0

        self.highest_attribute_level = highest_attribute_level = get_highest_stat_level(main_attrs)
        self.highest_secondary_level = highest_secondary_level = get_highest_stat_level(sec_attrs)
        self.highest_skill_level = highest_skill_level = get_highest_stat_level(skills)
        self.is_complete = highest_attribute_level > 0 and highest_secondary_level > 0 and highest_skill_level > 0
        self.sumlv = highest_attribute_level + highest_secondary_level + highest_skill_level


    def serialize(self):
        return {
            "id": self.unique_id,
            "info": self.original_info,
            "essd": [self.data.stats, self.data.levels, self.data.rarity, self.data.abandon_label, self.data.lock_label]
        }

    @classmethod
    def deserialize(cls, d):
        id_ = int(d["id"])
        ed = EssenceData(*d["essd"])
        return EssenceObj(ed, d["info"], id_)


    def __str__(self):
        if not self._cache_str:
            data = self.data
            ret = f"#{self.unique_id} {get_essence_string(data)}"
            self._cache_str = ret
        return self._cache_str

    __repr__ = __str__




class FourCollections:
    instance: "FourCollections" = None
    def __init__(self):
        self.skill_lv3: dict[str, list[EssenceObj]] = {}
        self.secondary_lv3: dict[str, list[EssenceObj]] = {}
        self.attr_high: dict[tuple[str,str], list[EssenceObj]] = {}
        self.total_high: list[EssenceObj] = []
        self.all_objs: dict[int, EssenceObj] = {}
        self.trashes: list[EssenceObj] = []
        self.trashes_set: dict[str, int] = {}

    def add_useful(self, data: EssenceData, info: dict, type_to_stats_map: dict[StatType, dict[StatId, tuple[EssenceStatV2, int]]], static_game_data) -> EssenceObj:
        if not MODE_SCAN:
            raise Exception("add useful is only for scan mode")
        ess = EssenceObj(data, info)
        self.all_objs[ess.unique_id] = ess
        """
        ess_useful_info = {
            "skill_level_3": skill_level_3,
            "useful_secondary_level3": useful_secondary_level3,
            "is_attr_level_high": is_attr_level_high,
            "is_total_level_high": is_total_level_high,
        }
        """
        if 'skill_level_3' in info:
            for skill_stat_id in info['skill_level_3']:
                stat: EssenceStatV2 = static_game_data.get_stat(skill_stat_id)
                self.skill_lv3.setdefault(stat.name, []).append(ess)
        if 'useful_secondary_level3' in info:
            for skill_stat_id in info['useful_secondary_level3']:
                stat: EssenceStatV2 = static_game_data.get_stat(skill_stat_id)
                self.secondary_lv3.setdefault(stat.name, []).append(ess)
        if 'is_attr_level_high' in info:
            main_attrs = type_to_stats_map.get(StatType.ATTRIBUTE)
            sec_attrs = type_to_stats_map.get(StatType.SECONDARY)
            skills = type_to_stats_map.get(StatType.SKILL)
            main_attrs_lv3 = {stat_id: v for stat_id,v in main_attrs.items() if v[1] >= 3}
            sec_attrs_lv3 = {stat_id: v for stat_id,v in sec_attrs.items() if v[1] >= 3}
            if not main_attrs_lv3 or not sec_attrs_lv3:
                raise Exception(f"wtf {data} {info}")
            for _, m in main_attrs_lv3.items():
                for __, s in sec_attrs_lv3.items():
                    self.attr_high.setdefault((m[0].name, s[0].name), []).append(ess)
        if "is_total_level_high" in info:
            self.total_high.append(ess)
        return ess

    def to_string(self):
        str_dict = dict(self.__dict__)
        str_dict["attr_high"] = {str(k):v for k,v in self.attr_high.items()}
        import json
        return json.dumps(str_dict, indent=4, default=lambda obj: str(obj), ensure_ascii=False, sort_keys=True)

    def check_valid(self):
        usefuls = [ess for ess in self.all_objs.values() if ess.is_useful]
        trash = [ess for ess in self.all_objs.values() if not ess.is_useful]
        trash.sort(key=lambda obj: obj.unique_id)
        if trash != self.trashes:
            logger.opt(colors=True).warning(f"!!!trash no match")

    def serialize(self):
        def ess_id_list(ess_list):
            return [ess.unique_id for ess in ess_list]
        sd = {
            "skill_lv3": {k: ess_id_list(v) for k,v in self.skill_lv3.items()},
            "secondary_lv3": {k: ess_id_list(v) for k,v in self.secondary_lv3.items()},
            "total_high": ess_id_list(self.total_high),
            "attr_high": [[k, ess_id_list(v)] for k,v in self.attr_high.items()],
            "all_objs": {k: v.serialize() for k,v in self.all_objs.items()}
        }
        import json
        return json.dumps(sd, indent=4, ensure_ascii=False, sort_keys=True)

    def deserialize(self, d):
        if isinstance(d, str):
            import json
            d = json.loads(d)
        all_objs = self.all_objs
        for k,v in d["all_objs"].items():
            k = int(k)
            all_objs[k] = EssenceObj.deserialize(v)
        for k,v in d["skill_lv3"].items():
            self.skill_lv3[k] = [all_objs[essid] for essid in v]
        for k,v in d["secondary_lv3"].items():
            self.secondary_lv3[k] = [all_objs[essid] for essid in v]
        self.total_high[:] = [all_objs[essid] for essid in d["total_high"]]
        for k,v in d["attr_high"]:
            self.attr_high[tuple(k)] = [all_objs[essid] for essid in v]

    def load_from_last(self):
        last_path = get_logs_dir() / f"{FourCollections.__name__}_last.json"
        if not last_path.exists():
            logger.opt(colors=True).warning(f"!!!未找到紫色基质数据: {last_path}")
            return
        logger.opt(colors=True).warning(f"!!!加载紫色基质数据: {last_path}")
        last_data = last_path.read_text(encoding="utf8")
        self.deserialize(last_data)
        self.check_valid()
        logger.opt(colors=True).warning(f"!!!数据合法检测: {last_data == self.serialize()}")
        self.check_trash()
        logger.opt(colors=True).warning(f"!!!紫色重复垃圾数量: {len(self.trashes)}")
        p = get_logs_dir() / "current_loaded_four.json"
        p.write_text(self.to_string(), encoding="utf8")

    def check_trash(self):
        trashes = set()
        for skill, ess_list in self.skill_lv3.items():
            skill_id = STAT_NAME_TO_ID[skill]
            count = len(ess_list)
            ess_list.sort(key=lambda ess: (ess.highest_attribute_level + ess.highest_secondary_level, *ess.data.levels))
            for i, ess in enumerate(ess_list):
                if count <= 10:
                    break
                if ess.highest_attribute_level >= 3 or ess.highest_secondary_level >= 3:
                    pass
                elif ess.is_complete:
                    pass
                else:
                    # trash
                    count -= 1
                    ess_list[i] = None
                    ess.info["skill_level_3"].remove(skill_id)
                    if not ess.info["skill_level_3"]:
                        ess.info.pop("skill_level_3")
                    ess.is_useful = len(ess.info) > 0
                    if not ess.is_useful:
                        trashes.add(ess)
            ess_list[:] = [t for t in ess_list if t is not None]

        for skill, ess_list in self.secondary_lv3.items():
            skill_id = STAT_NAME_TO_ID[skill]
            def sort_func(ess: EssenceObj):
                return (ess.highest_skill_level*100 + ess.highest_attribute_level, *ess.data.levels)
            count = len(ess_list)
            ess_list.sort(key=sort_func)
            for i, ess in enumerate(ess_list):
                if count <= 15:
                    break
                if ess.highest_attribute_level >= 3 or ess.highest_skill_level >= 3:
                    pass
                elif ess.highest_attribute_level + ess.highest_skill_level >= 4:
                    pass
                # elif ess.is_complete:
                #     pass
                else:
                    # trash
                    count -= 1
                    ess_list[i] = None
                    ess.info["useful_secondary_level3"].remove(skill_id)
                    if not ess.info["useful_secondary_level3"]:
                        ess.info.pop("useful_secondary_level3")
                    ess.is_useful = len(ess.info) > 0
                    if not ess.is_useful:
                        trashes.add(ess)
            ess_list[:] = [t for t in ess_list if t is not None]

        self.trashes = list(trashes)
        self.trashes.sort(key=lambda obj: obj.unique_id)
        self.trashes_set = ts = {}
        self.check_valid()
        for trash in self.trashes:
            ess_str = get_essence_string(trash.data)
            if ess_str not in ts:
                ts[ess_str] = 1
            else:
                ts[ess_str] += 1

    def pop_trash_if_it_is(self, data:EssenceData)->bool:
        ess_str = get_essence_string(data)
        is_trash = False
        ts = self.trashes_set
        if ess_str in ts:
            is_trash = True
            ts[ess_str] -= 1
            if ts[ess_str] == 0:
                ts.pop(ess_str)
        if is_trash:
            logger.opt(colors=True).warning(f"剩余紫色垃圾数量: <red>{sum(ts.values())}个</>")
            if sum(ts.values()) == 0:
                logger.opt(colors=True).warning("已经找到所有的垃圾~~")
        return is_trash



FourCollections.instance = FourCollections()



class FiveCollections:
    instance: "FiveCollections" = None
    def __init__(self):
        self.skill_lv3: dict[tuple[str,str], list[EssenceObj]] = {}
        self.secondary_lv4: dict[str, list[EssenceObj]] = {}
        self.complete: dict[tuple[str,str,str,int],list[EssenceObj]] = {}
        self.all_objs: dict[int, EssenceObj] = {}
        self.trashes: list[EssenceObj] = []
        self.trashes_set: dict[str, int] = {}

    def add_useful(self, data: EssenceData, info: dict, type_to_stats_map: dict[StatType, dict[StatId, tuple[EssenceStatV2, int]]], static_game_data) -> EssenceObj:
        if not MODE_SCAN:
            raise Exception("add useful is only for scan mode")
        ess = EssenceObj(data, info)
        self.all_objs[ess.unique_id] = ess
        """
        ess_useful_info["lv4_attr_lv3_skill"] = [attr_level_4, skill_level_3]
        ess_useful_info["useful_secondary_lv4"] = useful_secondary_level4
        ess_useful_info["complete"] = [bool(non_trash_weapon_ids), list(data.stats)]
        """
        if "lv4_attr_lv3_skill" in info:
            for skill_stat_id in info["lv4_attr_lv3_skill"][1]:
                sk_stat: EssenceStatV2 = static_game_data.get_stat(skill_stat_id)
                for attr_stat_id in info["lv4_attr_lv3_skill"][0]:
                    attr_stat: EssenceStatV2 = static_game_data.get_stat(attr_stat_id)
                    self.skill_lv3.setdefault((attr_stat.name, sk_stat.name), []).append(ess)
        if 'useful_secondary_lv4' in info:
            for skill_stat_id in info['useful_secondary_lv4']:
                stat: EssenceStatV2 = static_game_data.get_stat(skill_stat_id)
                self.secondary_lv4.setdefault(stat.name, []).append(ess)
        if "complete" in info:
            is_match_weapon = 1 if info["complete"][0] else 0
            stats = info["complete"][1]
            stats_names = tuple([static_game_data.get_stat(s).name for s in stats] + [is_match_weapon])
            self.complete.setdefault(stats_names, []).append(ess)

        return ess

    def to_string(self):
        str_dict = dict(self.__dict__)
        for a in ("skill_lv3", "complete"):
            str_dict[a] = {str(k):v for k,v in str_dict[a].items()}
        import json
        return json.dumps(str_dict, indent=4, default=lambda obj: str(obj), ensure_ascii=False, sort_keys=True)

    def check_valid(self):
        usefuls = [ess for ess in self.all_objs.values() if ess.is_useful]
        trash = [ess for ess in self.all_objs.values() if not ess.is_useful]
        trash.sort(key=lambda obj: obj.unique_id)
        if trash != self.trashes:
            logger.opt(colors=True).warning(f"!!!trash no match")

    def gen_todo_list(self):
        stats: dict[StatId, EssenceStatV2] = StaticGameData._stats
        mains = [t for t in stats.values() if t.type == StatType.ATTRIBUTE]
        secs = [t for t in stats.values() if t.type == StatType.SECONDARY]
        sks = [t for t in stats.values() if t.type == StatType.SKILL]
        complete = self.complete
        complete_d = {tuple(k[:-1]): {"have_match_weapon": k[3], "best_score":(calc_ess_score(v[-1])[0]), "lv":list(v[-1].data.levels)} for k,v in complete.items()}
        for main in mains:
            for sec in secs:
                for sk in sks:
                    cur_set = (main.name, sec.name, sk.name)
                    if cur_set not in complete_d:
                        matched_weapon_ids = set(
                            StaticGameData.find_weapons_by_stats(main.stat_id, sec.stat_id, sk.stat_id)
                        )
                        non_trash_weapon_ids = matched_weapon_ids - set(Settings.trash_weapon_ids)
                        complete_d[cur_set] = {"have_match_weapon":1 if non_trash_weapon_ids else 0, "best_score":0, "lv":[0,0,0]}
        todos = []
        for settuple, info in complete_d.items():
            if info["best_score"] <= 3:
                todos.append((settuple, info))
        todos.sort(key=lambda o: (o[1]["best_score"], 1-o[1]["have_match_weapon"], o[0][2], o[0][1], o[0][0]))
        return todos        

    def serialize(self):
        def ess_id_list(ess_list):
            return [ess.unique_id for ess in ess_list]
        sd = {
            "skill_lv3": [[k, ess_id_list(v)] for k,v in self.skill_lv3.items()],
            "secondary_lv4": {k: ess_id_list(v) for k,v in self.secondary_lv4.items()},
            "complete": [[k, ess_id_list(v)] for k,v in self.complete.items()],
            "all_objs": {k: v.serialize() for k,v in self.all_objs.items()},
            "todo": self.gen_todo_list(),
        }
        import json
        return json.dumps(sd, indent=4, ensure_ascii=False, sort_keys=True)

    def deserialize(self, d):
        if isinstance(d, str):
            import json
            d = json.loads(d)
        all_objs = self.all_objs
        for k,v in d["all_objs"].items():
            k = int(k)
            all_objs[k] = EssenceObj.deserialize(v)
        for k,v in d["skill_lv3"]:
            self.skill_lv3[tuple(k)] = [all_objs[essid] for essid in v]
        for k,v in d["secondary_lv4"].items():
            self.secondary_lv4[k] = [all_objs[essid] for essid in v]
        for k,v in d["complete"]:
            self.complete[tuple(k)] = [all_objs[essid] for essid in v]

    def load_from_last(self):
        last_path = get_logs_dir() / f"{FiveCollections.__name__}_last.json"
        if not last_path.exists():
            logger.opt(colors=True).warning(f"!!!未找到金色基质数据: {last_path}")
            return
        logger.opt(colors=True).warning(f"!!!加载金色基质数据: {last_path}")
        last_data = last_path.read_text(encoding="utf8")
        self.deserialize(last_data)
        self.check_valid()
        logger.opt(colors=True).warning(f"!!!数据合法检测: {last_data == self.serialize()}")
        self.check_trash()
        logger.opt(colors=True).warning(f"!!!金色重复垃圾数量: {len(self.trashes)}")
        p = get_logs_dir() / "current_loaded_five.json"
        p.write_text(self.to_string(), encoding="utf8")

    def check_trash(self):
        trashes = set()
        # for stat_pair, ess_list in self.skill_lv3.items():
        #     skill_id = STAT_NAME_TO_ID[skill]
        #     count = len(ess_list)
        #     ess_list.sort(key=lambda ess: ess.highest_attribute_level + ess.highest_secondary_level)
        #     for i, ess in enumerate(ess_list):
        #         if count <= 20:
        #             break
        #         if ess.highest_attribute_level >= 3 or ess.highest_secondary_level >= 3:
        #             pass
        #         elif ess.is_complete:
        #             pass
        #         else:
        #             # trash
        #             count -= 1
        #             ess_list[i] = None
        #             ess.info["skill_level_3"].remove(skill_id)
        #             if not ess.info["skill_level_3"]:
        #                 ess.info.pop("skill_level_3")
        #             ess.is_useful = len(ess.info) > 0
        #             if not ess.is_useful:
        #                 trashes.add(ess)
        #     ess_list[:] = [t for t in ess_list if t is not None]

        for skill, ess_list in self.secondary_lv4.items():
            skill_id = STAT_NAME_TO_ID[skill]
            def sort_func(ess: EssenceObj):
                return (ess.highest_skill_level*100 + ess.highest_attribute_level, *ess.data.levels)
            count = len(ess_list)
            ess_list.sort(key=sort_func)
            for i, ess in enumerate(ess_list):
                if count <= 20:
                    break
                if ess.highest_attribute_level >= 3 or ess.highest_skill_level >= 3:
                    pass
                elif ess.highest_attribute_level + ess.highest_skill_level >= 4:
                    pass
                else:
                    # trash
                    count -= 1
                    ess_list[i] = None
                    ess.info["useful_secondary_lv4"].remove(skill_id)
                    if not ess.info["useful_secondary_lv4"]:
                        ess.info.pop("useful_secondary_lv4")
                    ess.is_useful = len(ess.info) > 0
                    if not ess.is_useful:
                        trashes.add(ess)
            ess_list[:] = [t for t in ess_list if t is not None]



        for stats, ess_list in self.complete.items():
            main, sec, skill, is_match = stats
            main_stat = STAT_NAME_TO_ID[main]
            sec_stat = STAT_NAME_TO_ID[sec]
            skill_stat = STAT_NAME_TO_ID[skill]
            sort_func = calc_ess_score
            
            count = len(ess_list)
            ess_list.sort(key=sort_func)
            for i, ess in enumerate(ess_list):
                if count <= 2:
                    break
                if ess.highest_attribute_level >= 3 or ess.highest_secondary_level >= 3 or ess.highest_skill_level >= 3:
                    pass
                else:
                    # trash
                    count -= 1
                    ess_list[i] = None
                    ess.info.pop("complete")
                    ess.is_useful = len(ess.info) > 0
                    if not ess.is_useful:
                        trashes.add(ess)
            ess_list[:] = [t for t in ess_list if t is not None]

        self.trashes = list(trashes)
        self.trashes.sort(key=lambda obj: obj.unique_id)
        self.trashes_set = ts = {}
        self.check_valid()
        for trash in self.trashes:
            ess_str = get_essence_string(trash.data)
            if ess_str not in ts:
                ts[ess_str] = 1
            else:
                ts[ess_str] += 1

    def pop_trash_if_it_is(self, data:EssenceData)->bool:
        ess_str = get_essence_string(data)
        is_trash = False
        ts = self.trashes_set
        if ess_str in ts:
            is_trash = True
            ts[ess_str] -= 1
            if ts[ess_str] == 0:
                ts.pop(ess_str)
        if is_trash:
            logger.opt(colors=True).warning(f"剩余金色垃圾数量: <red>{sum(ts.values())}个</>")
            if sum(ts.values()) == 0:
                logger.opt(colors=True).warning("已经找到所有的垃圾~~")
        return is_trash



FiveCollections.instance = FiveCollections()






from datetime import datetime
import threading
from pathlib import Path

logger_lock = threading.Lock()

class AutoCloseFile:
    def __init__(self, path: Path, open_mode: str, delay: float, collection):
        self.path = path
        self.open_mode = open_mode
        self.delay = delay
        self._file = None
        self._timer = None
        self.collection = collection

    def before_close(self):
        logger.opt(colors=True).warning(f"!!!开始写入总结日志 {self.path}")
        collection = self.collection
        try:
            collection_info = collection.to_string()
            serialized = collection.serialize()
            self._file.write(f"\n```json\n{collection_info}\n```\n")
            # test serialization
            ins2 = type(collection)()
            ins2.deserialize(serialized)
            logger.opt(colors=True).warning(f"数据合法性检测 = {collection_info == ins2.to_string()}, 序列化合法性 = {serialized == ins2.serialize()}")
            self.path.with_suffix(".json").write_text(serialized, encoding="utf8")
            self.path.with_name(f"{type(collection).__name__}_last.json").write_text(serialized, encoding="utf8")
            collection.check_trash()
            collection.check_valid()
            self._file.write(f"\ncheck trash...\n")
            self._file.write(f"```json\n{collection.to_string()}\n```\n")
        except Exception as e:
            logger.opt(colors=True).warning(f"!!!错误 {e} {type(e)}")
        logger.opt(colors=True).warning(f"!!!写入总结日志完成 {self.path}")
        import gc
        gc.collect()


    def _close(self):
        with logger_lock:
            if self._file is not None:
                self.before_close()
                self._file.close()
                self._file = None
            self._timer = None

    def get(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

        if self._file is None or self._file.closed:
            self._file = self.path.open(self.open_mode, encoding="utf8")

        self._timer = threading.Timer(self.delay, self._close)
        self._timer.daemon = True
        self._timer.start()

        return self._file



time_string = datetime.now().strftime('%Y%m%d_%H%M%S')
if MODE_SCAN:
    rare4_log_file = AutoCloseFile(get_logs_dir() / f"rare4_{time_string}.md", "a", 10, FourCollections.instance)
    rare4_log_file.get().write(f"# MODE SCAN = {MODE_SCAN}\n")
    rare5_log_file = AutoCloseFile(get_logs_dir() / f"rare5_{time_string}.md", "a", 10, FiveCollections.instance)
    rare5_log_file.get().write(f"# MODE SCAN = {MODE_SCAN}\n")
else:
    rare4_log_file = None
    rare5_log_file = None






def custom_rule(data: EssenceData, setting, static_game_data, result: EvaluationResult):
    ret = _custom_rule(data, setting, static_game_data, result)
    return ret



def _custom_rule(data: EssenceData, setting, static_game_data, result: EvaluationResult):
    global StaticGameData
    global Settings
    if not STAT_ID_TO_NAME:
        for stat_id, d in static_game_data._stats.items():
            STAT_ID_TO_NAME[stat_id] = d.name
            STAT_NAME_TO_ID[d.name] = stat_id
        StaticGameData = static_game_data
        Settings = setting
        if not MODE_SCAN:
            FourCollections.instance.load_from_last()
            FiveCollections.instance.load_from_last()

    # EssenceStat.json

    stats_attribute = {}
    stats_secondary = {}
    stats_skill = {}
    _type_to_stats_map = {
        StatType.ATTRIBUTE: stats_attribute,
        StatType.SECONDARY: stats_secondary,
        StatType.SKILL: stats_skill,
    }

    for stat_id, level in zip(data.stats, data.levels, strict=True):
        if stat_id is not None and level is not None:
            stat: EssenceStatV2 = static_game_data.get_stat(stat_id)
            stats_map = _type_to_stats_map[stat.type]
            stats_map[stat.stat_id] = (stat, level)

    is_complete = (
        len(stats_attribute) > 0 and len(stats_secondary) > 0 and len(stats_skill) > 0
    )

    def get_highest_stat_level(stats):
        return max(t[1] for t in stats.values()) if stats else 0

    highest_attribute_level = get_highest_stat_level(stats_attribute)
    highest_secondary_level = get_highest_stat_level(stats_secondary)
    highest_skill_level = get_highest_stat_level(stats_skill)
    highest_level = max(data.levels) if data.levels else 0
    sumlv = highest_attribute_level + highest_secondary_level + highest_skill_level

    rare4_log_file and rare4_log_file.get()  # keep open
    rare5_log_file and rare5_log_file.get()  # keep open

    if data.rarity == RarityLabel.FIVE:  # 金的
        action_target = ActionTarget.DEFAULT
        ess_useful_info = {}
        if not is_complete:  # 不是标准组合
            if KEEP_RARE5_SKILL3:
                if highest_skill_level == 3:
                    modify_result(
                        result,
                        EssenceQuality.TREASURE,
                        f"非标准3词条组合，有LV3技能，视为<green><bold><underline>宝藏</></></>", 
                    )
                    return result
            # 只要没有4级词条 都视为狗粮
            if highest_level < 4:
                modify_result(
                    result,
                    EssenceQuality.TRASH,
                    f"非标准3词条组合，且最高词条等级{highest_level}<4，视为<red><bold><underline>养成材料</></></>", 
                    ActionTarget.ABANDON
                )
                rare5_log_file and rare5_log_file.get().write(f"* <font color=\"red\">~~skip trash: {get_essence_string(data)}~~</font>\n")
                return result
            main_attr_level_4 = [stat_id for stat_id, lv in stats_attribute.items() if lv[1] >= 4]
            secondary_attr_level_4 = [stat_id for stat_id, lv in stats_secondary.items() if lv[1] >= 4]
            attr_level_4 = main_attr_level_4 + secondary_attr_level_4
            skill_level_3 = [stat_id for stat_id, lv in stats_skill.items() if lv[1] >= 3]
            # 有4级属性和3级技能  可能有用
            if skill_level_3 and attr_level_4:
                ess_useful_info["lv4_attr_lv3_skill"] = [attr_level_4, skill_level_3]
            # 4级属性词条
            useful_secondary_level4 = [useful_secondary for useful_secondary in USEFUL_SECONDARY if (useful_secondary in stats_secondary and stats_secondary[useful_secondary][1] >= 4)]
            if useful_secondary_level4:
                ess_useful_info["useful_secondary_lv4"] = useful_secondary_level4
            
            if MODE_SCAN:
                if ess_useful_info:
                    obj = FiveCollections.instance.add_useful(data, ess_useful_info, _type_to_stats_map, static_game_data)
                    rare5_log_file.get().write(f"* <font color=\"green\">add useful: {obj}</font>\n")
                else:
                    rare5_log_file.get().write(f"* <font color=\"red\">~~skip trash: {get_essence_string(data)}~~</font>\n")

            ess_quality: EssenceQuality = EssenceQuality.TRASH
            ess_log: str = ""
            # 有4级属性和3级技能  可能有用
            if skill_level_3:
                ess_quality = EssenceQuality.TREASURE
                ess_log = f"非标准3词条组合，但有<green><bold><underline>3级技能词条和4级属性词条</></></>，视为辅助<green><bold><underline>宝藏</></></>",
            elif useful_secondary_level4:
                useful_names = [stats_secondary[useful_secondary][0].name for useful_secondary in useful_secondary_level4]
                useful_names = ",".join(useful_names)
                ess_quality = EssenceQuality.TREASURE
                ess_log = f"非标准3词条组合，但有<green><bold><underline>4级辅助属性词条[{useful_names}]</></></>，视为辅助<green><bold><underline>宝藏</></></>",
            else:
                ess_quality = EssenceQuality.TRASH
                ess_log = "非标准3词条组合，有4级词条但无用，视为<red><bold><underline>养成材料</></></>"
                action_target = ActionTarget.ABANDON

            if MODE_SCAN or ess_quality != EssenceQuality.TREASURE:
                modify_result(result, ess_quality, ess_log, action_target)
                return result

            is_trash = FiveCollections.instance.pop_trash_if_it_is(data)
            if is_trash:
                ess_quality = EssenceQuality.TRASH
                ess_log = f"有一定价值，但是<m><b>重复</></>，视为<red><bold><underline>养成材料</></></>"
                action_target = ActionTarget.NONE  # 不锁也不废弃  不优先作为狗粮使用
            modify_result(result, ess_quality, ess_log, action_target)
            return result
        # 标准组合
        # 有匹配武器
        non_trash_weapon_ids = set(result.matched_weapons) - set(
            setting.trash_weapon_ids
        )

        ess_useful_info["complete"] = [bool(non_trash_weapon_ids), list(data.stats)]
        if MODE_SCAN:
            obj = FiveCollections.instance.add_useful(data, ess_useful_info, _type_to_stats_map, static_game_data)
            rare5_log_file.get().write(f"* <font color=\"green\">add useful: {obj}</font>\n")

        ess_quality: EssenceQuality = EssenceQuality.TRASH
        ess_log: str = ""
        if non_trash_weapon_ids:
            ess_quality = EssenceQuality.TREASURE
            ess_log = "有匹配武器"
        # 无匹配
        elif highest_skill_level >= 2:
            ess_quality = EssenceQuality.TREASURE
            ess_log = f"无匹配武器，但是有<green><bold><underline>{highest_skill_level}级技能词条</></></>，可能有用，视为<green><bold><underline>宝藏</></></>~"
        elif highest_attribute_level >= 4 or highest_secondary_level >= 4:
            ess_quality = EssenceQuality.TREASURE
            ess_log = "无匹配武器，但是有<green><bold><underline>4级属性词条</></></>，可能有用，视为<green><bold><underline>宝藏</></></>~"
        elif highest_attribute_level + highest_secondary_level >= 3:  # TODO 改高
            ess_quality = EssenceQuality.TREASURE
            ess_log = f"无匹配武器，但是<green><bold><underline>属性词条总计达到{highest_attribute_level + highest_secondary_level}级</></></>，可能有用，视为<green><bold><underline>宝藏</></></>~"
        else:
            ess_quality = EssenceQuality.TRASH
            ess_log = "词条等级太低了，视为<red><bold><underline>养成材料</></></>"
            action_target = ActionTarget.NONE  # 不锁也不废弃 作为后备狗粮 不优先使用
        
        if MODE_SCAN:
            modify_result(result, ess_quality, ess_log, action_target)
            return result
        is_trash = FiveCollections.instance.pop_trash_if_it_is(data)
        if is_trash:
            ess_quality = EssenceQuality.TRASH
            ess_log = f"标准3词条组合，但是<m><b>重复</></>，视为<red><bold><underline>养成材料</></></>"
            action_target = ActionTarget.ABANDON  # 重复的 直接废弃
        modify_result(result, ess_quality, ess_log, action_target)
        return result
    elif data.rarity == RarityLabel.FOUR:  # 紫的
        # 紫色基质给辅助用就不考虑标准3词条组合了  只考虑词条等级
        skill_level_3 = [stat_id for stat_id, lv in stats_skill.items() if lv[1] >= 3]
        # 3级辅助属性词条？
        useful_secondary_level3 = [useful_secondary for useful_secondary in USEFUL_SECONDARY if (useful_secondary in stats_secondary and stats_secondary[useful_secondary][1] >= 3)]
        is_attr_level_high = highest_attribute_level + highest_secondary_level >= 6
        is_total_level_high = sumlv >= 7

        ess_useful_info = {
            "skill_level_3": skill_level_3,
            "useful_secondary_level3": useful_secondary_level3,
            "is_attr_level_high": is_attr_level_high,
            "is_total_level_high": is_total_level_high,
        }
        ess_useful_info = {k: v for k, v in ess_useful_info.items() if v}
        if MODE_SCAN:
            if ess_useful_info:
                obj = FourCollections.instance.add_useful(data, ess_useful_info, _type_to_stats_map, static_game_data)
                rare4_log_file.get().write(f"* <font color=\"green\">add useful: {obj}</font>\n")
            else:
                rare4_log_file.get().write(f"* <font color=\"red\">~~skip trash: {get_essence_string(data)}~~</font>\n")

        ess_quality: EssenceQuality = EssenceQuality.TRASH
        ess_log: str = ""
        if skill_level_3:
            skill_names = [stats_skill[s][0].name for s in skill_level_3]
            skill_names = ",".join(skill_names)
            ess_quality = EssenceQuality.TREASURE
            ess_log = f"紫色，但是有<green><bold><underline>3级技能词条[{skill_names}]</></></>，视为辅助<green><bold><underline>宝藏</></></>~"
        elif useful_secondary_level3:
            useful_names = [stats_secondary[useful_secondary][0].name for useful_secondary in useful_secondary_level3]
            useful_names = ",".join(useful_names)
            ess_quality = EssenceQuality.TREASURE
            ess_log = f"紫色，但有<green><bold><underline>3级辅助属性词条[{useful_names}]</></></>，视为辅助<green><bold><underline>宝藏</></></>"
        elif is_attr_level_high:
            ess_quality = EssenceQuality.TREASURE
            ess_log = "紫色，但是<green><bold><underline>属性词条等级总和达到6级</></></>，视为辅助<green><bold><underline>宝藏</></></>~"
        elif is_total_level_high:
            ess_quality = EssenceQuality.TREASURE
            ess_log = f"紫色，但是<green><bold><underline>等级总和达到{sumlv}级</></></>，视为辅助<green><bold><underline>宝藏</></></>~"
        else:
            ess_quality = EssenceQuality.TRASH
            ess_log = "紫色，词条等级也低，拿去回收调度券吧"
        if MODE_SCAN:
            modify_result(result, ess_quality, ess_log)
            return result
        
        if ess_quality == EssenceQuality.TREASURE:
            is_trash = FourCollections.instance.pop_trash_if_it_is(data)
            if is_trash:
                ess_quality = EssenceQuality.TRASH
                ess_log = f"紫色，有一定价值，但是<m><b>重复</></>，视为<red><bold><underline>养成材料</></></>"
        modify_result(result, ess_quality, ess_log)
        return result
    else:
        modify_result(result, EssenceQuality.TRASH, "蓝色基质，路边")
        return result
    return result



from endfield_essence_recognizer.core.path import get_root_dir
from endfield_essence_recognizer.core.scanner.models import (
    EssenceData,
    EvaluationResult,
)
from endfield_essence_recognizer.game_data.static_game_data import StaticGameData
from endfield_essence_recognizer.schemas.user_setting import (
    UserSetting,
)
from endfield_essence_recognizer.utils.log import logger


class CustomRule:
    def __init__(self):
        self.last_code = ""
        self.func = None

    def refresh_code(self):
        custom_rule_path = get_root_dir() / "custom_rule.py"
        if not custom_rule_path.exists() or not custom_rule_path.is_file():
            return
        rule_string = custom_rule_path.read_text("utf-8", errors="ignore")
        if rule_string == self.last_code:
            return
        self.last_code = rule_string
        local_context = {}
        try:
            exec(rule_string, local_context)
        except Exception as e:
            logger.warning(f"自定义规则加载出错 {e}")
            self.func = None
            return
        if "custom_rule" not in local_context:
            logger.warning("custom_rule文件中未定义custom_rule函数")
            self.func = None
            return
        self.func = local_context["custom_rule"]
        if not callable(self.func):
            logger.warning("custom_rule文件中的custom_rule不是一个可调用对象")
            self.func = None
            return
        logger.info("自定义规则加载完成")

    def apply(
        self,
        data: EssenceData,
        setting: UserSetting,
        static_game_data: StaticGameData,
        result: EvaluationResult,
    ):
        if not self.func:
            return result
        try:
            result = self.func(data, setting, static_game_data, result)
        except Exception as e:
            logger.warning(f"自定义规则执行出错，采用原始结果: {e}")
        return result


GlobalCustomRuleObject = CustomRule()

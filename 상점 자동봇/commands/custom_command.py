"""
커스텀 명령어 처리 모듈
Google Sheets의 '커스텀' 워크시트에서 명령어와 문구를 읽어 처리합니다.
15분 캐시를 지원하며, 명령어 매칭 시 띄어쓰기와 대소문자를 무시합니다.
"""

import os
import sys
import re
import random
import time
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta

# 경로 설정 (VM 환경 대응)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from utils.sheets_operations import get_sheets_manager
    from utils.cache_manager import bot_cache
    from utils.logging_config import logger
    from utils.korean_utils import format_korean
    from config.settings import config
except ImportError:
    # VM 환경에서 임포트 실패 시 폴백
    import logging
    logger = logging.getLogger('custom_command')
    
    class FallbackConfig:
        def get_worksheet_name(self, name):
            return name
    config = FallbackConfig()


class CustomCommandManager:
    """커스텀 명령어 관리자 클래스"""
    
    def __init__(self):
        """커스텀 명령어 관리자 초기화"""
        self.sheets_manager = None
        self._cache_key = "custom_commands"
        self._cache_expire_key = "custom_commands_expire"
        self._cache_duration = 15 * 60  # 15분 (초 단위)
        
        # 다이스 제한 설정
        self.max_dice_count = 20
        self.max_dice_sides = 1000
        
        try:
            self.sheets_manager = get_sheets_manager()
            logger.info("커스텀 명령어 관리자 초기화 완료")
        except Exception as e:
            logger.error(f"커스텀 명령어 관리자 초기화 실패: {e}")
    
    def _normalize_command(self, command: str) -> str:
        """
        명령어 정규화
        - 대소문자를 소문자로 통일
        - 띄어쓰기 제거
        - 앞뒤 공백 제거
        
        Args:
            command: 정규화할 명령어
            
        Returns:
            str: 정규화된 명령어
        """
        if not command:
            return ""
        
        # 대소문자를 소문자로 통일하고 띄어쓰기 제거
        normalized = re.sub(r'\s+', '', command.lower().strip())
        
        logger.debug(f"명령어 정규화: '{command}' -> '{normalized}'")
        
        return normalized
    
    def _parse_dice_expression(self, dice_expression: str) -> Dict[str, Any]:
        """
        다이스 표현식 파싱 (기본 + 보정값 지원)
        예: 1d100, 3d6, 2d10+5, 1d20-2
        
        Args:
            dice_expression: 다이스 표현식
            
        Returns:
            Dict: 파싱된 다이스 설정
            
        Raises:
            ValueError: 파싱 실패
        """
        if not dice_expression:
            raise ValueError("다이스 표현식이 비어있습니다.")
        
        # 공백 제거
        dice_expression = dice_expression.strip()
        
        # 보정값 파싱 (+5, -3 등)
        modifier = 0
        if '+' in dice_expression:
            parts = dice_expression.split('+')
            if len(parts) == 2:
                dice_part = parts[0].strip()
                try:
                    modifier = int(parts[1].strip())
                except ValueError:
                    raise ValueError(f"잘못된 보정값: {parts[1]}")
            else:
                dice_part = dice_expression
        elif '-' in dice_expression and not dice_expression.startswith('-'):
            parts = dice_expression.split('-')
            if len(parts) == 2:
                dice_part = parts[0].strip()
                try:
                    modifier = -int(parts[1].strip())
                except ValueError:
                    raise ValueError(f"잘못된 보정값: {parts[1]}")
            else:
                dice_part = dice_expression
        else:
            dice_part = dice_expression
        
        # 기본 다이스 표현식 파싱 (예: 2d6)
        match = re.match(r'(\d+)[dD](\d+)', dice_part.lower())
        if not match:
            raise ValueError(f"잘못된 다이스 표현식: {dice_expression}")
        
        try:
            num_dice = int(match.group(1))
            dice_sides = int(match.group(2))
        except ValueError:
            raise ValueError(f"다이스 숫자 파싱 실패: {dice_expression}")
        
        return {
            'num_dice': num_dice,
            'dice_sides': dice_sides,
            'modifier': modifier,
            'original_expression': dice_expression
        }
    
    def _validate_dice_limits(self, dice_config: Dict[str, Any]) -> None:
        """
        다이스 제한 검증
        
        Args:
            dice_config: 다이스 설정
            
        Raises:
            ValueError: 제한 초과
        """
        num_dice = dice_config['num_dice']
        dice_sides = dice_config['dice_sides']
        
        if num_dice < 1:
            raise ValueError("주사위 개수는 1개 이상이어야 합니다.")
        
        if num_dice > self.max_dice_count:
            raise ValueError(f"주사위 개수는 최대 {self.max_dice_count}개까지 가능합니다.")
        
        if dice_sides < 2:
            raise ValueError("주사위 면수는 2면 이상이어야 합니다.")
        
        if dice_sides > self.max_dice_sides:
            raise ValueError(f"주사위 면수는 최대 {self.max_dice_sides}면까지 가능합니다.")
    
    def _roll_dice(self, num_dice: int, dice_sides: int) -> List[int]:
        """
        주사위 굴리기
        
        Args:
            num_dice: 주사위 개수
            dice_sides: 주사위 면수
            
        Returns:
            List[int]: 각 주사위 결과
        """
        rolls = []
        for _ in range(num_dice):
            roll = random.randint(1, dice_sides)
            rolls.append(roll)
        
        return rolls
    
    def _calculate_dice_result(self, dice_config: Dict[str, Any]) -> Tuple[List[int], int]:
        """
        다이스 결과 계산
        
        Args:
            dice_config: 다이스 설정
            
        Returns:
            Tuple[List[int], int]: (개별 결과, 최종 결과)
        """
        rolls = self._roll_dice(dice_config['num_dice'], dice_config['dice_sides'])
        modifier = dice_config.get('modifier', 0)
        final_result = sum(rolls) + modifier
        
        return rolls, final_result
    
    def _process_dice_in_text(self, text: str) -> str:
        """
        텍스트에서 다이스 표기법을 실제 결과로 치환 (프리미엄 기능 +5000원)
        예: "능력치는 힘: {3d6}점, 민첩: {2d10+5}점입니다" 
        -> "능력치는 힘: 14점, 민첩: 17점입니다"
        
        프리미엄 기능이 비활성화된 경우 다이스 표기법을 그대로 유지합니다.
        
        Args:
            text: 처리할 텍스트
            
        Returns:
            str: 다이스가 치환된 텍스트 (프리미엄 활성화 시) 또는 원본 텍스트
        """
        if not text:
            return text
        
        # 프리미엄 기능 활성화 여부 확인
        if not config.PREMIUM_CUSTOMC_ENABLED:
            logger.debug("프리미엄 다이스 기능이 비활성화되어 있음. 다이스 표기법을 그대로 유지합니다.")
            return text
        
        # {다이스표현식} 패턴 찾기
        dice_pattern = re.compile(r'\{(\d+[dD]\d+(?:[+\-]\d+)?)\}')
        
        def replace_dice(match):
            dice_expr = match.group(1)
            try:
                # 다이스 표현식 파싱 및 계산
                dice_config = self._parse_dice_expression(dice_expr)
                self._validate_dice_limits(dice_config)
                
                rolls, final_result = self._calculate_dice_result(dice_config)
                
                # 로그 기록
                logger.debug(f"프리미엄 다이스 치환: {dice_expr} -> {rolls} = {final_result}")
                
                return str(final_result)
                
            except Exception as e:
                logger.warning(f"프리미엄 다이스 처리 실패 ({dice_expr}): {e}")
                # 실패 시 원본 그대로 반환
                return match.group(0)
        
        result = dice_pattern.sub(replace_dice, text)
        return result
    
    def _process_korean_substitutions(self, text: str, user_name: str) -> str:
        """
        한국어 치환 처리 ({시전자} 및 조사 처리) - 프리미엄 기능 (+5000원)
        
        프리미엄 기능이 비활성화된 경우 모든 괄호 표기법을 그대로 유지합니다.
        
        Args:
            text: 처리할 텍스트
            user_name: 사용자 이름
            
        Returns:
            str: 한국어 치환이 완료된 텍스트 (프리미엄 활성화 시) 또는 원본 텍스트
        """
        if not text:
            return text
        
        # 프리미엄 기능 활성화 여부 확인
        if not config.PREMIUM_CUSTOMC_ENABLED:
            logger.debug("프리미엄 기능이 비활성화되어 있음. 모든 괄호 표기법을 그대로 유지합니다.")
            return text
        
        # 먼저 {시전자}를 실제 사용자 이름으로 치환
        processed_text = text.replace('{시전자}', user_name)
        
        # 한국어 조사 처리
        try:
            # format_korean 함수를 사용하여 조사 자동 처리
            processed_text = format_korean(processed_text, 시전자=user_name)
            
            logger.debug(f"프리미엄 한국어 치환: '{text}' -> '{processed_text}'")
            
        except Exception as e:
            logger.warning(f"프리미엄 한국어 조사 처리 실패: {e}")
            # 실패 시 최소한 {시전자}만 치환된 상태로 반환
        
        return processed_text
    
    def _process_all_substitutions(self, text: str, user_name: str) -> str:
        """
        모든 치환 처리 (다이스 + 한국어) - 프리미엄 기능 (+5000원)
        
        프리미엄 기능이 비활성화된 경우 모든 괄호 표기법을 원본 그대로 유지합니다.
        
        Args:
            text: 처리할 텍스트
            user_name: 사용자 이름
            
        Returns:
            str: 모든 치환이 완료된 텍스트 (프리미엄 활성화 시) 또는 원본 텍스트
        """
        if not text:
            return text
        
        # 프리미엄 기능 비활성화 시 원본 그대로 반환
        if not config.PREMIUM_CUSTOMC_ENABLED:
            logger.debug(f"프리미엄 기능 비활성화: 원본 텍스트 그대로 반환 - '{text}'")
            return text
        
        # 프리미엄 기능 활성화 시 모든 치환 처리
        # 1. 한국어 치환 처리 ({시전자} 및 조사)
        processed_text = self._process_korean_substitutions(text, user_name)
        
        # 2. 다이스 치환 처리
        processed_text = self._process_dice_in_text(processed_text)
        
        logger.debug(f"프리미엄 모든 치환 완료: '{text}' -> '{processed_text}'")
        
        return processed_text
    
    def _is_cache_valid(self) -> bool:
        """
        캐시가 유효한지 확인 (15분 기준)
        
        Returns:
            bool: 캐시 유효성 여부
        """
        expire_time = bot_cache.general_cache.get(self._cache_expire_key)
        if expire_time is None:
            return False
        
        current_time = time.time()
        return current_time < expire_time
    
    def _load_custom_commands_from_sheet(self) -> Dict[str, List[str]]:
        """
        Google Sheets에서 커스텀 명령어 데이터를 로드
        
        Returns:
            Dict[str, List[str]]: {정규화된_명령어: [문구들]} 형태의 딕셔너리
        """
        commands = {}
        
        if not self.sheets_manager:
            logger.warning("Sheets manager가 초기화되지 않았습니다")
            return commands
        
        try:
            # 커스텀 워크시트에서 데이터 가져오기
            custom_data = self.sheets_manager.get_worksheet_data(
                config.get_worksheet_name('CUSTOM') if hasattr(config, 'get_worksheet_name') else '커스텀'
            )
            
            if not custom_data:
                logger.info("커스텀 워크시트에 데이터가 없습니다")
                return commands
            
            # 데이터 처리
            logger.debug(f"커스텀 시트 데이터 처리 시작: {len(custom_data)}개 행")
            
            for i, row in enumerate(custom_data):
                if not isinstance(row, dict):
                    logger.debug(f"행 {i}: dict가 아닌 타입 스킵 - {type(row)}")
                    continue
                
                command = str(row.get('명령어', '')).strip()
                phrase = str(row.get('문구', '')).strip()
                
                logger.debug(f"행 {i}: 원본 데이터 - 명령어='{command}', 문구='{phrase[:50]}...'")
                
                if not command or not phrase:
                    logger.debug(f"행 {i}: 빈 데이터로 인한 스킵 - 명령어='{command}', 문구='{phrase}'")
                    continue
                
                # 명령어 정규화
                normalized_command = self._normalize_command(command)
                
                if normalized_command:
                    if normalized_command not in commands:
                        commands[normalized_command] = []
                    commands[normalized_command].append(phrase)
                    logger.debug(f"커스텀 명령어 추가: 원본='{command}', 정규화='{normalized_command}', 문구='{phrase[:50]}...'")
                else:
                    logger.warning(f"빈 정규화 결과로 인한 명령어 스킵: '{command}'")
            
            logger.info(f"커스텀 명령어 로드 완료: {len(commands)}개 명령어, "
                       f"{sum(len(phrases) for phrases in commands.values())}개 문구")
            
        except Exception as e:
            logger.error(f"커스텀 명령어 로드 실패: {e}")
        
        return commands
    
    def _get_custom_commands(self) -> Dict[str, List[str]]:
        """
        커스텀 명령어 딕셔너리 조회 (캐시 우선)
        
        Returns:
            Dict[str, List[str]]: 커스텀 명령어 딕셔너리
        """
        # 캐시 유효성 확인
        if self._is_cache_valid():
            cached_commands = bot_cache.general_cache.get(self._cache_key)
            if cached_commands is not None:
                logger.debug("캐시에서 커스텀 명령어 데이터 로드")
                return cached_commands
        
        # 캐시가 없거나 만료된 경우 시트에서 로드
        logger.debug("시트에서 커스텀 명령어 데이터 로드")
        commands = self._load_custom_commands_from_sheet()
        
        # 캐시에 저장 (15분 TTL)
        current_time = time.time()
        expire_time = current_time + self._cache_duration
        
        bot_cache.general_cache.set(self._cache_key, commands)
        bot_cache.general_cache.set(self._cache_expire_key, expire_time)
        
        logger.debug(f"커스텀 명령어 데이터 캐시 저장, 만료 시간: {datetime.fromtimestamp(expire_time)}")
        
        return commands
    
    def find_matching_command(self, input_command: str) -> Optional[str]:
        """
        입력 명령어와 일치하는 커스텀 명령어 찾기
        
        Args:
            input_command: 사용자가 입력한 명령어
            
        Returns:
            Optional[str]: 일치하는 명령어 (정규화된 형태) 또는 None
        """
        if not input_command:
            return None
        
        # 입력 명령어 정규화
        normalized_input = self._normalize_command(input_command)
        if not normalized_input:
            return None
        
        # 커스텀 명령어 목록 가져오기
        commands = self._get_custom_commands()
        
        logger.debug(f"명령어 매칭 시도: 입력='{input_command}', 정규화='{normalized_input}'")
        logger.debug(f"사용 가능한 명령어 목록: {list(commands.keys())}")
        
        # 정확히 일치하는 명령어 찾기
        if normalized_input in commands:
            logger.debug(f"명령어 매칭 성공: '{normalized_input}'")
            return normalized_input
        
        logger.debug(f"명령어 매칭 실패: '{normalized_input}' not found in {list(commands.keys())}")
        return None
    
    def get_random_phrase(self, command: str, user_name: str = "") -> Optional[str]:
        """
        특정 명령어의 랜덤 문구 반환 (다이스 및 한국어 처리 포함)
        
        Args:
            command: 명령어 (정규화된 형태)
            user_name: 사용자 이름 ({시전자} 치환용)
            
        Returns:
            Optional[str]: 랜덤 문구 또는 None (모든 치환이 완료된 상태)
        """
        commands = self._get_custom_commands()
        
        if command not in commands:
            return None
        
        phrases = commands[command]
        if not phrases:
            return None
        
        # 랜덤 문구 선택
        selected_phrase = random.choice(phrases)
        
        # 모든 치환 처리 (한국어 + 다이스)
        processed_phrase = self._process_all_substitutions(selected_phrase, user_name)
        
        logger.debug(f"커스텀 명령어 '{command}' 실행 (사용자: {user_name}): '{selected_phrase[:50]}...' -> '{processed_phrase[:50]}...'")
        
        return processed_phrase
    
    def execute_custom_command(self, input_command: str, user_name: str = "") -> Optional[str]:
        """
        커스텀 명령어 실행 (한국어 및 다이스 처리 포함)
        
        Args:
            input_command: 사용자가 입력한 명령어
            user_name: 사용자 이름 ({시전자} 치환용)
            
        Returns:
            Optional[str]: 실행 결과 문구 또는 None (일치하는 명령어가 없는 경우)
        """
        logger.debug(f"커스텀 명령어 실행 요청: '{input_command}' (사용자: {user_name})")
        
        # 매칭되는 명령어 찾기
        matching_command = self.find_matching_command(input_command)
        
        if not matching_command:
            logger.debug(f"커스텀 명령어 실행 실패: '{input_command}' - 매칭되는 명령어 없음")
            return None
        
        # 랜덤 문구 반환 (사용자 이름 포함)
        result = self.get_random_phrase(matching_command, user_name)
        logger.debug(f"커스텀 명령어 실행 완료: '{input_command}' -> '{result[:100] if result else None}...'")
        return result
    
    def get_available_commands(self) -> List[str]:
        """
        사용 가능한 커스텀 명령어 목록 반환
        
        Returns:
            List[str]: 커스텀 명령어 목록 (정규화된 형태)
        """
        commands = self._get_custom_commands()
        return list(commands.keys())
    
    def get_command_info(self, command: str) -> Optional[Dict[str, any]]:
        """
        특정 명령어의 상세 정보 반환
        
        Args:
            command: 조회할 명령어
            
        Returns:
            Optional[Dict]: 명령어 정보 (문구 개수, 문구 목록 등) 또는 None
        """
        matching_command = self.find_matching_command(command)
        if not matching_command:
            return None
        
        commands = self._get_custom_commands()
        phrases = commands.get(matching_command, [])
        
        return {
            'command': matching_command,
            'phrase_count': len(phrases),
            'phrases': phrases
        }
    
    def invalidate_cache(self) -> bool:
        """
        캐시 무효화 (다음 조회 시 시트에서 다시 로드)
        
        Returns:
            bool: 무효화 성공 여부
        """
        try:
            bot_cache.general_cache.delete(self._cache_key)
            bot_cache.general_cache.delete(self._cache_expire_key)
            logger.info("커스텀 명령어 캐시 무효화 완료")
            return True
        except Exception as e:
            logger.error(f"커스텀 명령어 캐시 무효화 실패: {e}")
            return False


# 전역 인스턴스
_global_custom_command_manager = None


def get_custom_command_manager() -> CustomCommandManager:
    """전역 CustomCommandManager 인스턴스 반환"""
    global _global_custom_command_manager
    if _global_custom_command_manager is None:
        _global_custom_command_manager = CustomCommandManager()
    return _global_custom_command_manager


# 편의 함수들

def execute_custom_command(input_command: str, user_name: str = "") -> Optional[str]:
    """
    커스텀 명령어 실행 편의 함수
    
    Args:
        input_command: 사용자가 입력한 명령어
        user_name: 사용자 이름 ({시전자} 치환용)
        
    Returns:
        Optional[str]: 실행 결과 문구 또는 None
    """
    manager = get_custom_command_manager()
    return manager.execute_custom_command(input_command, user_name)


def is_custom_command(input_command: str) -> bool:
    """
    입력이 커스텀 명령어인지 확인
    
    Args:
        input_command: 확인할 명령어
        
    Returns:
        bool: 커스텀 명령어 여부
    """
    manager = get_custom_command_manager()
    return manager.find_matching_command(input_command) is not None


def get_custom_command_list() -> List[str]:
    """
    사용 가능한 커스텀 명령어 목록 반환
    
    Returns:
        List[str]: 커스텀 명령어 목록
    """
    manager = get_custom_command_manager()
    return manager.get_available_commands()


def invalidate_custom_command_cache() -> bool:
    """
    커스텀 명령어 캐시 무효화
    
    Returns:
        bool: 무효화 성공 여부
    """
    manager = get_custom_command_manager()
    return manager.invalidate_cache()


def has_dice_expressions(text: str) -> bool:
    """
    텍스트에 다이스 표기법이 포함되어 있는지 확인
    
    Args:
        text: 확인할 텍스트
        
    Returns:
        bool: 다이스 표기법 포함 여부
    """
    if not text:
        return False
    
    dice_pattern = re.compile(r'\{(\d+[dD]\d+(?:[+\-]\d+)?)\}')
    return bool(dice_pattern.search(text))


def process_dice_in_custom_text(text: str) -> str:
    """
    커스텀 텍스트의 다이스 표기법 처리 (독립 함수)
    
    Args:
        text: 처리할 텍스트
        
    Returns:
        str: 다이스가 치환된 텍스트
    """
    manager = get_custom_command_manager()
    return manager._process_dice_in_text(text)


def process_korean_in_custom_text(text: str, user_name: str) -> str:
    """
    커스텀 텍스트의 한국어 치환 처리 (독립 함수)
    
    Args:
        text: 처리할 텍스트
        user_name: 사용자 이름
        
    Returns:
        str: 한국어 치환이 완료된 텍스트
    """
    manager = get_custom_command_manager()
    return manager._process_korean_substitutions(text, user_name)


def process_all_custom_substitutions(text: str, user_name: str) -> str:
    """
    커스텀 텍스트의 모든 치환 처리 (다이스 + 한국어, 독립 함수)
    
    Args:
        text: 처리할 텍스트
        user_name: 사용자 이름
        
    Returns:
        str: 모든 치환이 완료된 텍스트
    """
    manager = get_custom_command_manager()
    return manager._process_all_substitutions(text, user_name)


def has_korean_substitutions(text: str) -> bool:
    """
    텍스트에 한국어 치환 요소가 포함되어 있는지 확인
    
    Args:
        text: 확인할 텍스트
        
    Returns:
        bool: 한국어 치환 요소 포함 여부
    """
    if not text:
        return False
    
    # {시전자} 또는 조사 패턴 확인
    korean_patterns = [
        r'\{시전자\}',
        r'\{은는\}',
        r'\{이가\}',
        r'\{을를\}',
        r'\{과와\}',
        r'\{아야\}',
        r'\{으로로\}'
    ]
    
    for pattern in korean_patterns:
        if re.search(pattern, text):
            return True
    
    return False


# 사용 예시 (테스트용)
if __name__ == "__main__":
    # 테스트 코드
    manager = get_custom_command_manager()
    
    print("=== 커스텀 명령어 + 다이스 + 한국어 테스트 ===")
    
    # 기본 커스텀 명령어 테스트 (사용자 이름 포함)
    test_user_names = ["철수", "영희", "민수", "수연"]
    test_commands = ["기숙사", "패션점수", "능력치", "인사"]
    
    print("\n[커스텀 명령어 테스트]")
    for cmd in test_commands[:2]:  # 처음 2개만 테스트
        for user in test_user_names[:2]:  # 처음 2명만 테스트
            result = manager.execute_custom_command(cmd, user)
            if result:
                print(f"'{cmd}' (사용자: {user}) -> '{result}'")
            else:
                print(f"'{cmd}' -> 매칭되는 명령어 없음")
    
    print(f"\n사용 가능한 명령어: {manager.get_available_commands()}")
    
    # 다이스 처리 테스트
    print("\n=== 다이스 처리 테스트 ===")
    dice_test_texts = [
        "오늘의 패션 점수는 {1d100}점입니다.",
        "능력치는 민첩: {3d6} / 힘: {3d10+5} / 운: {1d100} 입니다.",
        "피해량: {2d6+3}",
        "체력: {4d6} HP"
    ]
    
    for text in dice_test_texts:
        processed = manager._process_dice_in_text(text)
        print(f"'{text}' -> '{processed}'")
    
    # 한국어 치환 테스트
    print("\n=== 한국어 치환 테스트 ===")
    korean_test_texts = [
        "{시전자}{은는} 마법을 시전했습니다.",
        "{시전자}{이가} {1d100}점의 피해를 입혔습니다.",
        "{시전자}{을를} 치료했습니다.",
        "{시전자}{과와} 함께 모험을 떠났습니다.",
        "{시전자}{아야}! 안녕하세요!"
    ]
    
    for text in korean_test_texts:
        for user in ["철수", "영희"]:
            processed = manager._process_all_substitutions(text, user)
            print(f"'{text}' (사용자: {user}) -> '{processed}'")
    
    # 포함 여부 확인 테스트
    print("\n=== 포함 여부 테스트 ===")
    all_test_texts = dice_test_texts + korean_test_texts
    for text in all_test_texts:
        has_dice = has_dice_expressions(text)
        has_korean = has_korean_substitutions(text)
        print(f"'{text}' -> 다이스: {has_dice}, 한국어: {has_korean}")
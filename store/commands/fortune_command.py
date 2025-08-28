"""
운세 명령어 구현 - 간단한 버전
Google Sheets에서 운세 문구를 가져와 하루 한 번 제공하는 명령어입니다.
"""

import os
import sys
import random
from datetime import datetime, timezone, timedelta
from typing import List, Optional

# 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    from commands.base_command import BaseCommand, CommandContext, CommandResponse
    from commands.registry import register_command
    from utils.logging_config import logger
    from utils.cache_manager import bot_cache
    from config.settings import config
except ImportError:
    import logging
    logger = logging.getLogger('fortune_command')
    
    class BaseCommand:
        def __init__(self, sheets_manager=None, api=None, **kwargs):
            self.sheets_manager = sheets_manager
    
    class CommandContext:
        def __init__(self):
            self.keywords = []
            self.user_id = 'test_user'
    
    class CommandResponse:
        @classmethod
        def create_success(cls, message, data=None):
            return cls()
        
        @classmethod
        def create_error(cls, message, error=None):
            return cls()
    
    class MockCache:
        def cache_today_fortune(self, user_id, fortune):
            return True
        def get_today_fortune(self, user_id):
            return None
    
    bot_cache = MockCache()


@register_command(
    name="fortune",
    aliases=["운세"],
    description="오늘의 운세",
    category="게임",
    examples=["[운세]"],
    requires_sheets=True,
    requires_api=False
)
class FortuneCommand(BaseCommand):
    """간단한 운세 명령어 클래스"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # KST 타임존
        self.kst = timezone(timedelta(hours=9))
        # 캐싱 설정 로드
        self._cache_enabled = self._get_cache_setting()
    
    def execute(self, context: CommandContext) -> CommandResponse:
        """운세 명령어 실행"""
        try:
            user_id = getattr(context, 'user_id', 'unknown_user')
            
            # 캐싱 사용 여부 확인
            if self._cache_enabled:
                # 오늘의 운세 캐시 확인
                cached_fortune = bot_cache.get_today_fortune(user_id, self.kst)
                if cached_fortune:
                    return CommandResponse.create_success(cached_fortune)
            
            # 시트에서 운세 목록 가져오기 (1시간 캐시 사용)
            fortune_list = self._get_fortune_list()
            if not fortune_list:
                return CommandResponse.create_error("운세를 불러올 수 없습니다.")
            
            # 랜덤 운세 선택
            selected_fortune = random.choice(fortune_list)
            
            # 캐싱 설정에 따라 저장
            if self._cache_enabled:
                bot_cache.cache_today_fortune(user_id, selected_fortune, self.kst)
            
            return CommandResponse.create_success(selected_fortune)
            
        except Exception as e:
            logger.error(f"운세 명령어 오류: {e}")
            return CommandResponse.create_error(f"운세를 가져오는 중 오류가 발생했습니다: {str(e)}")
    
    def _get_fortune_list(self) -> List[str]:
        """시트에서 운세 목록 가져오기 (1시간 캐시)"""
        # 먼저 캐시된 운세 문구 조회
        cached_phrases = bot_cache.get_fortune_phrases()
        if cached_phrases:
            logger.debug(f"캐시된 운세 문구 사용: {len(cached_phrases)}개")
            return cached_phrases
        
        if not self.sheets_manager:
            logger.warning("SheetsManager가 없어서 더미 운세 사용")
            dummy_fortunes = [
                "오늘은 좋은 일이 생길 것입니다.",
                "새로운 기회가 찾아올 것입니다.",
                "주변 사람들과의 관계가 좋아질 것입니다.",
                "건강에 주의하세요.",
                "금전적으로 좋은 소식이 있을 것입니다."
            ]
            # 더미 데이터도 1시간 캐시
            bot_cache.cache_fortune_phrases(dummy_fortunes, ttl_hours=1)
            return dummy_fortunes
        
        try:
            # '운세' 워크시트에서 '문구' 열 가져오기
            worksheet_data = self.sheets_manager.get_worksheet_data('운세')
            if not worksheet_data:
                logger.error("운세 워크시트를 찾을 수 없음")
                return []
            
            # '문구' 열에서 운세 목록 추출
            fortune_list = []
            for row in worksheet_data:
                if '문구' in row and row['문구']:
                    fortune_text = str(row['문구']).strip()
                    if fortune_text:
                        fortune_list.append(fortune_text)
            
            logger.info(f"시트에서 {len(fortune_list)}개의 운세 로드")
            
            # 1시간 동안 캐시
            if fortune_list:
                bot_cache.cache_fortune_phrases(fortune_list, ttl_hours=1)
            
            return fortune_list
            
        except Exception as e:
            logger.error(f"시트에서 운세 로드 실패: {e}")
            return []
    
    def _get_cache_setting(self) -> bool:
        """캐시 설정값 가져오기"""
        try:
            # config에서 설정값 읽기
            cache_enabled = getattr(config, 'FORTUNE_CACHE_ENABLED', True)
            if isinstance(cache_enabled, str):
                return cache_enabled.lower() in ('true', '1', 'yes', 'on')
            return bool(cache_enabled)
        except Exception as e:
            logger.warning(f"캐시 설정 로드 실패, 기본값 사용: {e}")
            return True
    
    def _get_today_key(self) -> str:
        """오늘 날짜 키 생성 (KST 기준)"""
        now = datetime.now(self.kst)
        return now.strftime('%Y-%m-%d')
"""
카드 뽑기 명령어 구현 - 간단한 버전
표준 52장 카드 덱에서 카드를 뽑는 명령어입니다.
"""

import os
import sys
import random
import re
from typing import List, Optional

# 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    from commands.base_command import BaseCommand, CommandContext, CommandResponse
    from commands.registry import register_command
    from utils.logging_config import logger
except ImportError:
    import logging
    logger = logging.getLogger('card_command')
    
    class BaseCommand:
        def __init__(self, sheets_manager=None, api=None, **kwargs):
            pass
    
    class CommandContext:
        def __init__(self):
            self.keywords = []
    
    class CommandResponse:
        @classmethod
        def create_success(cls, message, data=None):
            return cls()
        
        @classmethod
        def create_error(cls, message, error=None):
            return cls()


@register_command(
    name="card",
    aliases=["카드뽑기", "카드 뽑기"],
    description="카드 뽑기",
    category="게임",
    examples=["[카드뽑기/3]", "[카드 뽑기/5장]"],
    requires_sheets=False,
    requires_api=False
)
class CardCommand(BaseCommand):
    """간단한 카드 뽑기 명령어 클래스"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 표준 52장 카드 덱 생성
        self.suits = ['♠', '♥', '♦', '♣']  # 스페이드, 하트, 다이아, 클로버
        self.ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
        self.deck = [f"{suit}{rank}" for suit in self.suits for rank in self.ranks]
    
    def execute(self, context: CommandContext) -> CommandResponse:
        """카드 뽑기 실행"""
        try:
            # 카드 수 추출
            num_cards = self._extract_card_count(context.keywords)
            
            # 제한 검증
            if num_cards > 52:
                return CommandResponse.create_error("최대 52장까지만 뽑을 수 있습니다.")
            if num_cards < 1:
                return CommandResponse.create_error("최소 1장은 뽑아야 합니다.")
            
            # 카드 뽑기
            drawn_cards = random.sample(self.deck, num_cards)
            
            # 결과 메시지 생성
            if len(drawn_cards) == 1:
                message = drawn_cards[0]
            else:
                message = ", ".join(drawn_cards)
            
            return CommandResponse.create_success(message, data=drawn_cards)
            
        except Exception as e:
            logger.error(f"카드 뽑기 오류: {e}")
            return CommandResponse.create_error(str(e), error=e)
    
    def _extract_card_count(self, keywords: List[str]) -> int:
        """키워드에서 카드 수 추출"""
        if not keywords:
            return 1  # 기본값
        
        # [카드뽑기/5] 또는 [카드 뽑기/3장] 형태 처리
        for keyword in keywords:
            # 숫자만 있는 경우 (예: "5")
            if keyword.isdigit():
                return int(keyword)
            
            # 숫자+장 형태 (예: "5장")
            match = re.search(r'(\d+)', keyword)
            if match:
                return int(match.group(1))
        
        return 1  # 기본값
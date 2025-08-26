"""
상점 조회 명령어

상점에서 구매 가능한 아이템 목록을 조회합니다.
[상점] 명령어를 지원합니다.
"""

import os
import sys
import time
from typing import List, Dict, Any, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.base_command import BaseCommand, CommandContext, CommandResponse
from config.settings import config
from utils.sheets_operations import SheetsManager


class StoreCommand(BaseCommand):
    """상점 조회 명령어"""
    
    # 명령어 메타데이터
    command_name = "상점"
    command_description = "상점에서 구매 가능한 아이템 목록을 확인합니다"
    command_category = "상점"
    command_examples = ["[상점]", "[상점 목록]", "[store]"]
    requires_sheets = True
    
    def __init__(self, sheets_manager: SheetsManager = None, **kwargs):
        super().__init__(sheets_manager=sheets_manager, **kwargs)
        
        # 환경변수에서 설정 로드
        self.currency = os.getenv('CURRENCY', '소지금')
        
        # 상점 데이터 캐시 (15분 TTL)
        self._store_cache = None
        self._store_cache_time = 0
        self._store_cache_ttl = 15 * 60  # 15분 (초 단위)
    
    def execute(self, context: CommandContext) -> CommandResponse:
        """상점 조회 실행"""
        try:
            # 명령어 매칭 확인
            if not self._matches_command(context.keywords):
                return CommandResponse.create_error("잘못된 명령어입니다")
            
            # 상점 데이터 조회 (15분 캐시 적용)
            store_items = self._get_store_items()
            
            if store_items is None:
                return CommandResponse.create_error("상점 정보를 조회할 수 없습니다")
            
            if not store_items:
                return CommandResponse.create_error("상점에 판매 중인 아이템이 없습니다")
            
            # 응답 메시지 생성
            message = self._format_store_message(store_items)
            
            return CommandResponse.create_success(message)
            
        except Exception as e:
            return CommandResponse.create_error(
                "상점 조회 중 오류가 발생했습니다",
                error=e
            )
    
    def _matches_command(self, keywords: List[str]) -> bool:
        """명령어 매칭 확인"""
        if not keywords:
            return False
        
        first_keyword = keywords[0].lower()
        
        # 기본 명령어들
        base_commands = ['상점']
        
        # 추가 가능한 명령어들
        additional_commands = ['store', 'shop', '샵', '마트', '매점']
        
        # 상점 목록 등의 확장 명령어
        if len(keywords) >= 2:
            second_keyword = keywords[1].lower()
            if first_keyword in base_commands + additional_commands:
                if second_keyword in ['목록', 'list', '리스트']:
                    return True
        
        all_commands = base_commands + additional_commands
        
        return first_keyword in all_commands
    
    def _get_store_items(self) -> Optional[List[Dict[str, Any]]]:
        """
        상점 아이템 조회 (15분 캐시 적용)
        
        Returns:
            Optional[List[Dict]]: 상점 아이템 목록 또는 None
        """
        current_time = time.time()
        
        # 캐시가 유효한지 확인
        if (self._store_cache is not None and 
            current_time - self._store_cache_time < self._store_cache_ttl):
            return self._store_cache
        
        try:
            # 상점 데이터를 시트에서 조회
            store_data = self.sheets_manager.get_worksheet_data('상점', use_cache=True)
            
            if not store_data:
                return []
            
            # 유효한 상품만 필터링
            valid_items = []
            for row in store_data:
                item_name = str(row.get('아이템명', '')).strip()
                price_str = str(row.get('가격', '')).strip()
                description = str(row.get('설명', '')).strip()
                
                # 필수 필드가 모두 있는 경우만 포함
                if item_name and price_str and description:
                    # 가격 파싱
                    price = self._parse_price(price_str)
                    if price >= 0:  # 가격이 유효한 경우
                        valid_items.append({
                            '아이템명': item_name,
                            '가격': price,
                            '설명': description
                        })
            
            # 캐시 업데이트
            self._store_cache = valid_items
            self._store_cache_time = current_time
            
            return valid_items
            
        except Exception as e:
            # 에러 발생시 캐시 무효화
            self._store_cache = None
            self._store_cache_time = 0
            return None
    
    def _parse_price(self, price_str: str) -> int:
        """
        가격 문자열 파싱
        
        Args:
            price_str: 가격 문자열 (예: "100", "1,000", "100포인트")
            
        Returns:
            int: 파싱된 가격 (실패시 -1)
        """
        if not price_str:
            return -1
        
        # 숫자가 아닌 문자 제거 (쉼표, 화폐 단위 등)
        import re
        numeric_str = re.sub(r'[^\d]', '', price_str)
        
        if not numeric_str:
            return -1
        
        try:
            return int(numeric_str)
        except ValueError:
            return -1
    
    def _format_store_message(self, store_items: List[Dict[str, Any]]) -> str:
        """
        상점 메시지 포맷팅
        
        Args:
            store_items: 상점 아이템 목록
            
        Returns:
            str: 포맷된 메시지
        """
        # 메시지 시작
        message_lines = ["상점에서 구매 가능한 목록입니다."]
        message_lines.append("")  # 빈 줄
        
        # 상품 목록
        for item in store_items:
            item_name = item['아이템명']
            price = item['가격']
            description = item['설명']
            
            # {아이템명} ({가격}{CURRENCY}) : {설명}
            item_line = f"{item_name} ({price:,}{self.currency}) : {description}"
            message_lines.append(item_line)
        
        return "\n".join(message_lines)
    
    def clear_cache(self) -> None:
        """상점 캐시 클리어"""
        self._store_cache = None
        self._store_cache_time = 0
    
    def get_cache_info(self) -> Dict[str, Any]:
        """캐시 정보 반환"""
        current_time = time.time()
        cache_age = current_time - self._store_cache_time if self._store_cache_time > 0 else 0
        cache_remaining = max(0, self._store_cache_ttl - cache_age)
        
        return {
            'cached': self._store_cache is not None,
            'cache_age_seconds': round(cache_age, 1),
            'cache_remaining_seconds': round(cache_remaining, 1),
            'cache_ttl_seconds': self._store_cache_ttl,
            'items_count': len(self._store_cache) if self._store_cache else 0
        }
    
    def validate_context(self, context: CommandContext) -> Optional[str]:
        """컨텍스트 유효성 검증"""
        # 기본 검증
        error = super().validate_context(context)
        if error:
            return error
        
        # 상점 명령어는 추가 키워드가 필요하지 않음
        return None
    
    def cleanup(self) -> None:
        """정리 작업"""
        super().cleanup()
        self.clear_cache()
    
    def get_help_text(self) -> str:
        """도움말 텍스트 반환"""
        return (f"{self.command_description}\n"
                f"사용법: {', '.join(self.command_examples)}\n"
                f"현재 설정된 화폐 단위: {self.currency}\n"
                f"캐시 유지 시간: {self._store_cache_ttl // 60}분")
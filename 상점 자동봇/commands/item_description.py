"""
아이템 설명 조회 명령어

특정 아이템의 설명을 조회합니다.
[설명 아이템명] 형태의 명령어를 지원합니다.
"""

import os
import sys
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.base_command import BaseCommand, CommandContext, CommandResponse
from config.settings import config
from utils.sheets_operations import SheetsManager


class ItemDescriptionCommand(BaseCommand):
    """아이템 설명 조회 명령어"""
    
    # 명령어 메타데이터
    command_name = "설명"
    command_description = "특정 아이템의 설명을 확인합니다"
    command_category = "상점"
    command_examples = ["[설명 가챠]", "[설명 송충이]", "[아이템 가챠]"]
    requires_sheets = True
    
    def __init__(self, sheets_manager: SheetsManager = None, **kwargs):
        super().__init__(sheets_manager=sheets_manager, **kwargs)
        
        # 환경변수에서 설정 로드
        self.currency = os.getenv('CURRENCY', '소지금')
    
    def execute(self, context: CommandContext) -> CommandResponse:
        """아이템 설명 조회 실행"""
        try:
            # 명령어 매칭 확인 및 아이템명 추출
            item_name = self._extract_item_name(context.keywords)
            if not item_name:
                return CommandResponse.create_error(
                    "아이템명을 입력해주세요.\n예: [설명 가챠], [설명 송충이]"
                )
            
            # 아이템 검색
            item_info = self._find_item(item_name)
            
            if item_info is None:
                return CommandResponse.create_error(f"'{item_name}' 아이템을 찾을 수 없습니다")
            
            # 응답 메시지 생성
            message = self._format_item_description(item_info)
            
            return CommandResponse.create_success(message)
            
        except Exception as e:
            return CommandResponse.create_error(
                "아이템 설명 조회 중 오류가 발생했습니다",
                error=e
            )
    
    def _extract_item_name(self, keywords: List[str]) -> Optional[str]:
        """
        키워드에서 아이템명 추출
        
        Args:
            keywords: 명령어 키워드 리스트
            
        Returns:
            Optional[str]: 추출된 아이템명 또는 None
        """
        if not keywords or len(keywords) < 2:
            return None
        
        first_keyword = keywords[0].lower()
        
        # 첫 번째 키워드가 설명 관련 명령어인지 확인
        if first_keyword not in ['설명', '아이템', 'item', 'desc', 'description']:
            return None
        
        # 나머지 키워드들을 아이템명으로 결합
        item_name = ' '.join(keywords[1:]).strip()
        return item_name if item_name else None
    
    def _find_item(self, item_name: str) -> Optional[Dict[str, Any]]:
        """
        아이템 검색 (부분 매칭 지원)
        
        Args:
            item_name: 검색할 아이템명
            
        Returns:
            Optional[Dict]: 찾은 아이템 정보 또는 None
        """
        try:
            # 상점 데이터 조회 (캐시 사용)
            store_data = self.sheets_manager.get_worksheet_data('상점', use_cache=True)
            
            if not store_data:
                return None
            
            # 정확한 매칭 먼저 시도
            for row in store_data:
                row_item_name = str(row.get('아이템명', '')).strip()
                if not row_item_name:
                    continue
                
                # 정확한 매칭
                if row_item_name.lower() == item_name.lower():
                    return self._create_item_info(row)
            
            # 부분 매칭 시도
            best_match = None
            best_similarity = 0.0
            
            for row in store_data:
                row_item_name = str(row.get('아이템명', '')).strip()
                if not row_item_name:
                    continue
                
                # 포함 관계 확인
                if item_name.lower() in row_item_name.lower():
                    similarity = len(item_name) / len(row_item_name)
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = row
                
                # 유사도 계산
                similarity = SequenceMatcher(None, item_name.lower(), row_item_name.lower()).ratio()
                if similarity > 0.6 and similarity > best_similarity:  # 60% 이상 유사도
                    best_similarity = similarity
                    best_match = row
            
            return self._create_item_info(best_match) if best_match else None
            
        except Exception as e:
            return None
    
    def _create_item_info(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        시트 행 데이터를 아이템 정보로 변환
        
        Args:
            row: 시트 행 데이터
            
        Returns:
            Dict: 아이템 정보
        """
        item_name = str(row.get('아이템명', '')).strip()
        price_str = str(row.get('가격', '')).strip()
        description = str(row.get('설명', '')).strip()
        
        # 가격 파싱
        price = self._parse_price(price_str) if price_str else None
        
        return {
            '아이템명': item_name,
            '가격': price,
            '설명': description,
            '가격_원본': price_str
        }
    
    def _parse_price(self, price_str: str) -> Optional[int]:
        """
        가격 문자열 파싱
        
        Args:
            price_str: 가격 문자열
            
        Returns:
            Optional[int]: 파싱된 가격 또는 None
        """
        if not price_str:
            return None
        
        # 숫자가 아닌 문자 제거
        import re
        numeric_str = re.sub(r'[^\d]', '', price_str)
        
        if not numeric_str:
            return None
        
        try:
            return int(numeric_str)
        except ValueError:
            return None
    
    def _format_item_description(self, item_info: Dict[str, Any]) -> str:
        """
        아이템 설명 메시지 포맷팅
        
        Args:
            item_info: 아이템 정보
            
        Returns:
            str: 포맷된 메시지
        """
        item_name = item_info['아이템명']
        price = item_info['가격']
        description = item_info['설명']
        
        # 가격이 있는 경우와 없는 경우를 구분
        if price is not None and price >= 0:
            # {아이템명}({가격}{CURRENCY}) : {설명}
            return f"{item_name}({price:,}{self.currency}) : {description}"
        else:
            # {아이템명} : {설명}
            return f"{item_name} : {description}"
    
    def validate_context(self, context: CommandContext) -> Optional[str]:
        """컨텍스트 유효성 검증"""
        # 기본 검증
        error = super().validate_context(context)
        if error:
            return error
        
        # 최소 2개의 키워드 필요 (명령어 + 아이템명)
        if len(context.keywords) < 2:
            return "아이템명을 입력해주세요"
        
        return None
    
    def get_help_text(self) -> str:
        """도움말 텍스트 반환"""
        return (f"{self.command_description}\n"
                f"사용법: {', '.join(self.command_examples)}\n"
                f"부분 매칭을 지원하므로 아이템명의 일부만 입력해도 됩니다")
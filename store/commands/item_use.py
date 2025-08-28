"""
아이템 사용 명령어

사용자의 소지품에서 아이템을 1개 사용(삭제)합니다.
[사용 아이템명] 형태의 명령어를 지원합니다.
"""

import os
import sys
import json
import ast
from typing import List, Dict, Any, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.base_command import BaseCommand, CommandContext, CommandResponse
from config.settings import config
from utils.sheets_operations import SheetsManager
from utils.korean_utils import get_last_char, has_final_consonant


class ItemUseCommand(BaseCommand):
    """아이템 사용 명령어"""
    
    # 명령어 메타데이터
    command_name = "사용"
    command_description = "소지품에서 아이템을 1개 사용합니다"
    command_category = "인벤토리"
    command_examples = ["[사용 가챠]", "[사용 송충이]", "[사용 별사탕]"]
    requires_sheets = True
    
    def __init__(self, sheets_manager: SheetsManager = None, **kwargs):
        super().__init__(sheets_manager=sheets_manager, **kwargs)
    
    def execute(self, context: CommandContext) -> CommandResponse:
        """아이템 사용 실행"""
        try:
            # 명령어 매칭 확인 및 아이템명 추출
            item_name = self._extract_item_name(context.keywords)
            if not item_name:
                return CommandResponse.create_error(
                    "사용할 아이템명을 입력해주세요.\n예: [사용 가챠], [사용 송충이]"
                )
            
            # 사용자 존재 확인
            if not self.sheets_manager.user_exists(context.user_id):
                return CommandResponse.create_error("등록되지 않은 사용자입니다")
            
            # 사용자 관리 데이터 조회 (캐시 사용 안함)
            user_data = self._get_user_management_data(context.user_id)
            
            if user_data is None:
                return CommandResponse.create_error("사용자 정보를 조회할 수 없습니다")
            
            # 소지품 딕셔너리 파싱
            inventory_data = user_data.get('소지품', {})
            inventory_dict = self._parse_inventory_data(inventory_data)
            
            # 아이템 검색
            found_item = self._find_item_in_inventory(item_name, inventory_dict)
            
            if found_item is None:
                return CommandResponse.create_error(f"'{item_name}' 아이템을 소지하고 있지 않습니다")
            
            actual_item_name, current_count = found_item
            
            if current_count <= 0:
                return CommandResponse.create_error(f"'{actual_item_name}' 아이템이 없습니다")
            
            # 아이템 1개 차감
            new_inventory = self._use_item(inventory_dict, actual_item_name)
            
            # 구글 시트 업데이트
            success = self._update_user_inventory(context.user_id, new_inventory)
            
            if not success:
                return CommandResponse.create_error("아이템 사용 처리에 실패했습니다")
            
            # 응답 메시지 생성
            message = self._format_use_message(actual_item_name)
            
            return CommandResponse.create_success(message)
            
        except Exception as e:
            return CommandResponse.create_error(
                "아이템 사용 중 오류가 발생했습니다",
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
        
        # 첫 번째 키워드가 사용 관련 명령어인지 확인
        if first_keyword not in ['사용', 'use', '사용하기', '먹기', '소모']:
            return None
        
        # 나머지 키워드들을 아이템명으로 결합
        item_name = ' '.join(keywords[1:]).strip()
        return item_name if item_name else None
    
    def _get_user_management_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        사용자 관리 데이터 조회 (실시간, 캐시 사용 안함)
        """
        try:
            management_data = self.sheets_manager.get_worksheet_data('관리', use_cache=False)
            
            if not management_data:
                return None
            
            for row in management_data:
                row_id = str(row.get('아이디', '')).strip()
                if row_id == user_id:
                    return row
            
            return None
            
        except Exception:
            return None
    
    def _parse_inventory_data(self, inventory_data: Any) -> Dict[str, int]:
        """
        소지품 데이터 파싱 (inventory_command.py와 동일한 로직)
        """
        if not inventory_data:
            return {}
        
        # 이미 딕셔너리인 경우
        if isinstance(inventory_data, dict):
            return {str(k): int(v) if str(v).isdigit() else 0 
                    for k, v in inventory_data.items() if k and v}
        
        # 문자열인 경우 JSON/파이썬 딕셔너리로 파싱 시도
        if isinstance(inventory_data, str):
            inventory_str = inventory_data.strip()
            
            if not inventory_str:
                return {}
            
            # JSON 형태로 파싱 시도
            try:
                parsed = json.loads(inventory_str)
                if isinstance(parsed, dict):
                    return {str(k): int(v) if str(v).isdigit() else 0 
                            for k, v in parsed.items() if k and v}
            except json.JSONDecodeError:
                pass
            
            # 파이썬 literal_eval로 파싱 시도
            try:
                parsed = ast.literal_eval(inventory_str)
                if isinstance(parsed, dict):
                    return {str(k): int(v) if str(v).isdigit() else 0 
                            for k, v in parsed.items() if k and v}
            except (ValueError, SyntaxError):
                pass
        
        return {}
    
    def _find_item_in_inventory(self, item_name: str, inventory: Dict[str, int]) -> Optional[tuple]:
        """
        인벤토리에서 아이템 검색 (정확한 매칭 → 부분 매칭)
        
        Returns:
            Optional[tuple]: (실제_아이템명, 개수) 또는 None
        """
        # 정확한 매칭 먼저 시도
        for inv_item_name, count in inventory.items():
            if inv_item_name.lower() == item_name.lower():
                return (inv_item_name, count)
        
        # 부분 매칭 시도
        for inv_item_name, count in inventory.items():
            if item_name.lower() in inv_item_name.lower():
                return (inv_item_name, count)
        
        return None
    
    def _use_item(self, inventory: Dict[str, int], item_name: str) -> Dict[str, int]:
        """
        아이템 1개 사용 (차감)
        
        Args:
            inventory: 현재 인벤토리
            item_name: 사용할 아이템명
            
        Returns:
            Dict: 업데이트된 인벤토리
        """
        new_inventory = inventory.copy()
        
        if item_name in new_inventory:
            current_count = new_inventory[item_name]
            
            if current_count <= 1:
                # 1개 이하면 아이템 키 자체를 삭제
                del new_inventory[item_name]
            else:
                # 1개 차감
                new_inventory[item_name] = current_count - 1
        
        return new_inventory
    
    def _update_user_inventory(self, user_id: str, new_inventory: Dict[str, int]) -> bool:
        """
        사용자 인벤토리 업데이트
        
        Args:
            user_id: 사용자 ID
            new_inventory: 새로운 인벤토리
            
        Returns:
            bool: 성공 여부
        """
        try:
            # 관리 워크시트 가져오기
            worksheet = self.sheets_manager.get_worksheet('관리', use_cache=False)
            all_values = worksheet.get_all_values()
            
            if not all_values:
                return False
            
            # 헤더에서 '아이디'와 '소지품' 컬럼 찾기
            headers = all_values[0]
            id_col = None
            inventory_col = None
            
            for i, header in enumerate(headers):
                if header == '아이디':
                    id_col = i
                elif header == '소지품':
                    inventory_col = i
            
            if id_col is None or inventory_col is None:
                return False
            
            # 사용자 행 찾기
            user_row = None
            for i, row in enumerate(all_values[1:], start=2):
                if len(row) > id_col and str(row[id_col]).strip() == user_id:
                    user_row = i
                    break
            
            if user_row is None:
                return False
            
            # 인벤토리를 JSON 문자열로 변환
            inventory_json = json.dumps(new_inventory, ensure_ascii=False)
            
            # 시트 업데이트
            return self.sheets_manager.update_cell('관리', user_row, inventory_col + 1, inventory_json)
            
        except Exception:
            return False
    
    def _format_use_message(self, item_name: str) -> str:
        """
        사용 메시지 포맷팅 (한국어 조사 처리)
        
        Args:
            item_name: 아이템명
            
        Returns:
            str: 포맷된 메시지
        """
        # 아이템명의 마지막 글자로 조사 결정
        last_char = get_last_char(item_name)
        has_consonant = has_final_consonant(last_char)
        
        # 받침에 따른 조사 선택
        josa = '을' if has_consonant else '를'
        
        return f"{item_name}{josa} 사용했습니다."
    
    def validate_context(self, context: CommandContext) -> Optional[str]:
        """컨텍스트 유효성 검증"""
        # 기본 검증
        error = super().validate_context(context)
        if error:
            return error
        
        # 최소 2개의 키워드 필요 (명령어 + 아이템명)
        if len(context.keywords) < 2:
            return "사용할 아이템명을 입력해주세요"
        
        return None
    
    def get_help_text(self) -> str:
        """도움말 텍스트 반환"""
        return (f"{self.command_description}\n"
                f"사용법: {', '.join(self.command_examples)}\n"
                f"아이템을 1개씩 사용하며, 0개가 되면 인벤토리에서 제거됩니다")
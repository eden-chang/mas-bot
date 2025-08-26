"""
소지품 조회 명령어

사용자의 현재 소지품과 소지금을 조회합니다.
[소지품] 명령어를 지원합니다.
"""

import os
import sys
import json
import ast
from typing import List, Dict, Any, Optional, Union

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.base_command import BaseCommand, CommandContext, CommandResponse
from config.settings import config
from utils.sheets_operations import SheetsManager


class InventoryCommand(BaseCommand):
    """소지품 조회 명령어"""
    
    # 명령어 메타데이터
    command_name = "소지품"
    command_description = "현재 소지품과 소지금을 확인합니다"
    command_category = "인벤토리"
    command_examples = ["[소지품]"]
    requires_sheets = True
    
    def __init__(self, sheets_manager: SheetsManager = None, **kwargs):
        super().__init__(sheets_manager=sheets_manager, **kwargs)
        
        # 환경변수에서 설정 로드
        self.currency = os.getenv('CURRENCY', '소지금')
        self.currency_eunneun = os.getenv('CURRENCY_EUNNEUN', '은')
        self.inventory_command = os.getenv('INVENTORY_COMMAND', '소지품')
    
    def execute(self, context: CommandContext) -> CommandResponse:
        """소지품 조회 실행"""
        try:
            # 명령어 매칭 확인
            if not self._matches_command(context.keywords):
                return CommandResponse.create_error("잘못된 명령어입니다")
            
            # 사용자 존재 확인
            if not self.sheets_manager.user_exists(context.user_id):
                return CommandResponse.create_error("등록되지 않은 사용자입니다")
            
            # 사용자 관리 데이터 조회 (캐시 사용 안함)
            user_data = self._get_user_management_data(context.user_id)
            
            if user_data is None:
                return CommandResponse.create_error("사용자 정보를 조회할 수 없습니다")
            
            # 소지품과 소지금 추출
            inventory_data = user_data.get('소지품', {})
            money_amount = user_data.get('소지금', 0)
            
            # 소지품 딕셔너리 파싱
            inventory_dict = self._parse_inventory_data(inventory_data)
            
            # 소지금 파싱 (money_command.py와 동일한 로직)
            parsed_money = self._parse_money_value(money_amount)
            
            # 응답 메시지 생성
            message = self._format_inventory_message(
                context.user_name, 
                inventory_dict, 
                parsed_money
            )
            
            return CommandResponse.create_success(message)
            
        except Exception as e:
            return CommandResponse.create_error(
                "소지품 조회 중 오류가 발생했습니다",
                error=e
            )
    
    def _matches_command(self, keywords: List[str]) -> bool:
        """명령어 매칭 확인"""
        if not keywords:
            return False
        
        first_keyword = keywords[0].lower()
        
        # 기본 명령어들
        base_commands = ['소지품', self.inventory_command.lower()]
        
        # 추가 가능한 명령어들
        additional_commands = ['인벤토리', 'inventory', 'inv', '아이템', 'item']
        
        all_commands = base_commands + additional_commands
        
        return first_keyword in all_commands
    
    def _get_user_management_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        사용자 관리 데이터 조회 (실시간, 캐시 사용 안함)
        
        Args:
            user_id: 사용자 ID
            
        Returns:
            Optional[Dict]: 사용자 관리 데이터 또는 None
        """
        try:
            # '관리' 탭에서 실시간으로 데이터 조회 (캐시 사용 안함)
            management_data = self.sheets_manager.get_worksheet_data('관리', use_cache=False)
            
            if not management_data:
                return None
            
            # 사용자 ID로 해당 행 찾기
            for row in management_data:
                row_id = str(row.get('아이디', '')).strip()
                
                if row_id == user_id:
                    return row
            
            return None
            
        except Exception as e:
            # 에러 로깅은 sheets_operations에서 처리됨
            return None
    
    def _parse_inventory_data(self, inventory_data: Any) -> Dict[str, int]:
        """
        소지품 데이터 파싱 (딕셔너리 형태로 변환)
        
        Args:
            inventory_data: 소지품 데이터 (문자열, 딕셔너리 등)
            
        Returns:
            Dict[str, int]: 파싱된 소지품 딕셔너리
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
            
            # 단순 문자열 파싱 시도 (예: "아이템1:1,아이템2:2")
            try:
                result = {}
                items = inventory_str.split(',')
                for item in items:
                    if ':' in item:
                        name, count = item.split(':', 1)
                        name = name.strip()
                        count = count.strip()
                        if name and count.isdigit():
                            result[name] = int(count)
                return result
            except:
                pass
        
        # 파싱 실패시 빈 딕셔너리 반환
        return {}
    
    def _parse_money_value(self, money_value: Any) -> int:
        """
        소지금 값 파싱 (money_command.py와 동일한 로직)
        
        Args:
            money_value: 소지금 값 (str 또는 int)
            
        Returns:
            int: 파싱된 소지금 값
        """
        if money_value is None:
            return 0
        
        # 이미 int인 경우
        if isinstance(money_value, int):
            return money_value
        
        # str인 경우 변환 시도
        if isinstance(money_value, str):
            # 공백 제거
            money_str = money_value.strip()
            
            if not money_str:
                return 0
            
            # 숫자가 아닌 문자 제거 (예: "1,234원" -> "1234")
            import re
            numeric_str = re.sub(r'[^\d-]', '', money_str)
            
            if not numeric_str:
                return 0
            
            try:
                return int(numeric_str)
            except ValueError:
                return 0
        
        # 기타 타입인 경우 str로 변환 후 다시 시도
        try:
            return self._parse_money_value(str(money_value))
        except:
            return 0
    
    def _format_inventory_message(
        self, 
        user_name: str, 
        inventory_dict: Dict[str, int], 
        money_amount: int
    ) -> str:
        """
        소지품 메시지 포맷팅
        
        Args:
            user_name: 사용자 이름
            inventory_dict: 소지품 딕셔너리
            money_amount: 소지금
            
        Returns:
            str: 포맷된 메시지
        """
        # 메시지 시작
        message_lines = [f"{user_name}의 현재 소지품은 다음과 같습니다."]
        message_lines.append("")  # 빈 줄
        
        # 소지품 목록
        if inventory_dict:
            for item_name, item_count in inventory_dict.items():
                if item_count > 0:  # 0개인 아이템은 표시하지 않음
                    message_lines.append(f"- {item_name} {item_count}개")
        else:
            message_lines.append("- 소지품이 없습니다.")
        
        # 빈 줄 추가
        message_lines.append("")
        
        # 소지금 정보
        message_lines.append(f"현재 {self.currency}: {money_amount:,}{self.currency}")
        
        return "\n".join(message_lines)
    
    def validate_context(self, context: CommandContext) -> Optional[str]:
        """컨텍스트 유효성 검증"""
        # 기본 검증
        error = super().validate_context(context)
        if error:
            return error
        
        # 소지품 명령어는 추가 키워드가 필요하지 않음
        return None
    
    def get_help_text(self) -> str:
        """도움말 텍스트 반환"""
        return (f"{self.command_description}\n"
                f"사용법: {', '.join(self.command_examples)}\n"
                f"현재 설정된 화폐 단위: {self.currency}")
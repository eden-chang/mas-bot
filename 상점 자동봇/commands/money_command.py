"""
소지금 조회 명령어

사용자의 현재 소지금을 조회합니다.
[소지금], [갈레온], [코인] 등 다양한 명령어를 지원합니다.
"""

import os
import sys
from typing import List, Dict, Any, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.base_command import BaseCommand, CommandContext, CommandResponse
from config.settings import config
from utils.sheets_operations import SheetsManager


class MoneyCommand(BaseCommand):
    """소지금 조회 명령어"""
    
    # 명령어 메타데이터
    command_name = "소지금"
    command_description = "현재 소지금을 확인합니다"
    command_category = "인벤토리"
    command_examples = ["[소지금]", "[갈레온]", "[코인]"]
    requires_sheets = True
    
    def __init__(self, sheets_manager: SheetsManager = None, **kwargs):
        super().__init__(sheets_manager=sheets_manager, **kwargs)
        
        # 환경변수에서 설정 로드
        self.currency = os.getenv('CURRENCY', '소지금')
        self.currency_eunneun = os.getenv('CURRENCY_EUNNEUN', '은')
        self.currency_command = os.getenv('CURRENCY_COMMAND', '소지금')
    
    def execute(self, context: CommandContext) -> CommandResponse:
        """소지금 조회 실행"""
        try:
            # 명령어 매칭 확인
            if not self._matches_command(context.keywords):
                return CommandResponse.create_error("잘못된 명령어입니다")
            
            # 사용자 존재 확인
            if not self.sheets_manager.user_exists(context.user_id):
                return CommandResponse.create_error("등록되지 않은 사용자입니다")
            
            # 소지금 조회 (캐시 사용 안함)
            money_amount = self._get_user_money(context.user_id)
            
            if money_amount is None:
                return CommandResponse.create_error("소지금 정보를 조회할 수 없습니다")
            
            # 응답 메시지 생성
            message = self._format_money_message(context.user_name, money_amount)
            
            return CommandResponse.create_success(message)
            
        except Exception as e:
            return CommandResponse.create_error(
                "소지금 조회 중 오류가 발생했습니다",
                error=e
            )
    
    def _matches_command(self, keywords: List[str]) -> bool:
        """명령어 매칭 확인"""
        if not keywords:
            return False
        
        first_keyword = keywords[0].lower()
        
        # 기본 명령어들
        base_commands = ['소지금', self.currency_command.lower()]
        
        # 추가 가능한 명령어들 (예: 갈레온, 코인 등)
        additional_commands = ['갈레온', '코인', '돈', '머니', 'money']
        
        all_commands = base_commands + additional_commands
        
        return first_keyword in all_commands
    
    def _get_user_money(self, user_id: str) -> Optional[int]:
        """
        사용자 소지금 조회 (실시간, 캐시 사용 안함)
        
        Args:
            user_id: 사용자 ID
            
        Returns:
            Optional[int]: 소지금 또는 None
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
                    # 소지금 정보 추출
                    money_value = row.get('소지금', 0)
                    
                    # str/int 타입 처리
                    return self._parse_money_value(money_value)
            
            return None
            
        except Exception as e:
            # 에러 로깅은 sheets_operations에서 처리됨
            return None
    
    def _parse_money_value(self, money_value: Any) -> int:
        """
        소지금 값 파싱 (str/int 타입 모두 처리)
        
        Args:
            money_value: 소지금 값 (str 또는 int)
            
        Returns:
            int: 파싱된 소지금 값
            
        Raises:
            ValueError: 파싱 실패시
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
    
    def _format_money_message(self, user_name: str, money_amount: int) -> str:
        """
        소지금 메시지 포맷팅
        
        Args:
            user_name: 사용자 이름
            money_amount: 소지금
            
        Returns:
            str: 포맷된 메시지
        """
        # {시전자 이름}의 현재 {CURRENCY}{CURRENCY_EUNNEUN} {소지금숫자}{CURRENCY}입니다.
        return f"{user_name}의 현재 {self.currency}{self.currency_eunneun} {money_amount:,}{self.currency}입니다."
    
    def validate_context(self, context: CommandContext) -> Optional[str]:
        """컨텍스트 유효성 검증"""
        # 기본 검증
        error = super().validate_context(context)
        if error:
            return error
        
        # 소지금 명령어는 추가 키워드가 필요하지 않음
        return None
    
    def get_help_text(self) -> str:
        """도움말 텍스트 반환"""
        return (f"{self.command_description}\n"
                f"사용법: {', '.join(self.command_examples)}\n"
                f"현재 설정된 화폐 단위: {self.currency}")
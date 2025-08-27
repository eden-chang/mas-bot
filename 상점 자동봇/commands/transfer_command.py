"""
양도 명령어

사용자가 아이템이나 소지금을 다른 사용자에게 양도하는 명령어입니다.
[양도/아이템명/캐릭터명] - 아이템 1개 양도
[양도/n{CURRENCY}/캐릭터명] - n만큼의 소지금 양도
"""

import os
import sys
import re
import json
import ast
from typing import List, Dict, Any, Optional, Union, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.base_command import BaseCommand, CommandContext, CommandResponse
from config.settings import config
from utils.sheets_operations import SheetsManager
from utils.korean_utils import add_eul_reul, add_i_ga
from utils.dm_sender import send_dm


class TransferCommand(BaseCommand):
    """양도 명령어"""
    
    # 명령어 메타데이터
    command_name = "양도"
    command_description = "아이템이나 소지금을 다른 사용자에게 양도합니다"
    command_category = "거래"
    command_examples = ["[양도/아이템명/캐릭터명]", "[양도/100갈레온/캐릭터명]"]
    requires_sheets = True
    
    def __init__(self, sheets_manager: SheetsManager = None, **kwargs):
        super().__init__(sheets_manager=sheets_manager, **kwargs)
        
        # 환경변수에서 설정 로드
        self.currency = os.getenv('CURRENCY', '갈레온')
        self.currency_eunneun = os.getenv('CURRENCY_EUNNEUN', '은')
    
    def execute(self, context: CommandContext) -> CommandResponse:
        """양도 명령어 실행"""
        try:
            # 프리미엄 기능 확인
            if not config.PREMIUM_TRANSFER_ENABLED:
                return CommandResponse.create_error(config.get_error_message('PREMIUM_TRANSFER_REQUIRED'))
            
            # 명령어 형식 검증 및 파싱
            parsed_data = self._parse_transfer_command(context.keywords)
            if not parsed_data:
                return CommandResponse.create_error("올바른 양도 명령어 형식이 아닙니다. [양도/아이템명 또는 금액/캐릭터명] 형식으로 입력해주세요.")
            
            transfer_type, transfer_item, target_character = parsed_data
            
            # 양도자 존재 확인
            if not self.sheets_manager.user_exists(context.user_id):
                return CommandResponse.create_error("등록되지 않은 사용자입니다.")
            
            # 수신자 존재 확인 및 ID 조회
            target_user_id = self._get_user_id_by_name(target_character)
            if not target_user_id:
                return CommandResponse.create_error(f"'{target_character}' 캐릭터를 찾을 수 없습니다.")
            
            # 자신에게 양도 방지
            if context.user_id == target_user_id:
                return CommandResponse.create_error("자신에게는 양도할 수 없습니다.")
            
            # 양도 타입에 따른 처리
            if transfer_type == "item":
                return self._transfer_item(context, transfer_item, target_character, target_user_id)
            elif transfer_type == "money":
                return self._transfer_money(context, transfer_item, target_character, target_user_id)
            
        except Exception as e:
            return CommandResponse.create_error(
                "양도 중 오류가 발생했습니다",
                error=e
            )
    
    def _parse_transfer_command(self, keywords: List[str]) -> Optional[Tuple[str, Union[str, int], str]]:
        """
        양도 명령어 파싱
        
        Returns:
            Optional[Tuple]: (transfer_type, transfer_item, target_character)
                - transfer_type: "item" 또는 "money"
                - transfer_item: 아이템명(str) 또는 금액(int)
                - target_character: 대상 캐릭터명
        """
        if len(keywords) < 3:
            return None
        
        if keywords[0].lower() != "양도":
            return None
        
        transfer_target = keywords[1]
        target_character = keywords[2]
        
        # 소지금 양도 패턴 확인 (예: 100갈레온, 50소지금)
        money_pattern = rf"^(\d+){re.escape(self.currency)}$"
        money_match = re.match(money_pattern, transfer_target)
        
        if money_match:
            amount = int(money_match.group(1))
            return ("money", amount, target_character)
        else:
            # 아이템 양도
            return ("item", transfer_target, target_character)
    
    def _get_user_id_by_name(self, character_name: str) -> Optional[str]:
        """
        캐릭터 이름으로 사용자 ID 조회
        
        Args:
            character_name: 캐릭터 이름
            
        Returns:
            Optional[str]: 사용자 ID 또는 None
        """
        try:
            # '명단' 탭에서 실시간으로 데이터 조회
            roster_data = self.sheets_manager.get_worksheet_data('명단', use_cache=False)
            
            if not roster_data:
                return None
            
            # 캐릭터 이름으로 검색
            for row in roster_data:
                row_name = str(row.get('이름', '')).strip()
                if row_name == character_name:
                    return str(row.get('아이디', '')).strip()
            
            return None
            
        except Exception:
            return None
    
    def _transfer_item(self, context: CommandContext, item_name: str, 
                      target_character: str, target_user_id: str) -> CommandResponse:
        """
        아이템 양도 처리
        
        Args:
            context: 명령어 컨텍스트
            item_name: 양도할 아이템명
            target_character: 대상 캐릭터명
            target_user_id: 대상 사용자 ID
            
        Returns:
            CommandResponse: 처리 결과
        """
        try:
            # 양도자 소지품 조회
            sender_data = self._get_user_management_data(context.user_id)
            if not sender_data:
                return CommandResponse.create_error("양도자 정보를 조회할 수 없습니다.")
            
            # 수신자 소지품 조회
            receiver_data = self._get_user_management_data(target_user_id)
            if not receiver_data:
                return CommandResponse.create_error("수신자 정보를 조회할 수 없습니다.")
            
            # 양도자 소지품 파싱
            sender_inventory = self._parse_inventory_data(sender_data.get('소지품', {}))
            
            # 아이템 보유 확인
            if item_name not in sender_inventory or sender_inventory[item_name] < 1:
                return CommandResponse.create_error(f"'{item_name}' 아이템을 보유하고 있지 않습니다.")
            
            # 수신자 소지품 파싱
            receiver_inventory = self._parse_inventory_data(receiver_data.get('소지품', {}))
            
            # 아이템 이동
            sender_inventory[item_name] -= 1
            if sender_inventory[item_name] == 0:
                del sender_inventory[item_name]
            
            receiver_inventory[item_name] = receiver_inventory.get(item_name, 0) + 1
            
            # 시트 업데이트
            success = self._update_inventories(context.user_id, target_user_id, 
                                             sender_inventory, receiver_inventory)
            
            if not success:
                return CommandResponse.create_error("시트 업데이트 중 오류가 발생했습니다.")
            
            # 성공 메시지 생성 (조사 적용)
            item_with_particle = add_eul_reul(item_name)
            success_message = f"{target_character}에게 {item_with_particle} 성공적으로 양도했습니다."
            
            # DM 전송 (수신자에게)
            self._send_transfer_notification_dm(target_user_id, context.user_name, item_name)
            
            return CommandResponse.create_success(success_message)
            
        except Exception as e:
            return CommandResponse.create_error(f"아이템 양도 중 오류가 발생했습니다: {str(e)}")
    
    def _transfer_money(self, context: CommandContext, amount: int,
                       target_character: str, target_user_id: str) -> CommandResponse:
        """
        소지금 양도 처리
        
        Args:
            context: 명령어 컨텍스트
            amount: 양도할 금액
            target_character: 대상 캐릭터명  
            target_user_id: 대상 사용자 ID
            
        Returns:
            CommandResponse: 처리 결과
        """
        try:
            if amount <= 0:
                return CommandResponse.create_error("0보다 큰 금액을 입력해주세요.")
            
            # 양도자 소지금 조회
            sender_data = self._get_user_management_data(context.user_id)
            if not sender_data:
                return CommandResponse.create_error("양도자 정보를 조회할 수 없습니다.")
            
            # 수신자 소지금 조회
            receiver_data = self._get_user_management_data(target_user_id)
            if not receiver_data:
                return CommandResponse.create_error("수신자 정보를 조회할 수 없습니다.")
            
            # 양도자 소지금 파싱
            sender_money = self._parse_money_value(sender_data.get('소지금', 0))
            
            # 잔액 확인
            if sender_money < amount:
                return CommandResponse.create_error(f"소지금이 부족합니다. (보유: {sender_money:,}{self.currency})")
            
            # 수신자 소지금 파싱
            receiver_money = self._parse_money_value(receiver_data.get('소지금', 0))
            
            # 금액 이동
            new_sender_money = sender_money - amount
            new_receiver_money = receiver_money + amount
            
            # 시트 업데이트
            success = self._update_money(context.user_id, target_user_id, 
                                       new_sender_money, new_receiver_money)
            
            if not success:
                return CommandResponse.create_error("시트 업데이트 중 오류가 발생했습니다.")
            
            # 성공 메시지 생성 (조사 적용)
            money_text = f"{amount:,}{self.currency}"
            money_with_particle = add_eul_reul(money_text)
            success_message = f"{target_character}에게 {money_with_particle} 성공적으로 양도했습니다."
            
            # DM 전송 (수신자에게)
            self._send_transfer_notification_dm(target_user_id, context.user_name, money_text)
            
            return CommandResponse.create_success(success_message)
            
        except Exception as e:
            return CommandResponse.create_error(f"소지금 양도 중 오류가 발생했습니다: {str(e)}")
    
    def _get_user_management_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        사용자 관리 데이터 조회 (실시간)
        
        Args:
            user_id: 사용자 ID
            
        Returns:
            Optional[Dict]: 사용자 관리 데이터 또는 None
        """
        try:
            # '관리' 탭에서 실시간으로 데이터 조회
            management_data = self.sheets_manager.get_worksheet_data('관리', use_cache=False)
            
            if not management_data:
                return None
            
            # 사용자 ID로 해당 행 찾기
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
        
        # 파싱 실패시 빈 딕셔너리 반환
        return {}
    
    def _parse_money_value(self, money_value: Any) -> int:
        """
        소지금 값 파싱 (money_command.py와 동일한 로직)
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
            
            # 숫자가 아닌 문자 제거
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
    
    def _update_inventories(self, sender_id: str, receiver_id: str,
                          sender_inventory: Dict[str, int], 
                          receiver_inventory: Dict[str, int]) -> bool:
        """
        소지품 시트 업데이트
        
        Args:
            sender_id: 양도자 ID
            receiver_id: 수신자 ID
            sender_inventory: 업데이트할 양도자 소지품
            receiver_inventory: 업데이트할 수신자 소지품
            
        Returns:
            bool: 성공 여부
        """
        try:
            # 소지품을 문자열로 변환 (JSON 형태)
            sender_inventory_str = json.dumps(sender_inventory, ensure_ascii=False) if sender_inventory else "{}"
            receiver_inventory_str = json.dumps(receiver_inventory, ensure_ascii=False) if receiver_inventory else "{}"
            
            # 양도자 소지품 업데이트
            success1 = self.sheets_manager.update_user_field(sender_id, '소지품', sender_inventory_str)
            if not success1:
                return False
            
            # 수신자 소지품 업데이트
            success2 = self.sheets_manager.update_user_field(receiver_id, '소지품', receiver_inventory_str)
            return success2
            
        except Exception:
            return False
    
    def _update_money(self, sender_id: str, receiver_id: str,
                     sender_money: int, receiver_money: int) -> bool:
        """
        소지금 시트 업데이트
        
        Args:
            sender_id: 양도자 ID
            receiver_id: 수신자 ID
            sender_money: 업데이트할 양도자 소지금
            receiver_money: 업데이트할 수신자 소지금
            
        Returns:
            bool: 성공 여부
        """
        try:
            # 양도자 소지금 업데이트
            success1 = self.sheets_manager.update_user_field(sender_id, '소지금', sender_money)
            if not success1:
                return False
            
            # 수신자 소지금 업데이트
            success2 = self.sheets_manager.update_user_field(receiver_id, '소지금', receiver_money)
            return success2
            
        except Exception:
            return False
    
    def _send_transfer_notification_dm(self, receiver_id: str, sender_name: str, item_name: str) -> None:
        """
        양도 알림 DM 전송
        
        Args:
            receiver_id: 수신자 ID
            sender_name: 양도자 이름
            item_name: 양도된 아이템/금액
        """
        try:
            # 조사 적용
            sender_with_subject = add_i_ga("누군가")  # "누군가가"
            item_with_particle = add_eul_reul(item_name)
            
            message = f"{sender_with_subject} 당신에게 {item_with_particle} 양도했습니다."
            send_dm(receiver_id, message)
            
        except Exception as e:
            # DM 전송 실패는 로그만 남기고 명령어는 성공 처리
            pass
    
    def validate_context(self, context: CommandContext) -> Optional[str]:
        """컨텍스트 유효성 검증"""
        # 기본 검증
        error = super().validate_context(context)
        if error:
            return error
        
        # 양도 명령어는 최소 3개의 키워드가 필요 ([양도, 아이템/금액, 캐릭터명])
        if not context.keywords or len(context.keywords) < 3:
            return "양도 명령어는 [양도/아이템명 또는 금액/캐릭터명] 형식으로 입력해주세요"
        
        return None
    
    def get_help_text(self) -> str:
        """도움말 텍스트 반환"""
        return (f"{self.command_description}\n"
                f"사용법:\n"
                f"  - 아이템 양도: [양도/아이템명/캐릭터명]\n"
                f"  - 소지금 양도: [양도/금액{self.currency}/캐릭터명]\n"
                f"예시: [양도/사과/홍길동], [양도/100{self.currency}/홍길동]")
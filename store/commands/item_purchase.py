"""
아이템 구매 명령어

상점에서 아이템을 구매합니다.
[구매 아이템명] 또는 [구매 아이템명 n개] 형태의 명령어를 지원합니다.
"""

import os
import sys
import json
import ast
import re
from typing import List, Dict, Any, Optional, Tuple
from difflib import SequenceMatcher

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.base_command import BaseCommand, CommandContext, CommandResponse
from config.settings import config
from utils.sheets_operations import SheetsManager
from utils.korean_utils import add_eun_neun


class ItemPurchaseCommand(BaseCommand):
    """아이템 구매 명령어"""
    
    # 명령어 메타데이터
    command_name = "구매"
    command_description = "상점에서 아이템을 구매합니다"
    command_category = "상점"
    command_examples = ["[구매 가챠]", "[구매 송충이 3개]", "[구매 별사탕 5]"]
    requires_sheets = True
    
    def __init__(self, sheets_manager: SheetsManager = None, **kwargs):
        super().__init__(sheets_manager=sheets_manager, **kwargs)
        
        # 환경변수에서 설정 로드
        self.currency = os.getenv('CURRENCY', '소지금')
        self.currency_eunneun = os.getenv('CURRENCY_EUNNEUN', '은')
    
    def execute(self, context: CommandContext) -> CommandResponse:
        """아이템 구매 실행"""
        try:
            # 명령어 파싱
            purchase_info = self._parse_purchase_command(context.keywords)
            if not purchase_info:
                return CommandResponse.create_error(
                    "구매 명령어 형식이 올바르지 않습니다.\n예: [구매 가챠], [구매 송충이 3개]"
                )
            
            item_name, quantity = purchase_info
            
            # 사용자 존재 확인
            if not self.sheets_manager.user_exists(context.user_id):
                return CommandResponse.create_error("등록되지 않은 사용자입니다")
            
            # 상점에서 아이템 찾기
            store_item = self._find_store_item(item_name)
            if not store_item:
                # '구매 불가' 아이템인지 확인
                if self._is_non_purchasable_item(item_name):
                    return CommandResponse.create_error(f"'{item_name}'{add_eun_neun(item_name)[len(item_name):]} 상점에서 구매할 수 없습니다")
                else:
                    return CommandResponse.create_error(f"'{item_name}'{add_eun_neun(item_name)[len(item_name):]} 존재하지 않는 아이템입니다")
            
            actual_item_name, item_price = store_item
            total_cost = item_price * quantity
            
            # 사용자 데이터 조회
            user_data = self._get_user_data(context.user_id)
            if not user_data:
                return CommandResponse.create_error("사용자 정보를 조회할 수 없습니다")
            
            current_money = self._parse_money_value(user_data.get('소지금', 0))
            
            # 소지금 확인
            if current_money < total_cost:
                return CommandResponse.create_error(
                    f"소지금이 부족합니다. 필요: {total_cost:,}{self.currency}, 현재: {current_money:,}{self.currency}"
                )
            
            # 구매 처리
            new_money = current_money - total_cost
            new_inventory = self._add_to_inventory(user_data.get('소지품', {}), actual_item_name, quantity)
            
            # 시트 업데이트
            success = self._update_user_data(context.user_id, new_money, new_inventory)
            if not success:
                return CommandResponse.create_error("구매 처리에 실패했습니다")
            
            # 성공 메시지
            message = self._format_success_message(actual_item_name, quantity, new_money)
            return CommandResponse.create_success(message)
            
        except Exception as e:
            return CommandResponse.create_error(
                "아이템 구매 중 오류가 발생했습니다",
                error=e
            )
    
    def _parse_purchase_command(self, keywords: List[str]) -> Optional[Tuple[str, int]]:
        """
        구매 명령어 파싱
        
        Returns:
            Optional[Tuple[str, int]]: (아이템명, 수량) 또는 None
        """
        if not keywords or len(keywords) < 2:
            return None
        
        if keywords[0].lower() not in ['구매', 'buy', '사기', '구입']:
            return None
        
        # 나머지 키워드들 처리
        remaining = keywords[1:]
        
        # 마지막 키워드에서 숫자 추출 시도
        quantity = 1
        item_keywords = remaining[:]
        
        if remaining:
            last_keyword = remaining[-1]
            
            # "3개", "5개" 형태
            match = re.match(r'(\d+)개?$', last_keyword)
            if match:
                quantity = int(match.group(1))
                item_keywords = remaining[:-1]
            # 단순 숫자 "3", "5" 형태
            elif last_keyword.isdigit():
                quantity = int(last_keyword)
                item_keywords = remaining[:-1]
        
        if not item_keywords:
            return None
        
        # 아이템명 결합
        item_name = ' '.join(item_keywords).strip()
        
        # 수량 유효성 검사
        if quantity <= 0 or quantity > 100:  # 최대 100개 제한
            return None
        
        return (item_name, quantity)
    
    def _find_store_item(self, item_name: str) -> Optional[Tuple[str, int]]:
        """
        상점에서 아이템 검색
        
        Returns:
            Optional[Tuple[str, int]]: (실제_아이템명, 가격) 또는 None
        """
        try:
            store_data = self.sheets_manager.get_worksheet_data('상점', use_cache=True)
            if not store_data:
                return None
            
            # 띄어쓰기, 대소문자 무시하고 비교
            normalized_search = re.sub(r'\s+', '', item_name.lower())
            
            # 정확한 매칭 시도
            for row in store_data:
                row_item_name = str(row.get('아이템명', '')).strip()
                price_str = str(row.get('가격', '')).strip()
                
                if not row_item_name or not price_str:
                    continue
                
                normalized_row = re.sub(r'\s+', '', row_item_name.lower())
                
                if normalized_row == normalized_search:
                    price = self._parse_price(price_str)
                    if price > 0:
                        return (row_item_name, price)
            
            # 부분 매칭 시도
            best_match = None
            best_similarity = 0.0
            
            for row in store_data:
                row_item_name = str(row.get('아이템명', '')).strip()
                price_str = str(row.get('가격', '')).strip()
                
                if not row_item_name or not price_str:
                    continue
                
                normalized_row = re.sub(r'\s+', '', row_item_name.lower())
                
                # 포함 관계 확인
                if normalized_search in normalized_row:
                    price = self._parse_price(price_str)
                    if price > 0:
                        similarity = len(normalized_search) / len(normalized_row)
                        if similarity > best_similarity:
                            best_similarity = similarity
                            best_match = (row_item_name, price)
                
                # 유사도 확인
                similarity = SequenceMatcher(None, normalized_search, normalized_row).ratio()
                if similarity > 0.6 and similarity > best_similarity:
                    price = self._parse_price(price_str)
                    if price > 0:
                        best_similarity = similarity
                        best_match = (row_item_name, price)
            
            return best_match
            
        except Exception:
            return None
    
    def _is_non_purchasable_item(self, item_name: str) -> bool:
        """아이템이 '구매 불가' 아이템인지 확인"""
        try:
            store_data = self.sheets_manager.get_worksheet_data('상점', use_cache=True)
            if not store_data:
                return False
            
            # 띄어쓰기, 대소문자 무시하고 비교
            normalized_search = re.sub(r'\s+', '', item_name.lower())
            
            for row in store_data:
                row_item_name = str(row.get('아이템명', '')).strip()
                price_str = str(row.get('가격', '')).strip()
                
                if not row_item_name:
                    continue
                
                normalized_row = re.sub(r'\s+', '', row_item_name.lower())
                
                # 아이템명이 일치하는지 확인
                if (normalized_row == normalized_search or 
                    normalized_search in normalized_row):
                    # 가격이 '구매 불가'인지 확인
                    if price_str.lower().strip() in ['구매 불가', '구매불가', '불가']:
                        return True
            
            return False
            
        except Exception:
            return False
    
    def _parse_price(self, price_str: str) -> int:
        """가격 문자열 파싱 (구매 불가 아이템 제외)"""
        if not price_str:
            return 0
        
        # '구매 불가' 아이템은 가격 0 반환 (구매 불가능)
        if price_str.lower().strip() in ['구매 불가', '구매불가', '불가']:
            return 0
        
        numeric_str = re.sub(r'[^\d]', '', price_str)
        if not numeric_str:
            return 0
        
        try:
            return int(numeric_str)
        except ValueError:
            return 0
    
    def _get_user_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        """사용자 데이터 조회"""
        try:
            management_data = self.sheets_manager.get_worksheet_data('관리', use_cache=False)
            if not management_data:
                return None
            
            for row in management_data:
                if str(row.get('아이디', '')).strip() == user_id:
                    return row
            
            return None
        except Exception:
            return None
    
    def _parse_money_value(self, money_value: Any) -> int:
        """소지금 값 파싱 (기존 로직 재사용)"""
        if money_value is None:
            return 0
        
        if isinstance(money_value, int):
            return money_value
        
        if isinstance(money_value, str):
            money_str = money_value.strip()
            if not money_str:
                return 0
            
            numeric_str = re.sub(r'[^\d-]', '', money_str)
            if not numeric_str:
                return 0
            
            try:
                return int(numeric_str)
            except ValueError:
                return 0
        
        try:
            return self._parse_money_value(str(money_value))
        except:
            return 0
    
    def _add_to_inventory(self, inventory_data: Any, item_name: str, quantity: int) -> Dict[str, int]:
        """인벤토리에 아이템 추가"""
        # 기존 인벤토리 파싱
        current_inventory = self._parse_inventory_data(inventory_data)
        
        # 아이템 추가
        if item_name in current_inventory:
            current_inventory[item_name] += quantity
        else:
            current_inventory[item_name] = quantity
        
        return current_inventory
    
    def _parse_inventory_data(self, inventory_data: Any) -> Dict[str, int]:
        """소지품 데이터 파싱 (기존 로직 재사용)"""
        if not inventory_data:
            return {}
        
        if isinstance(inventory_data, dict):
            return {str(k): int(v) if str(v).isdigit() else 0 
                    for k, v in inventory_data.items() if k and v}
        
        if isinstance(inventory_data, str):
            inventory_str = inventory_data.strip()
            if not inventory_str:
                return {}
            
            try:
                parsed = json.loads(inventory_str)
                if isinstance(parsed, dict):
                    return {str(k): int(v) if str(v).isdigit() else 0 
                            for k, v in parsed.items() if k and v}
            except json.JSONDecodeError:
                pass
            
            try:
                parsed = ast.literal_eval(inventory_str)
                if isinstance(parsed, dict):
                    return {str(k): int(v) if str(v).isdigit() else 0 
                            for k, v in parsed.items() if k and v}
            except (ValueError, SyntaxError):
                pass
        
        return {}
    
    def _update_user_data(self, user_id: str, new_money: int, new_inventory: Dict[str, int]) -> bool:
        """사용자 데이터 업데이트"""
        try:
            worksheet = self.sheets_manager.get_worksheet('관리', use_cache=False)
            all_values = worksheet.get_all_values()
            
            if not all_values:
                return False
            
            headers = all_values[0]
            id_col = money_col = inventory_col = None
            
            for i, header in enumerate(headers):
                if header == '아이디':
                    id_col = i
                elif header == '소지금':
                    money_col = i
                elif header == '소지품':
                    inventory_col = i
            
            if None in (id_col, money_col, inventory_col):
                return False
            
            # 사용자 행 찾기
            user_row = None
            for i, row in enumerate(all_values[1:], start=2):
                if len(row) > id_col and str(row[id_col]).strip() == user_id:
                    user_row = i
                    break
            
            if user_row is None:
                return False
            
            # 데이터 업데이트
            inventory_json = json.dumps(new_inventory, ensure_ascii=False)
            
            # 소지금과 소지품 동시 업데이트
            money_success = self.sheets_manager.update_cell('관리', user_row, money_col + 1, new_money)
            inventory_success = self.sheets_manager.update_cell('관리', user_row, inventory_col + 1, inventory_json)
            
            return money_success and inventory_success
            
        except Exception:
            return False
    
    def _format_success_message(self, item_name: str, quantity: int, remaining_money: int) -> str:
        """구매 성공 메시지 포맷팅"""
        lines = [
            f"{item_name} {quantity}개 구매에 성공했습니다.",
            f"잔여 {self.currency}{self.currency_eunneun} {remaining_money:,}{self.currency}입니다."
        ]
        return "\n".join(lines)
    
    def validate_context(self, context: CommandContext) -> Optional[str]:
        """컨텍스트 유효성 검증"""
        error = super().validate_context(context)
        if error:
            return error
        
        if len(context.keywords) < 2:
            return "구매할 아이템명을 입력해주세요"
        
        return None
    
    def get_help_text(self) -> str:
        """도움말 텍스트 반환"""
        return (f"{self.command_description}\n"
                f"사용법: {', '.join(self.command_examples)}\n"
                f"최대 100개까지 구매 가능하며, 띄어쓰기와 대소문자는 무시됩니다")
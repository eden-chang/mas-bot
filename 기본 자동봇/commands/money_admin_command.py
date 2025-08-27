"""
소지금 관리 명령어 구현
관리자용 소지금 추가/차감 명령어를 관리하는 클래스입니다.
"""

import os
import sys
import re
from typing import List, Tuple, Any, Optional, Dict

# 경로 설정 (VM 환경 대응)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    from config.settings import config
    from utils.logging_config import logger
    from utils.error_handling import CommandError
    from commands.base_command import BaseCommand
    from models.user import User
    from models.command_result import CommandType
except ImportError:
    # VM 환경에서 임포트 실패 시 폴백
    import logging
    logger = logging.getLogger('money_admin_command')
    
    # 기본 클래스들 정의
    class CommandError(Exception):
        pass
    
    class BaseCommand:
        pass


class MoneyAdminCommand(BaseCommand):
    """
    소지금 관리 명령어 클래스
    
    관리자가 사용자들의 소지금을 일괄 추가/차감하는 시스템을 구현합니다.
    
    지원하는 형식:
    - [소지금 추가/금액/캐릭터명] : 특정 캐릭터의 소지금 추가
    - [소지금 차감/금액/캐릭터명] : 특정 캐릭터의 소지금 차감
    - [소지금추가/금액/캐릭터명] : 공백 없는 형식
    - [소지금차감/금액/캐릭터명] : 공백 없는 형식
    - [소지금 추가/금액/캐릭터1,캐릭터2,캐릭터3] : 여러 캐릭터 동시 처리
    - [소지금 차감/금액/전원] : 전체 캐릭터 처리
    
    처리 순서:
    1. 명령어 형식 검증 (추가/차감, 금액, 대상 분석)
    2. 대상 캐릭터 목록 해석 (개별/복수/전원)
    3. 현재 소지금 조회 및 계산
    4. 배치 업데이트로 일괄 적용
    5. 결과 메시지 생성
    """
    
    def _get_command_type(self) -> CommandType:
        """명령어 타입 반환"""
        return CommandType.MONEY_TRANSFER  # 기존 타입 재사용
    
    def _get_command_name(self) -> str:
        """명령어 이름 반환"""
        return "소지금관리"
    
    def _execute_command(self, user: User, keywords: List[str]) -> Tuple[str, Any]:
        """
        소지금 관리 명령어 실행
        
        Args:
            user: 사용자 객체
            keywords: 명령어 키워드 리스트
            
        Returns:
            Tuple[str, Any]: (결과 메시지, 결과 데이터)
            
        Raises:
            CommandError: 명령어 실행 오류
        """
        if not self.sheets_manager:
            raise CommandError("시트 관리자가 설정되지 않았습니다.")
        
        try:
            # 1. 명령어 파싱
            operation, amount, targets = self._parse_money_command(keywords)
            
            # 2. 대상 캐릭터 목록 해석
            target_characters = self._resolve_target_characters(targets)
            if not target_characters:
                raise CommandError("처리할 대상 캐릭터가 없습니다.")
            
            # 3. 배치 업데이트 실행
            results = self._execute_batch_money_update(operation, amount, target_characters)
            
            # 4. 결과 메시지 생성
            result_message = self._generate_result_message(operation, amount, results)
            
            result_data = {
                'operation': operation,
                'amount': amount,
                'total_targets': len(target_characters),
                'successful_updates': len([r for r in results if r['success']]),
                'failed_updates': len([r for r in results if not r['success']]),
                'results': results
            }
            
            logger.info(f"소지금 관리 명령어 실행 완료: {operation} {amount} -> {len(target_characters)}명 대상")
            return result_message, result_data
            
        except CommandError:
            raise
        except Exception as e:
            logger.error(f"소지금 관리 명령어 실행 중 오류: {e}")
            raise CommandError("소지금 관리 명령어 실행 중 오류가 발생했습니다.")
    
    def _parse_money_command(self, keywords: List[str]) -> Tuple[str, int, str]:
        """
        명령어 키워드 파싱
        
        Args:
            keywords: 키워드 리스트
            
        Returns:
            Tuple[str, int, str]: (작업타입, 금액, 대상)
            
        Raises:
            CommandError: 파싱 오류
        """
        if len(keywords) < 3:
            raise CommandError("명령어 형식이 올바르지 않습니다. [소지금 추가/금액/대상] 형식으로 입력해주세요.")
        
        # 첫 번째 키워드에서 작업 타입 추출
        first_keyword = keywords[0].replace(" ", "").lower()
        
        if first_keyword in ['소지금추가', '소지금 추가']:
            operation = "추가"
        elif first_keyword in ['소지금차감', '소지금 차감']:
            operation = "차감"
        else:
            raise CommandError("지원하지 않는 작업입니다. '소지금 추가' 또는 '소지금 차감'을 사용해주세요.")
        
        # 두 번째 키워드에서 금액 추출
        try:
            amount = int(keywords[1])
            if amount <= 0:
                raise ValueError("금액은 양수여야 합니다.")
        except ValueError:
            raise CommandError("금액은 양의 정수로 입력해주세요.")
        
        # 세 번째 키워드에서 대상 추출
        targets = keywords[2]
        
        return operation, amount, targets
    
    def _resolve_target_characters(self, targets: str) -> List[str]:
        """
        대상 문자열을 캐릭터 목록으로 해석
        
        Args:
            targets: 대상 문자열 ("전원", "캐릭터1,캐릭터2" 등)
            
        Returns:
            List[str]: 캐릭터 이름 목록
        """
        try:
            # "전원" 처리
            if targets.strip() == "전원":
                return self._get_all_characters()
            
            # 쉼표로 구분된 캐릭터 목록 처리
            character_list = []
            for char_name in targets.split(','):
                char_name = char_name.strip()
                if char_name:
                    character_list.append(char_name)
            
            return character_list
            
        except Exception as e:
            logger.error(f"대상 캐릭터 해석 실패: {targets} -> {e}")
            return []
    
    def _get_all_characters(self) -> List[str]:
        """
        명단에서 모든 캐릭터 이름 조회
        
        Returns:
            List[str]: 모든 캐릭터 이름 목록
        """
        try:
            user_data = self.sheets_manager.get_worksheet_data('명단')
            characters = []
            
            for row in user_data:
                name = str(row.get('이름', '')).strip()
                if name:
                    characters.append(name)
            
            logger.debug(f"전체 캐릭터 조회: {len(characters)}명")
            return characters
            
        except Exception as e:
            logger.error(f"전체 캐릭터 조회 실패: {e}")
            return []
    
    def _execute_batch_money_update(self, operation: str, amount: int, target_characters: List[str]) -> List[Dict]:
        """
        배치 업데이트로 소지금 일괄 변경
        
        Args:
            operation: 작업 타입 ("추가" 또는 "차감")
            amount: 변경할 금액
            target_characters: 대상 캐릭터 목록
            
        Returns:
            List[Dict]: 각 캐릭터별 처리 결과
        """
        results = []
        
        try:
            # 1. 현재 명단 데이터 조회
            roster_data = self.sheets_manager.get_worksheet_data('명단')
            
            # 2. 소지금 컬럼 찾기
            money_col = self._find_money_column()
            if money_col is None:
                for char in target_characters:
                    results.append({
                        'character': char,
                        'success': False,
                        'error': '소지금 컬럼을 찾을 수 없습니다'
                    })
                return results
            
            # 3. 배치 업데이트용 데이터 준비
            batch_updates = []
            
            for char_name in target_characters:
                try:
                    # 캐릭터 찾기
                    char_row = None
                    current_money = 0
                    
                    for i, row in enumerate(roster_data):
                        if str(row.get('이름', '')).strip() == char_name:
                            char_row = i + 2  # 헤더 행 고려 (1부터 시작)
                            money_value = row.get(self._get_money_column_name(), 0)
                            try:
                                current_money = int(money_value) if money_value else 0
                            except (ValueError, TypeError):
                                current_money = 0
                            break
                    
                    if char_row is None:
                        results.append({
                            'character': char_name,
                            'success': False,
                            'error': '캐릭터를 찾을 수 없습니다'
                        })
                        continue
                    
                    # 새로운 금액 계산
                    if operation == "추가":
                        new_money = current_money + amount
                    else:  # 차감
                        new_money = max(0, current_money - amount)  # 음수 방지
                    
                    # 배치 업데이트 데이터 추가
                    batch_updates.append({
                        'range': f'{self._get_column_letter(money_col)}{char_row}',
                        'values': [[new_money]]
                    })
                    
                    results.append({
                        'character': char_name,
                        'success': True,
                        'old_money': current_money,
                        'new_money': new_money,
                        'change': new_money - current_money
                    })
                    
                except Exception as e:
                    results.append({
                        'character': char_name,
                        'success': False,
                        'error': str(e)
                    })
            
            # 4. 배치 업데이트 실행
            if batch_updates:
                success = self._execute_batch_update(batch_updates)
                if not success:
                    logger.error("배치 업데이트 실패")
                    # 모든 성공 결과를 실패로 변경
                    for result in results:
                        if result.get('success'):
                            result['success'] = False
                            result['error'] = '배치 업데이트 실패'
            
            return results
            
        except Exception as e:
            logger.error(f"배치 소지금 업데이트 실패: {e}")
            return [{'character': char, 'success': False, 'error': str(e)} for char in target_characters]
    
    def _find_money_column(self) -> Optional[int]:
        """
        명단 시트에서 소지금 컬럼 번호 찾기
        
        Returns:
            Optional[int]: 컬럼 번호 (1부터 시작) 또는 None
        """
        try:
            worksheet = self.sheets_manager.get_worksheet('명단')
            header_row = worksheet.row_values(1)
            
            # '소지금' 포함 헤더 찾기
            for i, header in enumerate(header_row):
                if '소지금' in str(header):
                    return i + 1
            
            logger.warning("소지금 컬럼을 찾을 수 없습니다.")
            return None
            
        except Exception as e:
            logger.error(f"소지금 컬럼 찾기 실패: {e}")
            return None
    
    def _get_money_column_name(self) -> str:
        """
        소지금 컬럼의 정확한 이름 반환
        
        Returns:
            str: 소지금 컬럼 이름
        """
        try:
            worksheet = self.sheets_manager.get_worksheet('명단')
            header_row = worksheet.row_values(1)
            
            for header in header_row:
                if '소지금' in str(header):
                    return str(header)
            
            return '소지금'  # 기본값
            
        except Exception:
            return '소지금'  # 기본값
    
    def _get_column_letter(self, col_num: int) -> str:
        """
        컬럼 번호를 알파벳으로 변환 (1->A, 2->B, ...)
        
        Args:
            col_num: 컬럼 번호 (1부터 시작)
            
        Returns:
            str: 컬럼 알파벳
        """
        result = ""
        while col_num > 0:
            col_num -= 1
            result = chr(col_num % 26 + ord('A')) + result
            col_num //= 26
        return result
    
    def _execute_batch_update(self, batch_updates: List[Dict]) -> bool:
        """
        Google Sheets 배치 업데이트 실행
        
        Args:
            batch_updates: 업데이트할 데이터 목록
            
        Returns:
            bool: 성공 여부
        """
        try:
            worksheet = self.sheets_manager.get_worksheet('명단')
            
            # gspread의 batch_update 사용
            # 각 업데이트를 개별적으로 처리하거나 SheetsManager의 batch_update 사용
            for update in batch_updates:
                try:
                    # range 파싱 (예: "D5" -> row=5, col=4)
                    range_str = update['range']
                    col_letter = ''.join(filter(str.isalpha, range_str))
                    row_num = int(''.join(filter(str.isdigit, range_str)))
                    col_num = self._column_letter_to_number(col_letter)
                    
                    value = update['values'][0][0]
                    
                    # 개별 셀 업데이트
                    worksheet.update_cell(row_num, col_num, value)
                    
                except Exception as e:
                    logger.error(f"개별 셀 업데이트 실패: {update} -> {e}")
                    return False
            
            logger.info(f"배치 업데이트 성공: {len(batch_updates)}개 셀")
            return True
            
        except Exception as e:
            logger.error(f"배치 업데이트 실패: {e}")
            return False
    
    def _column_letter_to_number(self, col_letter: str) -> int:
        """
        컬럼 알파벳을 번호로 변환 (A->1, B->2, ...)
        
        Args:
            col_letter: 컬럼 알파벳
            
        Returns:
            int: 컬럼 번호 (1부터 시작)
        """
        result = 0
        for char in col_letter.upper():
            result = result * 26 + (ord(char) - ord('A') + 1)
        return result
    
    def _generate_result_message(self, operation: str, amount: int, results: List[Dict]) -> str:
        """
        결과 메시지 생성
        
        Args:
            operation: 작업 타입
            amount: 변경 금액
            results: 처리 결과 목록
            
        Returns:
            str: 결과 메시지
        """
        successful = [r for r in results if r.get('success')]
        failed = [r for r in results if not r.get('success')]
        
        message_parts = []
        
        # 기본 정보
        currency_unit = self.sheets_manager.get_currency_setting() or "포인트"
        message_parts.append(f"소지금 {operation} 완료")
        message_parts.append(f"변경 금액: {amount:,} {currency_unit}")
        message_parts.append("")
        
        # 성공한 경우
        if successful:
            message_parts.append(f"성공: {len(successful)}명")
            for result in successful[:30]:  # 최대 10명까지만 표시
                char_name = result['character']
                old_money = result.get('old_money', 0)
                new_money = result.get('new_money', 0)
                change = result.get('change', 0)
                change_text = f"+{change:,}" if change >= 0 else f"{change:,}"
                message_parts.append(f"• {char_name}: {old_money:,} → {new_money:,}")
            
            if len(successful) > 10:
                message_parts.append(f"• ... 외 {len(successful) - 10}명")
            message_parts.append("")
        
        # 실패한 경우
        if failed:
            message_parts.append(f"❌ **실패: {len(failed)}명**")
            for result in failed[:5]:  # 최대 5명까지만 표시
                char_name = result['character']
                error = result.get('error', '알 수 없는 오류')
                message_parts.append(f"• {char_name}: {error}")
            
            if len(failed) > 5:
                message_parts.append(f"• ... 외 {len(failed) - 5}명")
        
        return "\n".join(message_parts)
    
    def get_help_text(self) -> str:
        """
        도움말 텍스트 반환
        
        Returns:
            str: 도움말 텍스트
        """
        return (
            "💰 **소지금 관리 명령어**\n"
            "캐릭터들의 소지금을 일괄 추가하거나 차감합니다.\n\n"
            "**사용법:**\n"
            "• `[소지금 추가/금액/캐릭터명]` - 특정 캐릭터 소지금 추가\n"
            "• `[소지금 차감/금액/캐릭터명]` - 특정 캐릭터 소지금 차감\n"
            "• `[소지금 추가/금액/캐릭터1,캐릭터2]` - 여러 캐릭터 동시 처리\n"
            "• `[소지금 차감/금액/전원]` - 전체 캐릭터 처리\n\n"
            "**참고:**\n"
            "• 공백 없이 `[소지금추가/금액/대상]`도 가능합니다\n"
            "• 배치 업데이트로 API 제한을 최소화합니다\n"
            "• 차감 시 소지금이 음수가 되지 않도록 보정됩니다"
        )


def is_money_admin_command(keywords: List[str]) -> bool:
    """
    소지금 관리 명령어 여부 확인
    
    Args:
        keywords: 키워드 리스트
        
    Returns:
        bool: 소지금 관리 명령어 여부
    """
    if not keywords:
        return False
    
    first_keyword = keywords[0].replace(" ", "").lower()
    return first_keyword in ['소지금추가', '소지금차감', '소지금 추가', '소지금 차감']
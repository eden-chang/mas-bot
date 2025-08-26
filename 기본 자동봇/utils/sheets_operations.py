"""
Google Sheets 작업 모듈
Google Sheets와 관련된 모든 작업을 통합 관리합니다.
"""

import os
import sys
import gspread
import pytz
import time
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Union, Tuple, Set
from gspread.exceptions import APIError
from difflib import SequenceMatcher

# 경로 설정 (VM 환경 대응)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    from config.settings import config
    from utils.error_handling import (
        safe_execute, SheetAccessError, UserNotFoundError, 
        SheetErrorHandler, ErrorContext
    )
    from utils.logging_config import logger, bot_logger
    from utils.cache_manager import cache_roster_data, get_roster_data
except ImportError:
    # VM 환경에서 임포트 실패 시 폴백
    import importlib.util
    
    # config.settings 로드
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'settings.py')
    spec = importlib.util.spec_from_file_location("settings", config_path)
    settings_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(settings_module)
    config = settings_module.config
    
    # 기본 로거 설정 (임포트 실패 시)
    import logging
    logger = logging.getLogger('sheets_operations')
    
    # 캐시 관련 폴백
    def cache_roster_data(data):
        return False
    
    def get_roster_data():
        return None


def normalize_text(text: str) -> str:
    """
    텍스트 정규화 - 매칭을 위해 텍스트를 정리
    """
    if not text:
        return ""
    
    # 1. HTML 태그 제거 (이미 되어있을 수도 있지만 재확인)
    text = re.sub(r'<[^>]+>', '', text)
    
    # 2. 연속된 공백을 단일 공백으로 변환
    text = re.sub(r'\s+', ' ', text)
    
    # 3. 앞뒤 공백 제거
    text = text.strip()
    
    # 4. 특수문자 통일 (전각 → 반각)
    text = text.replace('（', '(').replace('）', ')')
    text = text.replace('！', '!').replace('？', '?')
    text = text.replace('【', '[').replace('】', ']')
    
    return text



class SheetsManager:
    """Google Sheets 관리 클래스"""
    
    def __init__(self, sheet_name: str = None, credentials_path: str = None):
        """
        SheetsManager 초기화
        
        Args:
            sheet_name: 스프레드시트 이름
            credentials_path: 인증 파일 경로
        """
        self.sheet_name = sheet_name or config.SHEET_NAME
        self.credentials_path = credentials_path or config.get_credentials_path()
        self._spreadsheet = None
        self._worksheets_cache = {}
        
    @property
    def spreadsheet(self):
        """스프레드시트 객체 (지연 로딩)"""
        if self._spreadsheet is None:
            self._spreadsheet = self.connect_to_sheet()
        return self._spreadsheet
    
    def connect_to_sheet(self) -> gspread.Spreadsheet:
        """
        스프레드시트 연결 (기존 connect_to_sheet 함수 개선 버전)
        
        Returns:
            gspread.Spreadsheet: 연결된 스프레드시트 객체
            
        Raises:
            SheetAccessError: 연결 실패 시
        """
        def connection_operation():
            try:
                # Google API를 사용한 인증
                gc = gspread.service_account(filename=str(self.credentials_path))
                
                # 스프레드시트 열기
                spreadsheet = gc.open(self.sheet_name)
                logger.info(f"✅ 스프레드시트 '{self.sheet_name}' 연결 성공")
                return spreadsheet
                
            except FileNotFoundError:
                raise SheetAccessError(f"인증 파일을 찾을 수 없습니다: {self.credentials_path}")
            except gspread.exceptions.SpreadsheetNotFound:
                raise SheetAccessError(f"스프레드시트 '{self.sheet_name}'을 찾을 수 없습니다.")
            except Exception as e:
                raise SheetAccessError(f"스프레드시트 연결 실패: {str(e)}")
        
        with ErrorContext("스프레드시트 연결", sheet_name=self.sheet_name):
            result = safe_execute(
                operation_func=connection_operation,
                max_retries=config.MAX_RETRIES
            )
            
            if result.success:
                return result.result
            else:
                raise result.error or SheetAccessError("스프레드시트 연결 실패")
    
    def get_worksheet(self, worksheet_name: str, use_cache: bool = True) -> gspread.Worksheet:
        """
        워크시트 가져오기 (캐싱 지원)
        
        Args:
            worksheet_name: 워크시트 이름
            use_cache: 캐시 사용 여부
            
        Returns:
            gspread.Worksheet: 워크시트 객체
            
        Raises:
            SheetAccessError: 워크시트를 찾을 수 없을 때
        """
        if use_cache and worksheet_name in self._worksheets_cache:
            return self._worksheets_cache[worksheet_name]
        
        def get_operation():
            try:
                worksheet = self.spreadsheet.worksheet(worksheet_name)
                if use_cache:
                    self._worksheets_cache[worksheet_name] = worksheet
                return worksheet
            except gspread.exceptions.WorksheetNotFound:
                raise SheetErrorHandler.handle_worksheet_not_found(worksheet_name)
        
        with ErrorContext("워크시트 접근", worksheet=worksheet_name):
            result = safe_execute(get_operation)
            
            if result.success:
                return result.result
            else:
                raise result.error or SheetErrorHandler.handle_worksheet_not_found(worksheet_name)
    
    def get_worksheet_data(self, worksheet_name: str, use_cache: bool = False) -> List[Dict[str, Any]]:
        """
        워크시트 데이터 가져오기 (기존 get_worksheet_data_safe 개선 버전)
        
        Args:
            worksheet_name: 워크시트 이름
            use_cache: 캐시 사용 여부 (데이터는 기본적으로 캐시하지 않음)
            
        Returns:
            List[Dict]: 워크시트 데이터
        """
        def get_data_operation():
            worksheet = self.get_worksheet(worksheet_name)
            if worksheet.row_count <= 1:  # 헤더만 있거나 빈 시트
                return []
            return worksheet.get_all_records()
        
        with ErrorContext("워크시트 데이터 조회", worksheet=worksheet_name):
            result = safe_execute(get_data_operation, fallback_return=[])
            
            if result.success:
                bot_logger.log_sheet_operation("데이터 조회", worksheet_name, True)
                return result.result
            else:
                bot_logger.log_sheet_operation("데이터 조회", worksheet_name, False, str(result.error))
                return []
    
    def append_row(self, worksheet_name: str, values: List[Any]) -> bool:
        """
        워크시트에 행 추가
        
        Args:
            worksheet_name: 워크시트 이름
            values: 추가할 값들
            
        Returns:
            bool: 성공 여부
        """
        def append_operation():
            worksheet = self.get_worksheet(worksheet_name)
            worksheet.append_row(values)
            return True
        
        with ErrorContext("행 추가", worksheet=worksheet_name, values_count=len(values)):
            result = safe_execute(append_operation)
            
            success = result.success
            bot_logger.log_sheet_operation("행 추가", worksheet_name, success, 
                                         str(result.error) if not success else None)
            return success
    
    def update_cell(self, worksheet_name: str, row: int, col: int, value: Any) -> bool:
        """
        특정 셀 업데이트
        
        Args:
            worksheet_name: 워크시트 이름
            row: 행 번호 (1부터 시작)
            col: 열 번호 (1부터 시작)
            value: 업데이트할 값
            
        Returns:
            bool: 성공 여부
        """
        def update_operation():
            worksheet = self.get_worksheet(worksheet_name)
            worksheet.update_cell(row, col, value)
            return True
        
        with ErrorContext("셀 업데이트", worksheet=worksheet_name, row=row, col=col):
            result = safe_execute(update_operation)
            
            success = result.success
            bot_logger.log_sheet_operation("셀 업데이트", worksheet_name, success,
                                         str(result.error) if not success else None)
            return success
    
    def _get_roster_data_cached(self) -> List[Dict[str, Any]]:
        """
        명단 데이터 조회 (2시간 캐시 적용)
        
        Returns:
            List[Dict]: 명단 데이터
        """
        # 캐시에서 조회 시도
        cached_data = get_roster_data()
        
        if cached_data is not None:
            logger.debug("캐시에서 명단 데이터 로드")
            return cached_data
        
        # 캐시에 없으면 시트에서 로드
        logger.debug("시트에서 명단 데이터 로드 및 캐시 저장")
        roster_data = self.get_worksheet_data(config.get_worksheet_name('ROSTER'))
        
        # 캐시에 저장 (2시간 TTL)
        cache_roster_data(roster_data)
        
        return roster_data
    
    def find_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        사용자 ID로 사용자 정보 조회 (캐시 적용 - 기존 get_user_data_safe 개선 버전)
        
        Args:
            user_id: 사용자 ID
            
        Returns:
            Optional[Dict]: 사용자 정보 또는 None
        """
        roster_data = self._get_roster_data_cached()
        
        for row in roster_data:
            if str(row.get('아이디', '')).strip() == user_id:
                return row
        
        return None
    
    def user_exists(self, user_id: str) -> bool:
        """
        사용자 존재 여부 확인 (기존 user_id_check 개선 버전)
        
        Args:
            user_id: 사용자 ID
            
        Returns:
            bool: 사용자 존재 여부
        """
        return self.find_user_by_id(user_id) is not None
    
    def log_action(self, user_name: str, command: str, message: str, success: bool = True) -> bool:
        """
        로그 기록 (기존 log_action 개선 버전)
        
        Args:
            user_name: 사용자 이름
            command: 실행된 명령어
            message: 결과 메시지
            success: 성공 여부
            
        Returns:
            bool: 로그 기록 성공 여부
        """
        now = self.get_current_time()
        status = "성공" if success else "실패"
        
        # 로그 시트를 사용하지 않으므로 파일 로그만 기록
        log_message = f"📝 봇 액션 - {now} | {user_name} | {command} | {message} | {status}"
        if success:
            logger.info(log_message)
        else:
            logger.warning(log_message)
        
        return True
    
    @staticmethod
    def get_current_time() -> str:
        """
        현재 KST 기준 시간 반환
        
        Returns:
            str: 현재 시간 (YYYY-MM-DD HH:MM:SS 형식)
        """
        return datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
    
    def get_custom_commands(self) -> Dict[str, List[str]]:
        """
        커스텀 명령어와 문구들 조회
        
        Returns:
            Dict[str, List[str]]: {명령어: [문구들]} 형태의 딕셔너리
        """
        # 커스텀 시트를 사용하지 않으므로 빈 딕셔너리 반환
        return {}
        
        # custom_data = self.get_worksheet_data(config.get_worksheet_name('CUSTOM'))
        # commands = {}
        # 
        # for row in custom_data:
        #     command = str(row.get('명령어', '')).strip()
        #     phrase = str(row.get('문구', '')).strip()
        #     
        #     if command and phrase:
        #         if command not in commands:
        #             commands[command] = []
        #         commands[command].append(phrase)
        # 
        # return commands
    
    def get_help_items(self) -> List[Dict[str, str]]:
        """
        도움말 항목들 조회
        
        Returns:
            List[Dict]: [{'명령어': str, '설명': str}] 형태의 리스트
        """
        help_data = self.get_worksheet_data(config.get_worksheet_name('HELP'))
        help_items = []
        
        for row in help_data:
            command = str(row.get('명령어', '')).strip()
            description = str(row.get('설명', '')).strip()
            
            if command and description:
                help_items.append({'명령어': command, '설명': description})
        
        return help_items
    
    def get_fortune_phrases(self) -> List[str]:
        """
        운세 문구들 조회
        
        Returns:
            List[str]: 운세 문구 리스트
        """
        # 운세 시트를 사용하지 않으므로 빈 리스트 반환
        return []
        
        # fortune_data = self.get_worksheet_data(config.get_worksheet_name('FORTUNE'))
        # phrases = []
        # 
        # for row in fortune_data:
        #     phrase = str(row.get('문구', '')).strip()
        #     if phrase:
        #         phrases.append(phrase)
        # 
        # return phrases
    
    def _column_number_to_letter(self, col_num: int) -> str:
        """
        컬럼 번호를 알파벳으로 변환 (1 -> A, 2 -> B, ...)
        
        Args:
            col_num: 컬럼 번호 (1부터 시작)
            
        Returns:
            str: 컬럼 알파벳 (A, B, C, ..., AA, AB, ...)
        """
        result = ""
        while col_num > 0:
            col_num -= 1
            result = chr(col_num % 26 + ord('A')) + result
            col_num //= 26
        return result
    
    def _find_student_row_by_id(self, user_id: str) -> Optional[int]:
        """
        사용자 ID로 학생관리 시트에서 행 번호 찾기
        
        Args:
            user_id: 사용자 ID
            
        Returns:
            Optional[int]: 행 번호 (1부터 시작) 또는 None
        """
        try:
            worksheet = self.get_worksheet('학생관리')
            all_values = worksheet.get_all_values()
            
            # 헤더에서 '아이디' 컬럼 찾기
            if not all_values:
                return None
            
            headers = all_values[0]
            id_col = None
            for i, header in enumerate(headers):
                if header == '아이디':
                    id_col = i
                    break
            
            if id_col is None:
                return None
            
            # 사용자 ID가 있는 행 찾기
            for i, row in enumerate(all_values[1:], start=2):  # 2번째 행부터 시작
                if len(row) > id_col and str(row[id_col]).strip() == user_id:
                    return i
            
            return None
            
        except Exception as e:
            logger.error(f"학생 행 찾기 실패: {e}")
            return None
    
    # ==================== 기존 메서드들 ====================

    def clear_cache(self):
        """워크시트 캐시 초기화"""
        self._worksheets_cache.clear()
        logger.debug("워크시트 캐시가 초기화되었습니다.")
    
    def invalidate_roster_cache(self) -> bool:
        """
        명단 캐시 무효화
        
        Returns:
            bool: 무효화 성공 여부
        """
        try:
            from utils.cache_manager import invalidate_roster_data
            return invalidate_roster_data()
        except ImportError:
            return False
    
    def get_roster_cache_status(self) -> Dict[str, Any]:
        """
        명단 캐시 상태 정보 반환
        
        Returns:
            Dict: 캐시 상태 정보
        """
        try:
            from utils.cache_manager import get_roster_cache_info
            return get_roster_cache_info()
        except ImportError:
            return {'cached': False, 'message': '캐시 시스템을 사용할 수 없습니다'}
    
    def validate_sheet_structure(self) -> Dict[str, Any]:
        """
        시트 구조 검증
        
        Returns:
            Dict: 검증 결과
        """
        validation_results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'worksheets_found': []
        }
        
        try:
            # 모든 워크시트 이름 가져오기
            all_worksheets = [ws.title for ws in self.spreadsheet.worksheets()]
            validation_results['worksheets_found'] = all_worksheets
            
            # 필수 워크시트 확인
            required_worksheets = list(config.WORKSHEET_NAMES.values())
            for required in required_worksheets:
                if required not in all_worksheets:
                    validation_results['errors'].append(f"필수 워크시트 '{required}'가 없습니다.")
                    validation_results['valid'] = False
            
            # 각 워크시트 구조 확인
            self._validate_roster_structure(validation_results)
            # self._validate_custom_structure(validation_results)  # 커스텀 시트를 사용하지 않으므로 주석 처리
            self._validate_help_structure(validation_results)
            # self._validate_fortune_structure(validation_results)
            
        except Exception as e:
            validation_results['errors'].append(f"시트 구조 검증 중 오류: {str(e)}")
            validation_results['valid'] = False
        
        return validation_results
    
    def _validate_roster_structure(self, results: Dict):
        """명단 시트 구조 검증 (동적 키 검색 적용)"""
        try:
            worksheet = self.get_worksheet(config.get_worksheet_name('ROSTER'))
            if worksheet.row_count > 0:
                headers = worksheet.row_values(1)
                
                # 필수 헤더 확인
                required_headers = ['아이디', '이름']
                for header in required_headers:
                    if header not in headers:
                        results['errors'].append(f"'명단' 시트에 '{header}' 헤더가 없습니다.")
                        results['valid'] = False
                    
        except Exception as e:
            results['errors'].append(f"명단 시트 검증 실패: {str(e)}")
            results['valid'] = False
    
    # def _validate_custom_structure(self, results: Dict):
    #     """커스텀 시트 구조 검증"""
    #     try:
    #         worksheet = self.get_worksheet(config.get_worksheet_name('CUSTOM'))
    #         if worksheet.row_count > 0:
    #             headers = worksheet.row_values(1)
    #             required_headers = ['명령어', '문구']
    #             for header in required_headers:
    #                 if header not in headers:
    #                     results['errors'].append(f"'커스텀' 시트에 '{header}' 헤더가 없습니다.")
    #                     results['valid'] = False
    #     except Exception as e:
    #         results['errors'].append(f"커스텀 시트 검증 실패: {str(e)}")
    #         results['valid'] = False
    
    def _validate_help_structure(self, results: Dict):
        """도움말 시트 구조 검증"""
        try:
            worksheet = self.get_worksheet(config.get_worksheet_name('HELP'))
            if worksheet.row_count > 0:
                headers = worksheet.row_values(1)
                required_headers = ['명령어', '설명']
                for header in required_headers:
                    if header not in headers:
                        results['errors'].append(f"'도움말' 시트에 '{header}' 헤더가 없습니다.")
                        results['valid'] = False
        except Exception as e:
            results['errors'].append(f"도움말 시트 검증 실패: {str(e)}")
            results['valid'] = False
    
    # def _validate_fortune_structure(self, results: Dict):
    #     """운세 시트 구조 검증"""
    #     try:
    #         worksheet = self.get_worksheet(config.get_worksheet_name('FORTUNE'))
    #         if worksheet.row_count > 0:
    #             headers = worksheet.row_values(1)
    #             if '문구' not in headers:
    #                 results['errors'].append("'운세' 시트에 '문구' 헤더가 없습니다.")
    #                 results['valid'] = False
    #     except Exception as e:
    #         results['errors'].append(f"운세 시트 검증 실패: {str(e)}")
    #         results['valid'] = False
    

# 전역 인스턴스 (기존 코드와의 호환성을 위해)
_global_sheets_manager = None


def get_sheets_manager() -> SheetsManager:
    """전역 SheetsManager 인스턴스 반환"""
    global _global_sheets_manager
    if _global_sheets_manager is None:
        _global_sheets_manager = SheetsManager()
    return _global_sheets_manager


# 기존 코드와의 호환성을 위한 함수들
def connect_to_sheet(sheet_name: str = None, credentials_file: str = None):
    """기존 connect_to_sheet 함수 호환성 유지"""
    manager = SheetsManager(sheet_name, credentials_file)
    return manager.spreadsheet


def user_id_check(sheet, user_id: str) -> bool:
    """기존 user_id_check 함수 호환성 유지"""
    try:
        # sheet가 SheetsManager 인스턴스인 경우
        if isinstance(sheet, SheetsManager):
            return sheet.user_exists(user_id)
        
        # sheet가 gspread.Spreadsheet 인스턴스인 경우
        manager = SheetsManager()
        manager._spreadsheet = sheet
        return manager.user_exists(user_id)
    except Exception:
        return False


def get_user_data_safe(sheet, user_id: str) -> Optional[Dict[str, Any]]:
    """기존 get_user_data_safe 함수 호환성 유지"""
    try:
        # sheet가 SheetsManager 인스턴스인 경우
        if isinstance(sheet, SheetsManager):
            return sheet.find_user_by_id(user_id)
        
        # sheet가 gspread.Spreadsheet 인스턴스인 경우
        manager = SheetsManager()
        manager._spreadsheet = sheet
        return manager.find_user_by_id(user_id)
    except Exception:
        return None


def get_worksheet_data_safe(sheet, worksheet_name: str) -> List[Dict[str, Any]]:
    """기존 get_worksheet_data_safe 함수 호환성 유지"""
    try:
        # sheet가 SheetsManager 인스턴스인 경우
        if isinstance(sheet, SheetsManager):
            return sheet.get_worksheet_data(worksheet_name)
        
        # sheet가 gspread.Spreadsheet 인스턴스인 경우
        manager = SheetsManager()
        manager._spreadsheet = sheet
        return manager.get_worksheet_data(worksheet_name)
    except Exception:
        return []


def log_action(sheet, user_name: str, command: str, message: str, success: bool = True) -> bool:
    """기존 log_action 함수 호환성 유지"""
    try:
        # sheet가 SheetsManager 인스턴스인 경우
        if isinstance(sheet, SheetsManager):
            return sheet.log_action(user_name, command, message, success)
        
        # sheet가 gspread.Spreadsheet 인스턴스인 경우
        manager = SheetsManager()
        manager._spreadsheet = sheet
        return manager.log_action(user_name, command, message, success)
    except Exception:
        # 로그 실패 시 파일 로그에라도 기록
        logger.warning(f"시트 로그 실패: {user_name} | {command} | {message} | {'성공' if success else '실패'}")
        return False


def find_worksheet_safe(sheet, worksheet_name: str):
    """기존 find_worksheet_safe 함수 호환성 유지"""
    try:
        # sheet가 SheetsManager 인스턴스인 경우
        if isinstance(sheet, SheetsManager):
            return sheet.get_worksheet(worksheet_name)
        
        # sheet가 gspread.Spreadsheet 인스턴스인 경우
        manager = SheetsManager()
        manager._spreadsheet = sheet
        return manager.get_worksheet(worksheet_name)
    except Exception:
        return None
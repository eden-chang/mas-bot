"""
설정 검증 모듈
애플리케이션 설정과 환경을 검증합니다.
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

# 경로 설정 (VM 환경 대응)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    from config.settings import Config
except ImportError:
    # VM 환경에서 임포트 실패 시 폴백
    import importlib.util
    settings_path = os.path.join(os.path.dirname(__file__), 'settings.py')
    spec = importlib.util.spec_from_file_location("settings", settings_path)
    settings_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(settings_module)
    Config = settings_module.Config


@dataclass
class ValidationResult:
    """검증 결과를 담는 데이터 클래스"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    
    def add_error(self, error: str) -> None:
        """에러 추가"""
        self.errors.append(error)
        self.is_valid = False
    
    def add_warning(self, warning: str) -> None:
        """경고 추가"""
        self.warnings.append(warning)
    
    def get_summary(self) -> str:
        """검증 결과 요약 반환"""
        summary = []
        
        if self.is_valid:
            summary.append("✅ 모든 설정이 유효합니다.")
        else:
            summary.append("❌ 설정 검증 실패")
            
        if self.errors:
            summary.append("\n🚨 오류:")
            for error in self.errors:
                summary.append(f"  - {error}")
                
        if self.warnings:
            summary.append("\n⚠️ 경고:")
            for warning in self.warnings:
                summary.append(f"  - {warning}")
                
        return "\n".join(summary)


class ConfigValidator:
    """설정 검증 클래스"""
    
    @staticmethod
    def validate_environment() -> ValidationResult:
        """
        환경 변수와 기본 설정을 검증합니다.
        
        Returns:
            ValidationResult: 검증 결과
        """
        result = ValidationResult(is_valid=True, errors=[], warnings=[])
        
        # 필수 환경 변수 검증
        required_env_vars = [
            ('MASTODON_CLIENT_ID', Config.MASTODON_CLIENT_ID),
            ('MASTODON_CLIENT_SECRET', Config.MASTODON_CLIENT_SECRET),
            ('MASTODON_ACCESS_TOKEN', Config.MASTODON_ACCESS_TOKEN),
        ]
        
        for var_name, var_value in required_env_vars:
            if not var_value or var_value.strip() == '':
                result.add_error(f"필수 환경 변수 '{var_name}'가 설정되지 않았습니다.")
        
        # Mastodon API URL 검증
        if not Config.MASTODON_API_BASE_URL.startswith(('http://', 'https://')):
            result.add_error("MASTODON_API_BASE_URL은 http:// 또는 https://로 시작해야 합니다.")
        
        # Google 인증 파일 검증
        cred_path = Config.get_credentials_path()
        if not cred_path.exists():
            result.add_error(f"Google 인증 파일을 찾을 수 없습니다: {cred_path}")
        elif not cred_path.is_file():
            result.add_error(f"Google 인증 파일이 올바른 파일이 아닙니다: {cred_path}")
        
        # 숫자 설정값 검증
        numeric_configs = [
            ('MAX_RETRIES', Config.MAX_RETRIES, 1, 10),
            ('BASE_WAIT_TIME', Config.BASE_WAIT_TIME, 1, 60),
            ('MAX_DICE_COUNT', Config.MAX_DICE_COUNT, 1, 100),
            ('MAX_DICE_SIDES', Config.MAX_DICE_SIDES, 2, 10000),
            ('MAX_CARD_COUNT', Config.MAX_CARD_COUNT, 1, 52),
            ('CACHE_TTL', Config.CACHE_TTL, 0, 3600),
            ('LOG_MAX_BYTES', Config.LOG_MAX_BYTES, 1024, 104857600),  # 1KB ~ 100MB
            ('LOG_BACKUP_COUNT', Config.LOG_BACKUP_COUNT, 1, 20),
        ]
        
        for name, value, min_val, max_val in numeric_configs:
            if not isinstance(value, int) or value < min_val or value > max_val:
                result.add_error(f"{name}은 {min_val}과 {max_val} 사이의 정수여야 합니다. 현재값: {value}")
        
        # 로그 레벨 검증
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if Config.LOG_LEVEL.upper() not in valid_log_levels:
            result.add_error(f"LOG_LEVEL은 다음 중 하나여야 합니다: {', '.join(valid_log_levels)}")
        
        # 시트 이름 검증
        if not Config.SHEET_NAME or Config.SHEET_NAME.strip() == '':
            result.add_error("SHEET_NAME이 설정되지 않았습니다.")
        
        # 관리자 ID 검증
        if not Config.SYSTEM_ADMIN_ID or Config.SYSTEM_ADMIN_ID.strip() == '':
            result.add_warning("SYSTEM_ADMIN_ID가 설정되지 않았습니다. 오류 알림을 받을 수 없습니다.")
        
        # 로그 파일 경로 검증
        log_dir = Path(Config.LOG_FILE_PATH).parent
        if not log_dir.exists():
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
                result.add_warning(f"로그 디렉토리를 생성했습니다: {log_dir}")
            except PermissionError:
                result.add_error(f"로그 디렉토리를 생성할 권한이 없습니다: {log_dir}")
        
        return result
    
    @staticmethod
    def validate_sheet_structure(sheet) -> ValidationResult:
        """
        Google Sheets 구조를 검증합니다.
        
        Args:
            sheet: Google Spreadsheet 객체
            
        Returns:
            ValidationResult: 검증 결과
        """
        result = ValidationResult(is_valid=True, errors=[], warnings=[])
        
        try:
            # 필수 워크시트 존재 확인
            worksheet_titles = [ws.title for ws in sheet.worksheets()]
            required_worksheets = list(Config.WORKSHEET_NAMES.values())
            
            for required_sheet in required_worksheets:
                if required_sheet not in worksheet_titles:
                    result.add_error(f"필수 워크시트 '{required_sheet}'가 없습니다.")
            
            # 각 워크시트별 구조 검증
            ConfigValidator._validate_roster_sheet(sheet, result)
            ConfigValidator._validate_help_sheet(sheet, result)
            
        except Exception as e:
            result.add_error(f"시트 구조 검증 중 오류 발생: {str(e)}")
        
        return result
    
    @staticmethod
    def _validate_roster_sheet(sheet, result: ValidationResult) -> None:
        """명단 시트 검증"""
        try:
            roster_sheet = sheet.worksheet(Config.get_worksheet_name('ROSTER'))
            headers = roster_sheet.row_values(1) if roster_sheet.row_count > 0 else []
            
            required_headers = ['아이디', '이름']
            for header in required_headers:
                if header not in headers:
                    result.add_error(f"'명단' 시트에 '{header}' 헤더가 없습니다.")
                    
        except Exception as e:
            result.add_error(f"'명단' 시트 검증 실패: {str(e)}")
    
    # @staticmethod
    # def _validate_custom_sheet(sheet, result: ValidationResult) -> None:
    #     """커스텀 시트 검증"""
    #     try:
    #         custom_sheet = sheet.worksheet(Config.get_worksheet_name('CUSTOM'))
    #         headers = custom_sheet.row_values(1) if custom_sheet.row_count > 0 else []
            
    #         required_headers = ['명령어', '문구']
    #         for header in required_headers:
    #             if header not in headers:
    #                 result.add_error(f"'커스텀' 시트에 '{header}' 헤더가 없습니다.")
            
    #         # 데이터 유효성 검증
    #         if custom_sheet.row_count > 1:
    #             all_records = custom_sheet.get_all_records()
    #             valid_commands = 0
                
    #             for record in all_records:
    #                 command = str(record.get('명령어', '')).strip()
    #                 phrase = str(record.get('문구', '')).strip()
                    
    #                 if command and phrase:
    #                     valid_commands += 1
                        
    #                     # 시스템 키워드와 중복 확인
    #                     if Config.is_system_keyword(command):
    #                         result.add_warning(f"커스텀 명령어 '{command}'가 시스템 키워드와 중복됩니다.")
                
    #             if valid_commands == 0:
    #                 result.add_warning("'커스텀' 시트에 유효한 명령어가 없습니다.")
                    
    #     except Exception as e:
    #         result.add_error(f"'커스텀' 시트 검증 실패: {str(e)}")
    
    @staticmethod
    def _validate_help_sheet(sheet, result: ValidationResult) -> None:
        """도움말 시트 검증"""
        try:
            help_sheet = sheet.worksheet(Config.get_worksheet_name('HELP'))
            headers = help_sheet.row_values(1) if help_sheet.row_count > 0 else []
            
            required_headers = ['명령어', '설명']
            for header in required_headers:
                if header not in headers:
                    result.add_error(f"'도움말' 시트에 '{header}' 헤더가 없습니다.")
            
            # 데이터 유효성 검증
            if help_sheet.row_count > 1:
                all_records = help_sheet.get_all_records()
                valid_helps = sum(1 for record in all_records 
                                if str(record.get('명령어', '')).strip() and 
                                   str(record.get('설명', '')).strip())
                
                if valid_helps == 0:
                    result.add_warning("'도움말' 시트에 유효한 도움말이 없습니다.")
                    
        except Exception as e:
            result.add_error(f"'도움말' 시트 검증 실패: {str(e)}")
    
    # @staticmethod
    # def _validate_fortune_sheet(sheet, result: ValidationResult) -> None:
    #     """운세 시트 검증"""
    #     try:
    #         fortune_sheet = sheet.worksheet(Config.get_worksheet_name('FORTUNE'))
    #         headers = fortune_sheet.row_values(1) if fortune_sheet.row_count > 0 else []
            
    #         required_headers = ['문구']
    #         for header in required_headers:
    #             if header not in headers:
    #                 result.add_error(f"'운세' 시트에 '{header}' 헤더가 없습니다.")
            
    #         # 데이터 유효성 검증
    #         if fortune_sheet.row_count > 1:
    #             all_records = fortune_sheet.get_all_records()
    #             valid_fortunes = sum(1 for record in all_records 
    #                                if str(record.get('문구', '')).strip())
                
    #             if valid_fortunes == 0:
    #                 result.add_error("'운세' 시트에 유효한 운세가 없습니다.")
    #         else:
    #             result.add_error("'운세' 시트에 데이터가 없습니다.")
                    
    #     except Exception as e:
    #         result.add_error(f"'운세' 시트 검증 실패: {str(e)}")
    
    @staticmethod
    def validate_all(sheet=None) -> ValidationResult:
        """
        모든 설정을 종합적으로 검증합니다.
        
        Args:
            sheet: Google Spreadsheet 객체 (선택사항)
            
        Returns:
            ValidationResult: 종합 검증 결과
        """
        # 환경 설정 검증
        env_result = ConfigValidator.validate_environment()
        
        # 시트가 제공된 경우 시트 구조도 검증
        if sheet is not None:
            sheet_result = ConfigValidator.validate_sheet_structure(sheet)
            
            # 결과 합성
            combined_result = ValidationResult(
                is_valid=env_result.is_valid and sheet_result.is_valid,
                errors=env_result.errors + sheet_result.errors,
                warnings=env_result.warnings + sheet_result.warnings
            )
        else:
            combined_result = env_result
            combined_result.add_warning("시트 구조 검증을 수행하지 않았습니다.")
        
        return combined_result


def validate_startup_config(sheet=None) -> Tuple[bool, str]:
    """
    시작시 설정 검증을 수행하고 결과를 반환합니다.
    
    Args:
        sheet: Google Spreadsheet 객체 (선택사항)
        
    Returns:
        Tuple[bool, str]: (검증 성공 여부, 검증 결과 메시지)
    """
    result = ConfigValidator.validate_all(sheet)
    return result.is_valid, result.get_summary()
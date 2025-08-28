"""
마스토돈 예약 봇 설정 관리 모듈
환경 변수를 로드하고 검증하여 애플리케이션 전체에서 사용할 수 있도록 관리합니다.
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
import pytz


class Config:
    """
    마스토돈 예약 봇 설정 클래스
    
    환경 변수를 로드하고 검증하여 애플리케이션 전체에서 사용할 수 있는
    중앙집중식 설정 관리를 제공합니다.
    """
    
    def __init__(self):
        """Config 클래스 초기화"""
        # 프로젝트 루트 경로 설정 (main.py가 있는 위치)
        self.PROJECT_ROOT = Path(__file__).parent.parent.absolute()
        
        # .env 파일 로드
        self._load_environment()
        
        # 설정값 초기화
        self._initialize_settings()
        
        # 디렉토리 생성
        self._ensure_directories()
    
    def _load_environment(self) -> None:
        """환경 변수 파일(.env) 로드"""
        env_path = self.PROJECT_ROOT / ".env"
        
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
            print(f"환경 변수 파일 로드: {env_path}")
        else:
            print(f"경고: 환경 변수 파일을 찾을 수 없습니다: {env_path}")
            print("기본값으로 진행하지만 일부 기능이 제한될 수 있습니다.")
    
    def _initialize_settings(self) -> None:
        """모든 설정값 초기화"""
        # === 마스토돈 API 설정 ===
        self.MASTODON_INSTANCE_URL = self._get_env_str(
            'MASTODON_INSTANCE_URL',
            default='https://koltsevaya.xyz',
            description="마스토돈 인스턴스 URL"
        )
        
        # 동적 마스토돈 계정 설정
        self.MASTODON_ACCOUNTS = self._load_mastodon_accounts()
        
        # 기본 계정 설정 (첫 번째 계정)
        self.DEFAULT_ACCOUNT = self._get_default_account()
        
        # === Google Sheets 설정 ===
        self.GOOGLE_SHEETS_ID = self._get_env_str(
            'GOOGLE_SHEETS_ID',
            required=True,
            description="Google Sheets 문서 ID"
        )
        
        self.GOOGLE_SHEETS_TAB = self._get_env_str(
            'GOOGLE_SHEETS_TAB',
            default='관리',
            description="Google Sheets 탭 이름"
        )
        
        # === 봇 동작 설정 ===
        self.SYNC_INTERVAL_MINUTES = self._get_env_int(
            'SYNC_INTERVAL_MINUTES',
            default=20,
            min_value=1,
            max_value=60,
            description="시트 동기화 간격 (분)"
        )
        
        self.MAX_ROWS_PER_REQUEST = self._get_env_int(
            'MAX_ROWS_PER_REQUEST',
            default=100,
            min_value=10,
            max_value=1000,
            description="한 번에 조회할 최대 행 수"
        )
        
        # === 시간대 설정 ===
        timezone_str = self._get_env_str(
            'TIMEZONE',
            default='Asia/Seoul',
            description="봇 작업 시간대"
        )
        
        try:
            self.TIMEZONE = pytz.timezone(timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            print(f"경고: 알 수 없는 시간대: {timezone_str}, 기본값(Asia/Seoul) 사용")
            self.TIMEZONE = pytz.timezone('Asia/Seoul')
        
        # === 로깅 설정 ===
        self.LOG_LEVEL = self._get_env_str(
            'LOG_LEVEL',
            default='INFO',
            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
            description="로그 레벨"
        )
        
        # === 파일 경로 설정 ===
        self.CREDENTIALS_PATH = self.PROJECT_ROOT / "credentials.json"
        self.CACHE_DIR = self.PROJECT_ROOT / "data"
        self.CACHE_FILE = self.CACHE_DIR / "cache.json"
        self.BACKUP_DIR = self.CACHE_DIR / "backup"
        self.LOG_DIR = self.PROJECT_ROOT / "logs"
        
        # === 고급 설정 ===
        self.RETRY_ATTEMPTS = self._get_env_int(
            'RETRY_ATTEMPTS',
            default=3,
            min_value=1,
            max_value=10,
            description="API 요청 재시도 횟수"
        )
        
        self.RETRY_DELAY_SECONDS = self._get_env_int(
            'RETRY_DELAY_SECONDS',
            default=5,
            min_value=1,
            max_value=60,
            description="재시도 간격 (초)"
        )
        
        self.CACHE_EXPIRY_HOURS = self._get_env_int(
            'CACHE_EXPIRY_HOURS',
            default=24,
            min_value=1,
            max_value=168,  # 7일
            description="캐시 만료 시간 (시간)"
        )
        
        # === 알림 설정 ===
        self.NOTIFICATION_ENABLED = self._get_env_bool(
            'NOTIFICATION_ENABLED',
            default=True,
            description="시스템 알림 활성화 여부"
        )
        
        self.ERROR_NOTIFICATION_ENABLED = self._get_env_bool(
            'ERROR_NOTIFICATION_ENABLED',
            default=True,
            description="오류 알림 활성화 여부"
        )
        
        # === 보안 설정 ===
        self.RATE_LIMIT_REQUESTS_PER_HOUR = self._get_env_int(
            'RATE_LIMIT_REQUESTS_PER_HOUR',
            default=100,
            min_value=10,
            max_value=1000,
            description="시간당 최대 API 요청 수"
        )
    
    def _get_env_str(self, key: str, default: Optional[str] = None, 
                     required: bool = False, choices: Optional[list] = None,
                     description: str = "") -> str:
        """문자열 환경 변수 조회"""
        value = os.getenv(key, default)
        
        if required and not value:
            raise ValueError(f"필수 환경 변수가 설정되지 않았습니다: {key} ({description})")
        
        if choices and value not in choices:
            raise ValueError(f"환경 변수 {key}의 값이 유효하지 않습니다. 가능한 값: {choices}")
        
        return value or ""
    
    def _load_mastodon_accounts(self) -> Dict[str, Dict[str, str]]:
        """
        환경 변수에서 마스토돈 계정들을 동적으로 로드
        
        MASTODON_ACCOUNTS 환경 변수에서 계정 이름들을 읽어오고,
        각 계정별로 ACCESS_TOKEN을 조회합니다.
        
        예시 설정:
        MASTODON_ACCOUNTS=notice,company,announcement
        NOTICE_ACCESS_TOKEN=abc123
        COMPANY_ACCESS_TOKEN=def456
        ANNOUNCEMENT_ACCESS_TOKEN=ghi789
        """
        # 계정 목록을 환경 변수에서 읽기
        accounts_str = self._get_env_str(
            'MASTODON_ACCOUNTS', 
            default='notice,subway,story,whisper,station,alexey',  # 기본값 (하위 호환성)
            description="마스토돈 계정 이름들 (콤마로 구분)"
        )
        
        # 계정 이름들을 파싱
        account_names = [name.strip().upper() for name in accounts_str.split(',') if name.strip()]
        
        if not account_names:
            raise ValueError("MASTODON_ACCOUNTS가 비어있거나 유효하지 않습니다.")
        
        # 각 계정별로 ACCESS_TOKEN 로드
        accounts = {}
        for account_name in account_names:
            token_key = f"{account_name}_ACCESS_TOKEN"
            access_token = self._get_env_str(
                token_key,
                required=True,
                description=f"{account_name} 계정 액세스 토큰"
            )
            
            accounts[account_name] = {
                'access_token': access_token
            }
        
        return accounts
    
    def _get_default_account(self) -> str:
        """기본 계정 반환 (첫 번째 계정 또는 명시적 설정)"""
        # 명시적으로 설정된 기본 계정이 있는지 확인
        default_account = self._get_env_str(
            'DEFAULT_MASTODON_ACCOUNT',
            description="기본 마스토돈 계정 이름"
        )
        
        if default_account:
            default_account = default_account.upper()
            if default_account in self.MASTODON_ACCOUNTS:
                return default_account
            else:
                print(f"경고: 설정된 기본 계정 '{default_account}'이 존재하지 않습니다. 첫 번째 계정을 사용합니다.")
        
        # 첫 번째 계정을 기본값으로 사용
        if self.MASTODON_ACCOUNTS:
            return list(self.MASTODON_ACCOUNTS.keys())[0]
        
        raise ValueError("설정된 마스토돈 계정이 없습니다.")
    
    def get_account_list(self) -> List[str]:
        """사용 가능한 계정 목록 반환"""
        return list(self.MASTODON_ACCOUNTS.keys())
    
    def is_valid_account(self, account_name: str) -> bool:
        """계정 이름이 유효한지 확인 (대소문자 구분 안함)"""
        return account_name.upper() in self.MASTODON_ACCOUNTS
    
    def get_normalized_account_name(self, account_name: str) -> Optional[str]:
        """
        계정 이름을 정규화하여 실제 사용되는 대문자 형태로 반환
        시트에서 'notice', 'Notice', 'NOTICE' 등으로 써도 'NOTICE'로 반환
        """
        normalized = account_name.upper()
        if normalized in self.MASTODON_ACCOUNTS:
            return normalized
        return None
    
    def _get_env_int(self, key: str, default: int = 0, 
                     min_value: Optional[int] = None, max_value: Optional[int] = None,
                     description: str = "") -> int:
        """정수 환경 변수 조회"""
        value_str = os.getenv(key)
        
        if value_str is None:
            return default
        
        try:
            value = int(value_str)
        except ValueError:
            print(f"경고: 환경 변수 {key}의 값이 정수가 아닙니다: {value_str}, 기본값 {default} 사용")
            return default
        
        if min_value is not None and value < min_value:
            print(f"경고: 환경 변수 {key}의 값이 최소값보다 작습니다: {value} < {min_value}, 기본값 {default} 사용")
            return default
        
        if max_value is not None and value > max_value:
            print(f"경고: 환경 변수 {key}의 값이 최대값보다 큽니다: {value} > {max_value}, 기본값 {default} 사용")
            return default
        
        return value
    
    def _get_env_bool(self, key: str, default: bool = False, description: str = "") -> bool:
        """불린 환경 변수 조회"""
        value_str = os.getenv(key)
        
        if value_str is None:
            return default
        
        # 참값으로 인정할 문자열들
        true_values = {'true', '1', 'yes', 'on', 'enabled'}
        return value_str.lower().strip() in true_values
    
    def _ensure_directories(self) -> None:
        """필요한 디렉토리들을 생성"""
        directories = [
            self.CACHE_DIR,
            self.BACKUP_DIR,
            self.LOG_DIR
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def get_credentials_path(self) -> Path:
        """Google 인증 파일 경로 반환"""
        return self.CREDENTIALS_PATH
    
    def get_cache_file_path(self) -> Path:
        """캐시 파일 경로 반환"""
        return self.CACHE_FILE
    
    def get_backup_dir_path(self) -> Path:
        """백업 디렉토리 경로 반환"""
        return self.BACKUP_DIR
    
    def get_log_dir_path(self) -> Path:
        """로그 디렉토리 경로 반환"""
        return self.LOG_DIR
    
    def validate_config(self) -> tuple[bool, list[str]]:
        """설정 검증"""
        errors = []
        
        # 필수 파일 존재 확인
        if not self.CREDENTIALS_PATH.exists():
            errors.append(f"Google 인증 파일을 찾을 수 없습니다: {self.CREDENTIALS_PATH}")
        
        # URL 형식 검증
        if not self.MASTODON_INSTANCE_URL.startswith(('http://', 'https://')):
            errors.append("MASTODON_INSTANCE_URL은 http:// 또는 https://로 시작해야 합니다")
        
        # 시간대 검증
        try:
            pytz.timezone(str(self.TIMEZONE))
        except (pytz.exceptions.UnknownTimeZoneError, AttributeError):
            errors.append(f"유효하지 않은 시간대입니다: {self.TIMEZONE}")
        
        # Google Sheets ID 형식 검증 (기본적인 길이 체크)
        if len(self.GOOGLE_SHEETS_ID) < 10:
            errors.append("GOOGLE_SHEETS_ID가 너무 짧습니다")
        
        # 마스토돈 계정 설정 검증
        for account_name, account_config in self.MASTODON_ACCOUNTS.items():
            for key, value in account_config.items():
                if not value or len(str(value).strip()) == 0:
                    errors.append(f"{account_name} 계정의 {key}가 설정되지 않았습니다")
        
        return len(errors) == 0, errors
    
    def print_config_summary(self) -> None:
        """설정 요약 출력"""
        print("\n" + "=" * 60)
        print("📋 마스토돈 예약 봇 설정 요약")
        print("=" * 60)
        
        print(f"🌐 마스토돈 인스턴스: {self.MASTODON_INSTANCE_URL}")
        print(f"📊 Google Sheets ID: {self.GOOGLE_SHEETS_ID[:20]}...")
        print(f"📝 시트 탭 이름: {self.GOOGLE_SHEETS_TAB}")
        print(f"⏰ 동기화 간격: {self.SYNC_INTERVAL_MINUTES}분")
        print(f"📏 최대 조회 행수: {self.MAX_ROWS_PER_REQUEST}행")
        print(f"🌍 시간대: {self.TIMEZONE}")
        print(f"📜 로그 레벨: {self.LOG_LEVEL}")
        
        print(f"\n👥 마스토돈 계정:")
        for account_name in self.MASTODON_ACCOUNTS.keys():
            print(f"   - {account_name}")
        
        print(f"\n📁 파일 경로:")
        print(f"   프로젝트 루트: {self.PROJECT_ROOT}")
        print(f"   인증 파일: {self.CREDENTIALS_PATH}")
        print(f"   캐시 파일: {self.CACHE_FILE}")
        print(f"   로그 디렉토리: {self.LOG_DIR}")
        
        print(f"\n🔧 고급 설정:")
        print(f"   재시도 횟수: {self.RETRY_ATTEMPTS}회")
        print(f"   재시도 간격: {self.RETRY_DELAY_SECONDS}초")
        print(f"   캐시 만료: {self.CACHE_EXPIRY_HOURS}시간")
        print(f"   시간당 API 제한: {self.RATE_LIMIT_REQUESTS_PER_HOUR}회")
        
        print("=" * 60 + "\n")
    
    def get_config_dict(self) -> Dict[str, Any]:
        """설정을 딕셔너리로 반환 (디버깅/로깅용)"""
        return {
            'mastodon_instance': self.MASTODON_INSTANCE_URL,
            'sheets_id': self.GOOGLE_SHEETS_ID[:20] + "...",  # 보안상 일부만
            'sheets_tab': self.GOOGLE_SHEETS_TAB,
            'sync_interval': self.SYNC_INTERVAL_MINUTES,
            'max_rows': self.MAX_ROWS_PER_REQUEST,
            'timezone': str(self.TIMEZONE),
            'log_level': self.LOG_LEVEL,
            'retry_attempts': self.RETRY_ATTEMPTS,
            'retry_delay': self.RETRY_DELAY_SECONDS,
            'cache_expiry': self.CACHE_EXPIRY_HOURS,
            'rate_limit': self.RATE_LIMIT_REQUESTS_PER_HOUR,
            'notifications_enabled': self.NOTIFICATION_ENABLED,
            'error_notifications_enabled': self.ERROR_NOTIFICATION_ENABLED
        }


# 전역 설정 인스턴스
config = Config()


def get_config() -> Config:
    """전역 설정 인스턴스 반환"""
    return config


def reload_config() -> Config:
    """설정 다시 로드 (런타임 중 .env 파일 변경 시)"""
    global config
    config = Config()
    return config


# 설정 검증 함수 (모듈 레벨)
def validate_startup_config() -> tuple[bool, str]:
    """
    시작시 설정 검증을 수행하고 결과를 반환합니다.
    
    Returns:
        tuple[bool, str]: (검증 성공 여부, 검증 결과 메시지)
    """
    is_valid, errors = config.validate_config()
    
    if is_valid:
        summary = "✅ 모든 설정이 유효합니다."
    else:
        summary = "❌ 설정 검증 실패:\n" + "\n".join([f"  - {error}" for error in errors])
    
    return is_valid, summary


if __name__ == "__main__":
    """설정 모듈 직접 실행 시 검증 및 요약 출력"""
    try:
        print("🔧 마스토돈 예약 봇 설정 검증 중...")
        
        # 설정 검증
        is_valid, message = validate_startup_config()
        print(message)
        
        if is_valid:
            # 설정 요약 출력
            config.print_config_summary()
            print("🎉 설정이 정상적으로 로드되었습니다!")
        else:
            print("\n💡 .env 파일을 확인하고 필요한 값들을 설정해주세요.")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ 설정 로드 실패: {e}")
        sys.exit(1)
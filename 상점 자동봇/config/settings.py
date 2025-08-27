"""
설정 관리 모듈
환경 변수를 로드하고 애플리케이션 전반의 설정을 관리합니다.
"""

import os
import sys
from pathlib import Path
from typing import Optional

# 경로 설정 (VM 환경 대응)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


# .env 파일을 먼저 로드
def _load_env():
    """환경 변수를 먼저 로드하는 함수"""
    base_dir = Path(__file__).parent.parent
    env_path = base_dir / '.env'
    
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    # 따옴표 제거
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    os.environ.setdefault(key, value)


# 환경변수 먼저 로드
_load_env()


class Config:
    """애플리케이션 설정 클래스"""
    
    # 기본 경로 설정
    BASE_DIR = Path(__file__).parent.parent

    # 응답 메시지 프리픽스 (이것만 수정하면 모든 응답에 반영!)
    RESPONSE_PREFIX: str = os.getenv('RESPONSE_PREFIX', '')
    
    # Mastodon API 설정 (이제 환경변수가 로드된 후라서 정상 작동)
    MASTODON_CLIENT_ID: str = os.getenv('MASTODON_CLIENT_ID', '')
    MASTODON_CLIENT_SECRET: str = os.getenv('MASTODON_CLIENT_SECRET', '')
    MASTODON_ACCESS_TOKEN: str = os.getenv('MASTODON_ACCESS_TOKEN', '')
    MASTODON_API_BASE_URL: str = os.getenv('MASTODON_API_BASE_URL', '')
    
    # Google Sheets 설정
    GOOGLE_CREDENTIALS_PATH: str = os.getenv(
        'GOOGLE_CREDENTIALS_PATH', 
        str(BASE_DIR / 'credentials' / 'credentials.json')
    )
    SHEET_NAME: str = os.getenv('SHEET_NAME', '메인 시트')
    
    # 봇 동작 설정
    MAX_RETRIES: int = int(os.getenv('BOT_MAX_RETRIES', '5'))
    BASE_WAIT_TIME: int = int(os.getenv('BOT_BASE_WAIT_TIME', '2'))
    MAX_DICE_COUNT: int = int(os.getenv('BOT_MAX_DICE_COUNT', '20'))
    MAX_DICE_SIDES: int = int(os.getenv('BOT_MAX_DICE_SIDES', '1000'))
    MAX_CARD_COUNT: int = int(os.getenv('BOT_MAX_CARD_COUNT', '52'))
    
    # 시스템 관리자 설정
    SYSTEM_ADMIN_ID: str = os.getenv('SYSTEM_ADMIN_ID', 'admin')
    
    # 로그 설정
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE_PATH: str = os.getenv('LOG_FILE_PATH', 'logs/bot.log')
    LOG_MAX_BYTES: int = int(os.getenv('LOG_MAX_BYTES', '10485760'))  # 10MB
    LOG_BACKUP_COUNT: int = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    
    # 캐시 설정
    CACHE_TTL: int = int(os.getenv('CACHE_TTL', '1'))  # 5분
    
    # 운세 설정
    FORTUNE_CACHE_ENABLED: bool = os.getenv('FORTUNE_CACHE_ENABLED', 'True').lower() == 'true'
    
    # 개발/디버그 설정
    DEBUG_MODE: bool = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
    ENABLE_CONSOLE_LOG: bool = os.getenv('ENABLE_CONSOLE_LOG', 'True').lower() == 'true'
    
    # 프리미엄 기능 설정
    PREMIUM_TRANSFER_ENABLED: bool = os.getenv('PREMIUM_TRANSFER_ENABLED', 'False').lower() == 'true'
    
    # 워크시트 이름 상수 (환경변수에서 로드)
    WORKSHEET_NAMES = {
        'HELP': os.getenv('HELP_SHEET', '도움말'),
        'ROSTER': os.getenv('LIST_SHEET', '명단'), 
        'CUSTOM': os.getenv('CUSTOM_SHEET', '커스텀'),
        'FORTUNE': os.getenv('FORTUNE_SHEET', '운세'),
    }
    
    # 시스템 키워드 (커스텀 명령어와 구분하기 위함)
    SYSTEM_KEYWORDS = [
        '도움말',
        '다이스', '카드 뽑기', '카드뽑기', '운세',
        '소지금', '포인트', '갈레온', '코인', '달러',
        '소지품', '인벤토리', '가방',
        '상점', '마트', '매점', '설명', '사용', '구매',
        '양도',
        '소지금 추가', '소지금 차감', '소지금추가', '소지금차감',
        ]
    
    # 에러 메시지 상수
    ERROR_MESSAGES = {
        'USER_NOT_FOUND': '등록되지 않은 사용자입니다. 먼저 캐릭터를 등록해주세요.',
        'USER_ID_CHECK_FAILED': '명령어 시전자의 아이디를 확인할 수 없습니다. 잠시만 기다려 주세요.',
        'USER_NAME_INVALID': '사용자 이름 정보가 올바르지 않습니다.',
        'TEMPORARY_ERROR': '일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.',
        'UNKNOWN_COMMAND': '알 수 없는 명령어입니다. [도움말]을 입력해 사용 가능한 명령어를 확인하세요.',
        'DICE_FORMAT_ERROR': '주사위 형식이 올바르지 않습니다. 예: [2d6], [1d6<4] (4 이하 성공), [3d10>7] (7 이상 성공)',
        'DICE_COUNT_LIMIT': f'주사위 개수는 최대 20개까지 가능합니다.',
        'DICE_SIDES_LIMIT': f'주사위 면수는 최대 1000면까지 가능합니다.',
        'SHEET_NOT_FOUND': '필요한 시트를 찾을 수 없습니다.',
        'DATA_NOT_FOUND': '데이터를 찾을 수 없습니다.',
        'PREMIUM_TRANSFER_REQUIRED': '양도 기능을 위해서는 추가 옵션을 구매하시기 바랍니다.',
    }
    
    # 성공 메시지 상수
    SUCCESS_MESSAGES = {
        'SHEET_CONNECTED': '스프레드시트 연결 성공',
        'AUTH_SUCCESS': 'auth success',
        'STREAMING_START': 'Mastodon 스트리밍 시작',
        'ERROR_NOTIFICATION_SENT': '오류 알림 전송 완료'
    }
    
    @classmethod
    def get_credentials_path(cls) -> Path:
        """
        Google 인증 파일의 경로를 반환합니다.
        
        Returns:
            Path: 인증 파일 경로
        """
        cred_path = Path(cls.GOOGLE_CREDENTIALS_PATH)
        if not cred_path.is_absolute():
            cred_path = cls.BASE_DIR / cred_path
        return cred_path
    
    @classmethod
    def is_system_keyword(cls, keyword: str) -> bool:
        """
        시스템 키워드인지 확인합니다.
        
        Args:
            keyword: 확인할 키워드
            
        Returns:
            bool: 시스템 키워드면 True
        """
        return keyword in cls.SYSTEM_KEYWORDS
    
    @classmethod
    def get_worksheet_name(cls, key: str) -> Optional[str]:
        """
        워크시트 키에 해당하는 실제 시트 이름을 반환합니다.
        
        Args:
            key: 워크시트 키 (예: 'ROSTER', 'LOG')
            
        Returns:
            Optional[str]: 시트 이름 또는 None
        """
        return cls.WORKSHEET_NAMES.get(key.upper())
    
    @classmethod
    def get_error_message(cls, key: str) -> str:
        """
        에러 메시지 키에 해당하는 메시지를 반환합니다.
        
        Args:
            key: 에러 메시지 키
            
        Returns:
            str: 에러 메시지
        """
        return cls.ERROR_MESSAGES.get(key, cls.ERROR_MESSAGES['TEMPORARY_ERROR'])
    
    @classmethod
    def get_success_message(cls, key: str) -> str:
        """
        성공 메시지 키에 해당하는 메시지를 반환합니다.
        
        Args:
            key: 성공 메시지 키
            
        Returns:
            str: 성공 메시지
        """
        return cls.SUCCESS_MESSAGES.get(key, '')
    
    @classmethod
    def format_response(cls, message: str) -> str:
        """
        모든 응답 메시지에 프리픽스 추가
        
        Args:
            message: 원본 메시지
            
        Returns:
            str: 프리픽스가 추가된 메시지
        """
        if not message or not isinstance(message, str):
            return message
        
        # 공백 제거
        message = message.strip()
        if not message:
            return message
        
        # 이미 프리픽스가 있으면 중복 방지
        if message.startswith(cls.RESPONSE_PREFIX.strip()):
            return message
            
        return f"{cls.RESPONSE_PREFIX}{message}"


# 설정 인스턴스 (싱글톤 패턴)
config = Config()
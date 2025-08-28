"""
환경 설정 검증 스크립트
봇 실행 전에 모든 필요한 환경이 올바르게 설정되었는지 확인합니다.
"""

import os
import sys
import time
from pathlib import Path
from typing import List, Tuple, Dict, Any

# 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class SetupChecker:
    """환경 설정 검증 클래스"""
    
    def __init__(self):
        """SetupChecker 초기화"""
        self.errors = []
        self.warnings = []
        self.info = []
        self.start_time = time.time()
    
    def check_all(self) -> bool:
        """모든 설정 검증"""
        print("🔍 마스토돈 봇 환경 설정 검증")
        print("=" * 50)
        
        checks = [
            ("Python 환경 확인", self.check_python_environment),
            ("필수 패키지 확인", self.check_required_packages),
            ("환경 변수 확인", self.check_environment_variables),
            ("Google 인증 파일 확인", self.check_google_credentials),
            ("마스토돈 API 연결 확인", self.check_mastodon_connection),
            ("Google Sheets 연결 확인", self.check_google_sheets),
            ("봇 모듈 확인", self.check_bot_modules),
            ("권한 및 디렉토리 확인", self.check_permissions),
        ]
        
        for check_name, check_func in checks:
            print(f"\n🔍 {check_name}...")
            try:
                check_func()
                if not any(check_name in error for error in self.errors):
                    print(f"  ✅ 통과")
            except Exception as e:
                self.errors.append(f"{check_name}: 검증 중 오류 - {str(e)}")
                print(f"  💥 오류: {str(e)}")
        
        self._print_summary()
        return len(self.errors) == 0
    
    def check_python_environment(self) -> None:
        """Python 환경 확인"""
        # Python 버전 확인
        python_version = sys.version_info
        if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 8):
            self.errors.append("Python 3.8 이상이 필요합니다")
        else:
            self.info.append(f"Python {python_version.major}.{python_version.minor}.{python_version.micro}")
        
        # 가상환경 확인
        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            self.info.append("가상환경에서 실행 중 (권장)")
        else:
            self.warnings.append("가상환경 사용을 권장합니다")
    
    def check_required_packages(self) -> None:
        """필수 패키지 확인"""
        required_packages = {
            'mastodon': 'Mastodon.py',
            'gspread': 'gspread', 
            'bs4': 'beautifulsoup4',
            'pytz': 'pytz'
        }
        
        missing_packages = []
        installed_packages = []
        
        for module_name, package_name in required_packages.items():
            try:
                __import__(module_name)
                installed_packages.append(package_name)
            except ImportError:
                missing_packages.append(package_name)
        
        if missing_packages:
            self.errors.append(f"필수 패키지 누락: {', '.join(missing_packages)}")
            self.errors.append("설치 명령: pip install " + " ".join(missing_packages))
        
        if installed_packages:
            self.info.append(f"설치된 패키지: {', '.join(installed_packages)}")
    
    def check_environment_variables(self) -> None:
        """환경 변수 확인"""
        # .env 파일 확인
        env_file = Path('.env')
        if env_file.exists():
            self.info.append(".env 파일 발견")
            self._load_env_file()
        else:
            self.warnings.append(".env 파일이 없습니다 (환경 변수로 설정되어야 함)")
        
        # 필수 환경 변수 확인
        required_env_vars = {
            'MASTODON_CLIENT_ID': '마스토돈 클라이언트 ID',
            'MASTODON_CLIENT_SECRET': '마스토돈 클라이언트 시크릿',
            'MASTODON_ACCESS_TOKEN': '마스토돈 액세스 토큰',
            'MASTODON_API_BASE_URL': '마스토돈 인스턴스 URL'
        }
        
        missing_vars = []
        found_vars = []
        
        for var_name, description in required_env_vars.items():
            value = os.getenv(var_name)
            if not value or value.strip() == '':
                missing_vars.append(f"{var_name} ({description})")
            else:
                found_vars.append(var_name)
                # 민감한 정보는 일부만 표시
                if len(value) > 10:
                    display_value = value[:4] + "..." + value[-4:]
                else:
                    display_value = "***"
                self.info.append(f"{var_name}: {display_value}")
        
        if missing_vars:
            self.errors.append("필수 환경 변수 누락:")
            for var in missing_vars:
                self.errors.append(f"  - {var}")
        
        # 선택적 환경 변수 확인
        optional_env_vars = {
            'SHEET_NAME': 'Google Sheets 이름',
            'GOOGLE_CREDENTIALS_PATH': 'Google 인증 파일 경로',
            'LOG_LEVEL': '로그 레벨'
        }
        
        for var_name, description in optional_env_vars.items():
            value = os.getenv(var_name)
            if value:
                self.info.append(f"{var_name}: {value}")
            else:
                self.info.append(f"{var_name}: 기본값 사용")
    
    def check_google_credentials(self) -> None:
        """Google 인증 파일 확인"""
        # 환경 변수에서 경로 확인
        cred_path = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials/credentials.json')
        
        # 상대 경로인 경우 절대 경로로 변환
        if not os.path.isabs(cred_path):
            cred_path = os.path.join(os.path.dirname(__file__), cred_path)
        
        cred_file = Path(cred_path)
        
        if not cred_file.exists():
            self.errors.append(f"Google 인증 파일을 찾을 수 없습니다: {cred_path}")
            self.errors.append("Google Cloud Console에서 서비스 계정 키를 다운로드하세요")
        else:
            self.info.append(f"Google 인증 파일: {cred_path}")
            
            # 파일 내용 기본 검증
            try:
                import json
                with open(cred_file, 'r', encoding='utf-8') as f:
                    cred_data = json.load(f)
                
                required_keys = ['type', 'project_id', 'private_key', 'client_email']
                missing_keys = [key for key in required_keys if key not in cred_data]
                
                if missing_keys:
                    self.errors.append(f"인증 파일에 필수 키 누락: {missing_keys}")
                else:
                    self.info.append(f"프로젝트 ID: {cred_data['project_id']}")
                    self.info.append(f"서비스 계정: {cred_data['client_email']}")
                    
            except json.JSONDecodeError:
                self.errors.append("Google 인증 파일 형식이 올바르지 않습니다")
            except Exception as e:
                self.warnings.append(f"인증 파일 검증 중 오류: {str(e)}")
    
    def check_mastodon_connection(self) -> None:
        """마스토돈 API 연결 확인"""
        try:
            import mastodon
            
            # 환경 변수 확인
            client_id = os.getenv('MASTODON_CLIENT_ID')
            client_secret = os.getenv('MASTODON_CLIENT_SECRET')
            access_token = os.getenv('MASTODON_ACCESS_TOKEN')
            api_base_url = os.getenv('MASTODON_API_BASE_URL')
            
            if not all([client_id, client_secret, access_token, api_base_url]):
                self.errors.append("마스토돈 환경 변수가 설정되지 않아 연결 테스트를 건너뜁니다")
                return
            
            # API 객체 생성
            api = mastodon.Mastodon(
                client_id=client_id,
                client_secret=client_secret,
                access_token=access_token,
                api_base_url=api_base_url,
                version_check_mode='none'
            )
            
            # 연결 테스트
            account_info = api.me()
            
            self.info.append(f"마스토돈 연결 성공")
            self.info.append(f"봇 계정: @{account_info.get('username', 'Unknown')}")
            self.info.append(f"인스턴스: {api_base_url}")
            
        except ImportError:
            self.errors.append("mastodon.py 패키지가 설치되지 않았습니다")
        except Exception as e:
            self.errors.append(f"마스토돈 API 연결 실패: {str(e)}")
            if "401" in str(e):
                self.errors.append("인증 정보가 올바르지 않습니다")
            elif "404" in str(e):
                self.errors.append("API URL이 올바르지 않습니다")
    
    def check_google_sheets(self) -> None:
        """Google Sheets 연결 확인"""
        try:
            import gspread
            
            # 인증 파일 경로
            cred_path = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials/credentials.json')
            if not os.path.isabs(cred_path):
                cred_path = os.path.join(os.path.dirname(__file__), cred_path)
            
            if not os.path.exists(cred_path):
                self.errors.append("Google 인증 파일이 없어 Sheets 연결 테스트를 건너뜁니다")
                return
            
            # Google Sheets 연결 테스트
            gc = gspread.service_account(filename=cred_path)
            
            # 시트 이름 확인
            sheet_name = os.getenv('SHEET_NAME', '자동봇 시트')
            
            try:
                spreadsheet = gc.open(sheet_name)
                worksheets = spreadsheet.worksheets()
                
                self.info.append(f"Google Sheets 연결 성공")
                self.info.append(f"시트 이름: {sheet_name}")
                self.info.append(f"워크시트 개수: {len(worksheets)}개")
                
                # 필수 워크시트 확인
                required_sheets = ['도움말', '명단', '운세', '커스텀',]
                found_sheets = [ws.title for ws in worksheets]
                missing_sheets = [sheet for sheet in required_sheets if sheet not in found_sheets]
                
                if missing_sheets:
                    self.warnings.append(f"권장 워크시트 누락: {', '.join(missing_sheets)}")
                else:
                    self.info.append("모든 필수 워크시트 확인됨")
                
            except gspread.exceptions.SpreadsheetNotFound:
                self.errors.append(f"Google Sheets '{sheet_name}'을 찾을 수 없습니다")
                self.errors.append("시트 이름을 확인하거나 서비스 계정에 접근 권한을 부여하세요")
            
        except ImportError:
            self.errors.append("gspread 패키지가 설치되지 않았습니다")
        except Exception as e:
            self.errors.append(f"Google Sheets 연결 실패: {str(e)}")
            if "403" in str(e):
                self.errors.append("서비스 계정에 시트 접근 권한이 없습니다")
    
    def check_bot_modules(self) -> None:
        """봇 모듈 확인"""
        try:
            # 핵심 모듈 import 테스트
            from config.settings import config
            from utils.logging_config import logger
            from utils.sheets_operations import SheetsManager
            from handlers.command_router import CommandRouter
            from handlers.stream_handler import StreamManager
            
            self.info.append("모든 봇 모듈 import 성공")
            
            # 기본 설정값 확인
            self.info.append(f"최대 재시도: {config.MAX_RETRIES}")
            self.info.append(f"최대 다이스 개수: {config.MAX_DICE_COUNT}")
            self.info.append(f"최대 카드 개수: {config.MAX_CARD_COUNT}")
            
        except ImportError as e:
            self.errors.append(f"봇 모듈 import 실패: {str(e)}")
        except Exception as e:
            self.errors.append(f"봇 모듈 확인 중 오류: {str(e)}")
    
    def check_permissions(self) -> None:
        """권한 및 디렉토리 확인"""
        # 현재 디렉토리 쓰기 권한 확인
        try:
            test_file = Path('test_write_permission.tmp')
            test_file.write_text('test')
            test_file.unlink()
            self.info.append("디렉토리 쓰기 권한 확인됨")
        except Exception:
            self.warnings.append("현재 디렉토리에 쓰기 권한이 없을 수 있습니다")
        
        # 로그 디렉토리 확인
        log_path = os.getenv('LOG_FILE_PATH', 'logs/bot.log')
        log_dir = Path(log_path).parent
        
        if not log_dir.exists():
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
                self.info.append(f"로그 디렉토리 생성: {log_dir}")
            except Exception:
                self.warnings.append(f"로그 디렉토리 생성 실패: {log_dir}")
        else:
            self.info.append(f"로그 디렉토리 확인됨: {log_dir}")
        
        # 필수 파일들 확인
        required_files = [
            'main.py',
            'requirements.txt',
            '.env.example'
        ]
        
        missing_files = []
        for filename in required_files:
            if not Path(filename).exists():
                missing_files.append(filename)
        
        if missing_files:
            self.warnings.append(f"권장 파일 누락: {', '.join(missing_files)}")
    
    def _load_env_file(self) -> None:
        """환경 변수 파일 로드"""
        try:
            env_file = Path('.env')
            with open(env_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ.setdefault(key.strip(), value.strip())
            
            self.info.append(".env 파일 로드 완료")
            
        except Exception as e:
            self.warnings.append(f".env 파일 로드 실패: {str(e)}")
    
    def _print_summary(self) -> None:
        """검증 결과 요약 출력"""
        total_time = time.time() - self.start_time
        
        print("\n" + "=" * 50)
        print("📊 환경 설정 검증 결과")
        print("=" * 50)
        
        if self.errors:
            print(f"\n❌ 오류 ({len(self.errors)}개):")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")
        
        if self.warnings:
            print(f"\n⚠️ 경고 ({len(self.warnings)}개):")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")
        
        if self.info:
            print(f"\n✅ 확인된 정보 ({len(self.info)}개):")
            for i, info in enumerate(self.info, 1):
                print(f"  {i}. {info}")
        
        print(f"\n🕒 검증 시간: {total_time:.2f}초")
        print("=" * 50)
        
        if len(self.errors) == 0:
            print("🎉 모든 환경 설정이 완료되었습니다!")
            print("✅ 봇을 실행할 준비가 되었습니다.")
            print("\n실행 명령: python main.py")
        else:
            print("🚨 환경 설정에 문제가 있습니다.")
            print("❗ 오류를 수정한 후 다시 검증해주세요.")
            print("\n다시 검증: python check_setup.py")
        
        print("=" * 50)


def create_example_env():
    """예시 .env 파일 생성"""
    env_example_content = """# 마스토돈 API 설정
MASTODON_CLIENT_ID=your_client_id_here
MASTODON_CLIENT_SECRET=your_client_secret_here
MASTODON_ACCESS_TOKEN=your_access_token_here
MASTODON_API_BASE_URL=https://your.mastodon.instance

# Google Sheets 설정
GOOGLE_CREDENTIALS_PATH=credentials.json
SHEET_NAME=기본 자동봇 시트

# 봇 설정 (선택사항)
BOT_MAX_RETRIES=5
BOT_BASE_WAIT_TIME=2
LOG_LEVEL=INFO

# 시스템 관리자 설정
SYSTEM_ADMIN_ID=longwhile
"""
    
    try:
        with open('.env.example', 'w', encoding='utf-8') as f:
            f.write(env_example_content)
        print("✅ .env.example 파일을 생성했습니다.")
        print("📝 이 파일을 .env로 복사하고 실제 값으로 수정하세요.")
        return True
    except Exception as e:
        print(f"❌ .env.example 파일 생성 실패: {e}")
        return False


def show_setup_guide():
    """설정 가이드 출력"""
    guide = """
🚀 마스토돈 봇 설정 가이드

1️⃣ 필수 패키지 설치:
   pip install -r requirements.txt

2️⃣ 마스토돈 API 설정:
   - 마스토돈 인스턴스에서 애플리케이션 등록
   - 클라이언트 ID, 시크릿, 액세스 토큰 발급

3️⃣ Google Sheets API 설정:
   - Google Cloud Console에서 프로젝트 생성
   - Sheets API 활성화
   - 서비스 계정 생성 및 키 다운로드
   - credentials/credentials.json으로 저장

4️⃣ 환경 변수 설정:
   - .env.example을 .env로 복사
   - 실제 값으로 수정

5️⃣ Google Sheets 준비:
   - 스프레드시트 생성
   - 서비스 계정에 편집 권한 부여
   - 필수 워크시트 생성: 명단, 관리, 도움말, 이상행동, 관찰, 속삭임, 아이템

6️⃣ 환경 검증:
   python check_setup.py

7️⃣ 봇 실행:
   python main.py

📖 자세한 설명은 README.md를 참고하세요.
"""
    print(guide)


def quick_check():
    """빠른 검증 (핵심 요소만)"""
    print("⚡ 빠른 환경 검증")
    print("-" * 30)
    
    issues = []
    
    # Python 버전
    if sys.version_info < (3, 8):
        issues.append("Python 3.8+ 필요")
    else:
        print("✅ Python 버전 OK")
    
    # 필수 패키지
    try:
        import mastodon, gspread, bs4, pytz
        print("✅ 필수 패키지 OK")
    except ImportError as e:
        issues.append(f"패키지 누락: {e}")
    
    # 환경 변수
    required_vars = ['MASTODON_CLIENT_ID', 'MASTODON_CLIENT_SECRET', 'MASTODON_ACCESS_TOKEN']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        issues.append(f"환경 변수 누락: {', '.join(missing_vars)}")
    else:
        print("✅ 환경 변수 OK")
    
    # 인증 파일
    if os.path.exists('credentials/credentials.json'):
        print("✅ Google 인증 파일 OK")
    else:
        issues.append("credentials/credentials.json 파일 없음")
    
    if issues:
        print(f"\n❌ 발견된 문제 ({len(issues)}개):")
        for issue in issues:
            print(f"  - {issue}")
        print("\n전체 검증 실행: python check_setup.py")
        return False
    else:
        print("\n🎉 빠른 검증 통과!")
        print("✅ 기본 환경이 준비되었습니다.")
        return True


def main():
    """메인 실행 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="마스토돈 봇 환경 설정 검증")
    parser.add_argument("--quick", action="store_true", help="빠른 검증만 실행")
    parser.add_argument("--guide", action="store_true", help="설정 가이드 표시")
    parser.add_argument("--create-env", action="store_true", help=".env.example 파일 생성")
    
    args = parser.parse_args()
    
    if args.guide:
        show_setup_guide()
        return 0
    
    if args.create_env:
        success = create_example_env()
        return 0 if success else 1
    
    if args.quick:
        success = quick_check()
        return 0 if success else 1
    
    # 전체 검증 실행
    checker = SetupChecker()
    success = checker.check_all()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
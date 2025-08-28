"""
마스토돈 자동봇 메인 실행 파일
리팩토링된 버전 - 모든 새로운 모듈들을 통합하여 실행합니다.
"""

import os
import sys
import signal
import time
from typing import Optional

# 경로 설정 (VM 환경 대응)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import mastodon
    from config.settings import config
    from config.validators import validate_startup_config
    from utils.logging_config import setup_logging, logger, bot_logger
    from utils.error_handling import setup_global_exception_handler
    from utils.sheets_operations import SheetsManager
    from utils.cache_manager import bot_cache, warmup_cache
    from handlers.stream_handler import StreamManager,validate_stream_dependencies
    from handlers.command_router import initialize_command_router
except ImportError as e:
    print(f"❌ 필수 모듈 임포트 실패: {e}")
    print("필요한 패키지가 설치되어 있는지 확인해주세요.")
    sys.exit(1)


class BotApplication:
    """
    마스토돈 봇 애플리케이션 클래스
    
    봇의 전체 생명주기를 관리합니다:
    - 초기화 및 설정 검증
    - 마스토돈 API 연결
    - Google Sheets 연결
    - 명령어 시스템 초기화
    - 스트리밍 시작 및 관리
    """
    
    def __init__(self):
        """BotApplication 초기화"""
        self.api: Optional[mastodon.Mastodon] = None
        self.sheets_manager: Optional[SheetsManager] = None
        self.stream_manager: Optional[StreamManager] = None
        self.is_running = False
        self.startup_time = time.time()
        
        # 시그널 핸들러 설정 (Ctrl+C 처리)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def run(self) -> int:
        """
        봇 애플리케이션 실행
        
        Returns:
            int: 종료 코드 (0: 정상, 1: 오류)
        """
        try:
            logger.info("=" * 60)
            logger.info("🤖 마스토돈 자동봇 시작")
            logger.info("=" * 60)
            
            # 1. 기본 설정 및 검증
            if not self._initialize_basic_systems():
                return 1
            
            # 2. 외부 서비스 연결
            if not self._connect_external_services():
                return 1
            
            # 3. 봇 시스템 초기화
            if not self._initialize_bot_systems():
                return 1
            
            # 4. 스트리밍 시작
            if not self._start_streaming():
                return 1
            
            # 정상 종료
            logger.info("🎉 봇이 정상적으로 종료되었습니다.")
            return 0
            
        except KeyboardInterrupt:
            logger.info("👋 사용자 요청으로 봇을 종료합니다.")
            return 0
        except Exception as e:
            logger.critical(f"💥 예상치 못한 오류로 봇이 종료됩니다: {e}", exc_info=True)
            self._send_emergency_notification(str(e))
            return 1
        finally:
            self._cleanup()
    
    def _initialize_basic_systems(self) -> bool:
        """기본 시스템 초기화"""
        try:
            logger.info("🔧 기본 시스템 초기화 중...")
            
            # 전역 예외 핸들러 설정
            setup_global_exception_handler()
            
            # 환경 설정 검증
            is_valid, validation_summary = validate_startup_config()
            if not is_valid:
                logger.error("❌ 설정 검증 실패:")
                logger.error(validation_summary)
                return False
            
            logger.info("✅ 설정 검증 완료")
            
            # 스트리밍 의존성 검증
            deps_valid, deps_errors = validate_stream_dependencies()
            if not deps_valid:
                logger.error("❌ 스트리밍 의존성 검증 실패:")
                for error in deps_errors:
                    logger.error(f"  - {error}")
                return False
            
            logger.info("✅ 의존성 검증 완료")
            return True
            
        except Exception as e:
            logger.error(f"❌ 기본 시스템 초기화 실패: {e}")
            return False
    
    def _connect_external_services(self) -> bool:
        """외부 서비스 연결"""
        try:
            logger.info("🌐 외부 서비스 연결 중...")
            
            # 마스토돈 API 연결
            if not self._connect_mastodon_api():
                return False
            
            # Google Sheets 연결
            if not self._connect_google_sheets():
                return False
            
            logger.info("✅ 모든 외부 서비스 연결 완료")
            return True
            
        except Exception as e:
            logger.error(f"❌ 외부 서비스 연결 실패: {e}")
            return False
    
    def _connect_mastodon_api(self) -> bool:
        """마스토돈 API 연결"""
        try:
            logger.info("📡 마스토돈 API 연결 중...")
            
            # 액세스 토큰이 있으면 직접 사용 (CLIENT_ID, CLIENT_SECRET 불필요)
            if config.MASTODON_ACCESS_TOKEN:
                self.api = mastodon.Mastodon(
                    access_token=config.MASTODON_ACCESS_TOKEN,
                    api_base_url=config.MASTODON_API_BASE_URL,
                    version_check_mode='none'
                )
            else:
                # 액세스 토큰이 없는 경우만 CLIENT_ID, CLIENT_SECRET 사용
                self.api = mastodon.Mastodon(
                    client_id=config.MASTODON_CLIENT_ID,
                    client_secret=config.MASTODON_CLIENT_SECRET,
                    access_token=config.MASTODON_ACCESS_TOKEN,
                    api_base_url=config.MASTODON_API_BASE_URL,
                    version_check_mode='none'
                )
            
            # 연결 테스트
            account_info = self.api.me()
            bot_username = account_info.get('username', 'Unknown')
            
            logger.info(f"✅ 마스토돈 API 연결 성공 (@{bot_username})")
            return True
            
        except Exception as e:
            logger.error(f"❌ 마스토돈 API 연결 실패: {e}")
            return False
    
    def _connect_google_sheets(self) -> bool:
        """Google Sheets 연결"""
        try:
            logger.info("📊 Google Sheets 연결 중...")
            
            self.sheets_manager = SheetsManager(
                sheet_id=config.SHEET_ID,
                credentials_path=config.get_credentials_path()
            )
            
            # 연결 테스트 및 구조 검증
            validation_result = self.sheets_manager.validate_sheet_structure()
            
            if not validation_result['valid']:
                logger.error("❌ 시트 구조 검증 실패:")
                for error in validation_result['errors']:
                    logger.error(f"  - {error}")
                return False
            
            if validation_result['warnings']:
                logger.warning("⚠️ 시트 구조 경고:")
                for warning in validation_result['warnings']:
                    logger.warning(f"  - {warning}")
            
            logger.info(f"✅ Google Sheets 연결 성공 (시트: {len(validation_result['worksheets_found'])}개)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Google Sheets 연결 실패: {e}")
            return False
    
    def _initialize_bot_systems(self) -> bool:
        """봇 시스템 초기화"""
        try:
            logger.info("🤖 봇 시스템 초기화 중...")
            
            # 명령어 라우터 초기화 (API 인스턴스 전달)
            command_router = initialize_command_router(self.sheets_manager, self.api)
            logger.info("✅ 명령어 라우터 초기화 완료")
            
            # 캐시 워밍업
            try:
                warmup_cache(self.sheets_manager)
                logger.info("✅ 캐시 워밍업 완료")
            except Exception as e:
                logger.warning(f"⚠️ 캐시 워밍업 실패 (계속 진행): {e}")
            
            # DM 지원 스트림 매니저 생성
            try:
                from handlers.stream_handler import initialize_stream_with_dm
                self.stream_manager = initialize_stream_with_dm(self.api, self.sheets_manager)
                logger.info("✅ DM 지원 스트림 매니저 생성 완료")
            except ImportError:
                # initialize_stream_with_dm 함수가 없는 경우 기본 스트림 매니저 사용
                logger.warning("⚠️ DM 지원 함수를 찾을 수 없어 기본 스트림 매니저 사용")
                self.stream_manager = StreamManager(self.api, self.sheets_manager)
                logger.info("✅ 기본 스트림 매니저 생성 완료")
            except Exception as e:
                logger.error(f"❌ DM 지원 스트림 매니저 생성 실패, 기본 매니저로 전환: {e}")
                self.stream_manager = StreamManager(self.api, self.sheets_manager)
                logger.info("✅ 기본 스트림 매니저 생성 완료")
            
            # 명령어 검증
            validation_result = command_router.validate_all_systems()
            if not validation_result['overall_valid']:
                logger.warning("⚠️ 일부 명령어에 문제가 있습니다:")
                for error in validation_result['errors']:
                    logger.warning(f"  - {error}")
            else:
                logger.info("✅ 모든 명령어 검증 완료")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 봇 시스템 초기화 실패: {e}")
            return False
    
    def _start_streaming(self) -> bool:
        """스트리밍 시작"""
        try:
            logger.info("🚀 마스토돈 스트리밍 시작...")
            
            # 스트리밍 시작 (블로킹)
            self.is_running = True
            success = self.stream_manager.start_streaming(max_retries=config.MAX_RETRIES)
            self.is_running = False
            
            if success:
                logger.info("✅ 스트리밍이 정상적으로 종료되었습니다")
                return True
            else:
                logger.error("❌ 스트리밍 시작 실패")
                return False
                
        except Exception as e:
            self.is_running = False
            logger.error(f"❌ 스트리밍 중 오류 발생: {e}")
            return False
    
    def _send_startup_notification(self) -> None:
        """시작 알림 전송"""
        try:
            uptime_seconds = time.time() - self.startup_time
            startup_message = (
                f"🤖 자동봇이 시작되었습니다!\n"
                f"📊 명령어 시스템 준비 완료\n"
                f"🔧 시작 시간: {uptime_seconds:.2f}초"
            )
            
            logger.info("✅ 시작 알림 전송 완료")
            
        except Exception as e:
            logger.warning(f"⚠️ 시작 알림 전송 실패: {e}")
    
    def _send_emergency_notification(self, error_message: str) -> None:
        """긴급 상황 알림 전송"""
        try:
            if not self.api:
                return
            
            # 사용자 공지
            self.api.status_post(
                status="자동봇이 오류로 인해 중지되었습니다. 복구 작업 중입니다.",
                visibility='unlisted'
            )
            
            # 관리자 알림
            if config.SYSTEM_ADMIN_ID:
                admin_message = f"@{config.SYSTEM_ADMIN_ID} 🚨 봇 시스템 오류\n{error_message[:400]}"
                self.api.status_post(
                    status=admin_message,
                    visibility='direct'
                )
            
            logger.info("✅ 긴급 알림 전송 완료")
            
        except Exception as e:
            logger.error(f"❌ 긴급 알림 전송 실패: {e}")
    
    def _signal_handler(self, signum, frame):
        """시그널 핸들러 (Ctrl+C 등)"""
        logger.info(f"🛑 종료 시그널 수신 ({signum})")
        self.is_running = False
        
        if self.stream_manager:
            self.stream_manager.stop_streaming()
    
    def _cleanup(self) -> None:
        """정리 작업"""
        try:
            logger.info("🧹 정리 작업 시작...")
            
            # 스트리밍 중지
            if self.stream_manager:
                self.stream_manager.stop_streaming()
            
            # 통계 기능 제거됨 - 더 이상 사용하지 않음
            
            # 캐시 정리
            try:
                bot_cache.cleanup_all_expired()
                logger.info("🗑️ 캐시 정리 완료")
            except Exception as e:
                logger.warning(f"캐시 정리 실패: {e}")
            
            logger.info("✅ 정리 작업 완료")
            
        except Exception as e:
            logger.error(f"❌ 정리 작업 중 오류: {e}")
    
    def get_status(self) -> dict:
        """애플리케이션 상태 반환 (개발/디버깅용)"""
        status = {
            'is_running': self.is_running,
            'startup_time': self.startup_time,
            'uptime_seconds': time.time() - self.startup_time,
            'api_connected': self.api is not None,
            'sheets_connected': self.sheets_manager is not None,
            'stream_manager_ready': self.stream_manager is not None,
        }
        
        # 스트림 매니저 상태 추가
        if self.stream_manager:
            status['stream_status'] = self.stream_manager.get_status()
            # handler_stats 제거됨 - 통계 기능 사용 안함
        
        return status


def main() -> int:
    """메인 엔트리 포인트"""
    # 로깅 시스템 초기화
    setup_logging()
    
    try:
        # 봇 애플리케이션 생성 및 실행
        app = BotApplication()
        return app.run()
        
    except Exception as e:
        print(f"💥 애플리케이션 시작 실패: {e}")
        return 1


def show_version():
    """버전 정보 출력"""
    print("🤖 마스토돈 자동봇 v2.1")
    print("🔧 모듈형 아키텍처")
    print("📊 Google Sheets 연동")
    print("⏰ 자동 일일 리셋 (KST 0시)")


def show_help():
    """도움말 출력"""
    print("🤖 마스토돈 자동봇 사용법")
    print("")
    print("실행:")
    print("  python main.py              # 봇 시작")
    print("  python main.py --version    # 버전 정보")
    print("  python main.py --help       # 이 도움말")
    print("")
    print("새로운 기능:")
    print("  ⏰ 자동 일일 리셋          # 매일 KST 0시에 성공수 초기화")
    print("  🎯 일일 성공 제한          # 하루 최대 2번까지 성공 가능")
    print("")
    print("환경 설정:")
    print("  .env 파일을 생성하거나 환경 변수를 설정하세요.")
    print("  .env.example 파일을 참고하세요.")
    print("")
    print("필수 환경 변수:")
    print("  MASTODON_CLIENT_ID       # 마스토돈 클라이언트 ID")
    print("  MASTODON_CLIENT_SECRET   # 마스토돈 클라이언트 시크릿")  
    print("  MASTODON_ACCESS_TOKEN    # 마스토돈 액세스 토큰")
    print("  MASTODON_API_BASE_URL    # 마스토돈 인스턴스 URL")
    print("")
    print("선택 환경 변수:")
    print("  SHEET_ID                # Google Sheets ID")
    print("  GOOGLE_CREDENTIALS_PATH # Google 인증 파일 경로")
    print("  LOG_LEVEL               # 로그 레벨 (DEBUG/INFO/WARNING/ERROR)")
    print("")


if __name__ == '__main__':
    # 명령행 인수 처리
    if len(sys.argv) > 1:
        if sys.argv[1] in ['--version', '-v']:
            show_version()
            sys.exit(0)
        elif sys.argv[1] in ['--help', '-h']:
            show_help()
            sys.exit(0)
        else:
            print(f"알 수 없는 옵션: {sys.argv[1]}")
            print("--help를 사용하여 도움말을 확인하세요.")
            sys.exit(1)
    
    # 봇 실행
    exit_code = main()
    sys.exit(exit_code)
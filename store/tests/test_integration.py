"""
통합 테스트 스크립트
전체 시스템의 통합 기능을 테스트합니다.
"""

import os
import sys
import time
import traceback
from typing import Dict, List, Tuple, Any

# 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class IntegrationTester:
    """통합 테스트 실행 클래스"""
    
    def __init__(self):
        """IntegrationTester 초기화"""
        self.test_results = []
        self.failed_tests = []
        self.warnings = []
        self.start_time = time.time()
        
    def run_all_tests(self) -> bool:
        """모든 테스트 실행"""
        print("=" * 60)
        print("🧪 마스토돈 봇 통합 테스트 시작")
        print("=" * 60)
        
        # 테스트 목록
        tests = [
            ("모듈 Import 테스트", self.test_module_imports),
            ("설정 시스템 테스트", self.test_config_system),
            ("로깅 시스템 테스트", self.test_logging_system),
            ("에러 처리 테스트", self.test_error_handling),
            ("데이터 모델 테스트", self.test_data_models),
            ("명령어 시스템 테스트", self.test_command_system),
            ("라우터 시스템 테스트", self.test_router_system),
            ("캐시 시스템 테스트", self.test_cache_system),
            ("시트 연결 테스트", self.test_sheets_connection),
            ("명령어 실행 테스트", self.test_command_execution),
        ]
        
        # 각 테스트 실행
        for test_name, test_func in tests:
            try:
                print(f"\n🔍 {test_name}...")
                success, message = test_func()
                
                if success:
                    print(f"  ✅ {message}")
                    self.test_results.append((test_name, True, message))
                else:
                    print(f"  ❌ {message}")
                    self.test_results.append((test_name, False, message))
                    self.failed_tests.append(test_name)
                    
            except Exception as e:
                error_msg = f"테스트 실행 중 오류: {str(e)}"
                print(f"  💥 {error_msg}")
                self.test_results.append((test_name, False, error_msg))
                self.failed_tests.append(test_name)
        
        # 결과 출력
        self._print_summary()
        
        # 전체 성공 여부 반환
        return len(self.failed_tests) == 0
    
    def test_module_imports(self) -> Tuple[bool, str]:
        """모듈 import 테스트"""
        try:
            # 기본 설정 모듈
            from config.settings import config
            from config.validators import validate_startup_config
            
            # 유틸리티 모듈
            from utils.logging_config import setup_logging, logger
            from utils.error_handling import safe_execute, CommandError
            from utils.sheets_operations import SheetsManager
            from utils.cache_manager import bot_cache
            
            # 데이터 모델
            from models.user import User, UserManager
            from models.command_result import CommandResult, CommandType
            
            # 명령어 모듈
            from commands.base_command import BaseCommand
            from commands.dice_command import DiceCommand
            from commands.card_command import CardCommand
            from commands.fortune_command import FortuneCommand
            from commands.custom_command import CustomCommand
            from commands.help_command import HelpCommand
            
            # 핸들러 모듈
            from handlers.command_router import CommandRouter
            from handlers.stream_handler import StreamManager
            
            return True, "모든 모듈 import 성공"
            
        except ImportError as e:
            return False, f"모듈 import 실패: {str(e)}"
        except Exception as e:
            return False, f"예상치 못한 오류: {str(e)}"
    
    def test_config_system(self) -> Tuple[bool, str]:
        """설정 시스템 테스트"""
        try:
            from config.settings import config
            from config.validators import validate_startup_config
            
            # 기본 설정값 확인
            required_configs = [
                'MAX_RETRIES', 'BASE_WAIT_TIME', 'MAX_DICE_COUNT', 
                'MAX_DICE_SIDES', 'MAX_CARD_COUNT', 'CACHE_TTL'
            ]
            
            for config_name in required_configs:
                if not hasattr(config, config_name):
                    return False, f"필수 설정 '{config_name}' 없음"
            
            # 환경 설정 검증 (실제 값이 없어도 검증 로직 확인)
            try:
                is_valid, summary = validate_startup_config()
                # 환경 변수가 없어서 실패하는 것은 정상
            except Exception as e:
                return False, f"설정 검증 로직 오류: {str(e)}"
            
            return True, f"설정 시스템 정상 (기본값: MAX_RETRIES={config.MAX_RETRIES})"
            
        except Exception as e:
            return False, f"설정 시스템 오류: {str(e)}"
    
    def test_logging_system(self) -> Tuple[bool, str]:
        """로깅 시스템 테스트"""
        try:
            from utils.logging_config import setup_logging, logger, bot_logger
            
            # 로거 초기화
            bot_logger_instance = setup_logging()
            
            # 로그 레벨 테스트
            logger.debug("디버그 로그 테스트")
            logger.info("정보 로그 테스트")
            logger.warning("경고 로그 테스트")
            
            # 구조화된 로깅 테스트
            bot_logger.log_command_execution("test_user", "[테스트]", "테스트 결과", True)
            
            return True, "로깅 시스템 정상 작동"
            
        except Exception as e:
            return False, f"로깅 시스템 오류: {str(e)}"
    
    def test_error_handling(self) -> Tuple[bool, str]:
        """에러 처리 시스템 테스트"""
        try:
            from utils.error_handling import (
                safe_execute, CommandError, DiceError, CardError,
                ErrorHandler, create_dice_error
            )
            
            # 안전한 실행 테스트
            def test_operation():
                return "테스트 성공"
            
            result = safe_execute(test_operation)
            if not result.success or result.result != "테스트 성공":
                return False, "safe_execute 실행 결과 오류"
            
            # 에러 생성 테스트
            dice_error = create_dice_error("테스트 다이스 오류")
            if not isinstance(dice_error, DiceError):
                return False, "에러 생성 실패"
            
            return True, "에러 처리 시스템 정상"
            
        except Exception as e:
            return False, f"에러 처리 시스템 오류: {str(e)}"
    
    def test_data_models(self) -> Tuple[bool, str]:
        """데이터 모델 테스트"""
        try:
            from models.user import User, create_user_from_sheet
            from models.command_result import (
                CommandResult, CommandType, DiceResult, 
                create_dice_result, create_card_result
            )
            
            # User 모델 테스트
            sheet_data = {'아이디': 'test_user', '이름': '테스트 사용자'}
            user = create_user_from_sheet(sheet_data)
            
            if user.id != 'test_user' or user.name != '테스트 사용자':
                return False, "User 모델 생성 실패"
            
            # CommandResult 테스트
            result = CommandResult.success(
                command_type=CommandType.DICE,
                user_id='test_user',
                user_name='테스트 사용자',
                original_command='[테스트]',
                message='테스트 성공'
            )
            
            if not result.is_successful():
                return False, "CommandResult 생성 실패"
            
            # DiceResult 테스트
            dice_result = create_dice_result("2d6", [3, 5])
            if dice_result.total != 8:
                return False, "DiceResult 계산 오류"
            
            return True, f"데이터 모델 정상 (User: {user.name}, Dice: {dice_result.total})"
            
        except Exception as e:
            return False, f"데이터 모델 오류: {str(e)}"
    
    def test_command_system(self) -> Tuple[bool, str]:
        """명령어 시스템 테스트"""
        try:
            from commands.dice_command import DiceCommand
            from commands.card_command import CardCommand
            from commands.fortune_command import FortuneCommand
            from commands.help_command import HelpCommand
            
            # 각 명령어 인스턴스 생성 테스트
            dice_cmd = DiceCommand()
            card_cmd = CardCommand()
            fortune_cmd = FortuneCommand()
            help_cmd = HelpCommand()
            
            # 기본 속성 확인
            commands = [dice_cmd, card_cmd, fortune_cmd, help_cmd]
            for cmd in commands:
                if not hasattr(cmd, 'get_help_text'):
                    return False, f"{cmd.__class__.__name__} get_help_text 메서드 없음"
                
                help_text = cmd.get_help_text()
                if not help_text:
                    return False, f"{cmd.__class__.__name__} 도움말 텍스트 없음"
            
            return True, f"명령어 시스템 정상 ({len(commands)}개 명령어)"
            
        except Exception as e:
            return False, f"명령어 시스템 오류: {str(e)}"
    
    def test_router_system(self) -> Tuple[bool, str]:
        """라우터 시스템 테스트"""
        try:
            from handlers.command_router import (
                CommandRouter, parse_command_from_text, 
                validate_command_format, is_custom_keyword
            )
            
            # 명령어 파싱 테스트
            keywords = parse_command_from_text("[다이스/2d6] 안녕하세요")
            if keywords != ['다이스', '2d6']:
                return False, f"명령어 파싱 오류: {keywords}"
            
            # 명령어 형식 검증 테스트
            valid, msg = validate_command_format("[다이스/2d6]")
            if not valid:
                return False, f"명령어 형식 검증 실패: {msg}"
            
            # 라우터 생성 테스트
            router = CommandRouter()
            if not router:
                return False, "CommandRouter 생성 실패"
            
            return True, "라우터 시스템 정상 (파싱 및 검증 기능 확인)"
            
        except Exception as e:
            return False, f"라우터 시스템 오류: {str(e)}"
    
    def test_cache_system(self) -> Tuple[bool, str]:
        """캐시 시스템 테스트"""
        try:
            from utils.cache_manager import bot_cache, CacheManager
            
            # 기본 캐시 테스트
            test_cache = CacheManager(default_ttl=60)
            
            # 캐시 설정 및 조회
            test_cache.set("test_key", "test_value")
            cached_value = test_cache.get("test_key")
            
            if cached_value != "test_value":
                return False, f"캐시 저장/조회 실패: {cached_value}"
            
            # 봇 캐시 테스트
            if not hasattr(bot_cache, 'user_cache'):
                return False, "bot_cache 구조 오류"
            
            # 캐시 구조 테스트
            if not hasattr(bot_cache, 'command_cache'):
                return False, "캐시 구조 오류"
            
            return True, f"캐시 시스템 정상 (테스트 값: {cached_value})"
            
        except Exception as e:
            return False, f"캐시 시스템 오류: {str(e)}"
    
    def test_sheets_connection(self) -> Tuple[bool, str]:
        """시트 연결 테스트 (환경 변수 없이도 실행 가능한 부분만)"""
        try:
            from utils.sheets_operations import SheetsManager
            
            # SheetsManager 생성 (실제 연결은 하지 않음)
            sheets_manager = SheetsManager()
            
            if not hasattr(sheets_manager, 'get_worksheet_data'):
                return False, "SheetsManager 메서드 누락"
            
            return True, "시트 연결 시스템 구조 정상 (실제 연결은 환경 설정 필요)"
            
        except Exception as e:
            return False, f"시트 연결 시스템 오류: {str(e)}"
    
    def test_command_execution(self) -> Tuple[bool, str]:
        """명령어 실행 테스트 (모의 실행)"""
        try:
            from commands.dice_command import DiceCommand
            from commands.card_command import CardCommand
            from models.user import User
            
            # 테스트 사용자 생성
            test_user = User(id="test_user", name="테스트 사용자")
            
            # 다이스 명령어 테스트 (시트 연결 없이)
            dice_cmd = DiceCommand()
            
            # 다이스 표현식 검증 테스트
            valid, msg = dice_cmd.validate_dice_expression_format("2d6")
            if not valid:
                return False, f"다이스 표현식 검증 실패: {msg}"
            
            # 카드 명령어 테스트
            card_cmd = CardCommand()
            
            # 카드 개수 검증 테스트
            valid, msg = card_cmd.validate_card_count_format("5장")
            if not valid:
                return False, f"카드 개수 검증 실패: {msg}"
            
            return True, "명령어 실행 시스템 정상 (검증 로직 확인)"
            
        except Exception as e:
            return False, f"명령어 실행 테스트 오류: {str(e)}"
    
    def _print_summary(self) -> None:
        """테스트 결과 요약 출력"""
        total_time = time.time() - self.start_time
        total_tests = len(self.test_results)
        passed_tests = total_tests - len(self.failed_tests)
        
        print("\n" + "=" * 60)
        print("📊 테스트 결과 요약")
        print("=" * 60)
        
        print(f"총 테스트: {total_tests}개")
        print(f"성공: {passed_tests}개")
        print(f"실패: {len(self.failed_tests)}개")
        print(f"실행 시간: {total_time:.2f}초")
        
        if self.failed_tests:
            print(f"\n❌ 실패한 테스트:")
            for i, test_name in enumerate(self.failed_tests, 1):
                print(f"  {i}. {test_name}")
        
        if self.warnings:
            print(f"\n⚠️ 경고:")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        print("\n" + "=" * 60)
        
        if len(self.failed_tests) == 0:
            print("🎉 모든 테스트가 성공했습니다!")
            print("✅ 시스템이 정상적으로 작동할 준비가 되었습니다.")
        else:
            print("🚨 일부 테스트가 실패했습니다.")
            print("❗ 실패한 부분을 수정한 후 다시 실행해주세요.")
        
        print("=" * 60)


def run_quick_test():
    """빠른 테스트 실행 (핵심 기능만)"""
    print("⚡ 빠른 테스트 모드")
    print("-" * 30)
    
    try:
        # 핵심 모듈 import 테스트
        from config.settings import config
        from utils.logging_config import logger
        from models.command_result import CommandType
        from commands.dice_command import DiceCommand
        from handlers.command_router import CommandRouter
        
        print("✅ 핵심 모듈 import 성공")
        
        # 기본 기능 테스트
        dice_cmd = DiceCommand()
        router = CommandRouter()
        
        print("✅ 핵심 객체 생성 성공")
        print("🎉 빠른 테스트 통과!")
        return True
        
    except Exception as e:
        print(f"❌ 빠른 테스트 실패: {e}")
        return False


def main():
    """메인 실행 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="마스토돈 봇 통합 테스트")
    parser.add_argument("--quick", action="store_true", help="빠른 테스트만 실행")
    parser.add_argument("--verbose", action="store_true", help="상세한 출력")
    
    args = parser.parse_args()
    
    if args.quick:
        success = run_quick_test()
    else:
        tester = IntegrationTester()
        success = tester.run_all_tests()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

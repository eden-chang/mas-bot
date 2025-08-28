"""
Mastodon 알림 처리 모듈
NOTICE 계정의 알림을 모니터링하고 스토리 명령어를 처리합니다.
"""

import os
import sys
import time
import threading
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import pytz

# 마스토돈 라이브러리
try:
    from mastodon import Mastodon, MastodonError, MastodonAPIError, MastodonNetworkError
except ImportError:
    print("❌ Mastodon.py 라이브러리가 설치되지 않았습니다.")
    print("pip install Mastodon.py 를 실행하세요.")
    sys.exit(1)

# 프로젝트 루트 경로 설정
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(current_dir)

try:
    from config.settings import config
    from utils.logging_config import get_logger
    from utils.datetime_utils import format_datetime_korean
    from core.mastodon_client import MultiMastodonManager
    from core.story_loop_manager import StoryLoopManager
except ImportError as e:
    print(f"❌ 필수 모듈 임포트 실패: {e}")
    sys.exit(1)

logger = get_logger(__name__)


@dataclass
class StoryCommand:
    """
    스토리 명령어 정보
    """
    command_type: str  # 'story', 'script', 'story_progress' 등
    worksheet_name: str
    sender_username: str
    sender_id: str
    notification_id: str
    toot_id: str
    timestamp: datetime
    is_direct: bool = True
    
    def __str__(self) -> str:
        return f"[{self.command_type}] {self.worksheet_name} from @{self.sender_username}"


class NotificationHandler:
    """
    Mastodon 알림 처리 클래스
    STORY 계정이 받는 NOTICE 계정의 direct 메시지를 모니터링합니다.
    """
    
    def __init__(self):
        """NotificationHandler 초기화"""
        self.mastodon_manager: Optional[MultiMastodonManager] = None
        self.story_loop_manager: Optional[StoryLoopManager] = None
        
        # STORY 계정의 마스토돈 클라이언트
        self.story_client: Optional[Mastodon] = None
        self.story_account_username: Optional[str] = None
        
        # 알림 처리 상태
        self.is_monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # 처리된 알림 추적 (중복 방지)
        self.processed_notifications: set = set()
        self.last_notification_id: Optional[str] = None
        
        # 명령어 패턴
        self.command_patterns = {
            'story': re.compile(r'\[스토리/(.+?)\]', re.IGNORECASE),
            'script': re.compile(r'\[스진/(.+?)\]', re.IGNORECASE), 
            'story_progress': re.compile(r'\[스토리진행/(.+?)\]', re.IGNORECASE)
        }
        
        # 통계
        self.stats = {
            'total_notifications': 0,
            'processed_commands': 0,
            'successful_commands': 0,
            'failed_commands': 0,
            'start_time': None,
            'last_check_time': None
        }
        
        logger.info("알림 처리기 초기화 완료")
    
    def initialize(self, mastodon_manager: MultiMastodonManager, story_loop_manager: StoryLoopManager) -> bool:
        """
        알림 처리기 초기화
        
        Args:
            mastodon_manager: 마스토돈 매니저
            story_loop_manager: 스토리 루프 매니저
        
        Returns:
            bool: 초기화 성공 여부
        """
        try:
            self.mastodon_manager = mastodon_manager
            self.story_loop_manager = story_loop_manager
            
            # STORY 계정 정보 설정 (mastodon_manager를 통해 접근)
            if 'STORY' not in self.mastodon_manager.clients:
                logger.error("STORY 계정을 찾을 수 없습니다")
                return False
            
            self.story_client = self.mastodon_manager.clients['STORY']
            
            # 연결 테스트 및 계정 정보 저장
            try:
                account_info = self.story_client.get_bot_info()
                if account_info:
                    self.story_account_username = account_info.get('username', '').lower()
                    logger.info(f"✅ STORY 계정 연결 성공: @{self.story_account_username}")
                else:
                    logger.error("❌ STORY 계정 정보 조회 실패")
                    return False
            except Exception as e:
                logger.error(f"❌ STORY 계정 연결 실패: {e}")
                return False
            
            logger.info("알림 처리기 초기화 성공")
            return True
            
        except Exception as e:
            logger.error(f"알림 처리기 초기화 실패: {e}")
            return False
    
    def start_monitoring(self) -> bool:
        """
        알림 모니터링 시작
        
        Returns:
            bool: 시작 성공 여부
        """
        try:
            if self.is_monitoring:
                logger.warning("알림 모니터링이 이미 실행 중입니다")
                return False
            
            if not self.story_client:
                logger.error("STORY 클라이언트가 초기화되지 않았습니다")
                return False
            
            logger.info("알림 모니터링 시작...")
            
            self.is_monitoring = True
            self._stop_event.clear()
            self.stats['start_time'] = datetime.now(pytz.timezone('Asia/Seoul')).isoformat()
            
            # 모니터링 스레드 시작
            self.monitor_thread = threading.Thread(
                target=self._monitor_notifications,
                name="NotificationMonitor",
                daemon=True
            )
            self.monitor_thread.start()
            
            logger.info("✅ 알림 모니터링 시작됨")
            return True
            
        except Exception as e:
            logger.error(f"알림 모니터링 시작 실패: {e}")
            self.is_monitoring = False
            return False
    
    def stop_monitoring(self) -> None:
        """알림 모니터링 중지"""
        try:
            if not self.is_monitoring:
                logger.info("알림 모니터링이 실행 중이지 않습니다")
                return
            
            logger.info("알림 모니터링 중지 중...")
            
            self.is_monitoring = False
            self._stop_event.set()
            
            # 스레드 종료 대기
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=5.0)
            
            logger.info("✅ 알림 모니터링 중지됨")
            
        except Exception as e:
            logger.error(f"알림 모니터링 중지 중 오류: {e}")
    
    def _monitor_notifications(self) -> None:
        """
        알림 모니터링 루프 (스레드에서 실행됨)
        """
        logger.info("알림 모니터링 루프 시작")
        
        check_interval = 5  # 5초마다 확인
        
        while self.is_monitoring and not self._stop_event.is_set():
            try:
                # 알림 확인
                self._check_notifications()
                
                # 다음 확인까지 대기
                self._stop_event.wait(timeout=check_interval)
                
            except Exception as e:
                logger.error(f"알림 모니터링 중 오류: {e}")
                time.sleep(check_interval)
        
        logger.info("알림 모니터링 루프 종료")
    
    def _check_notifications(self) -> None:
        """
        새로운 알림 확인 및 처리
        """
        try:
            self.stats['last_check_time'] = datetime.now(pytz.timezone('Asia/Seoul')).isoformat()
            
            # 최신 알림 조회 (최대 20개) - STORY 클라이언트의 raw mastodon client 사용
            notifications = self.story_client.client.notifications(limit=20)
            
            if not notifications:
                return
            
            # 새로운 알림만 처리 (ID 기준으로 필터링)
            new_notifications = []
            
            for notification in notifications:
                notif_id = str(notification.get('id', ''))
                
                # 이미 처리된 알림 건너뛰기
                if notif_id in self.processed_notifications:
                    continue
                
                # 멘션 타입만 처리
                if notification.get('type') != 'mention':
                    continue
                
                new_notifications.append(notification)
                self.processed_notifications.add(notif_id)
            
            # 새로운 알림 처리
            if new_notifications:
                logger.info(f"새로운 알림 {len(new_notifications)}개 발견")
                
                for notification in reversed(new_notifications):  # 오래된 것부터 처리
                    self._process_notification(notification)
            
            # 처리된 알림 ID 캐시 정리 (최대 1000개 유지)
            if len(self.processed_notifications) > 1000:
                # 오래된 것부터 500개 제거
                old_ids = list(self.processed_notifications)[:500]
                for old_id in old_ids:
                    self.processed_notifications.discard(old_id)
            
        except Exception as e:
            logger.error(f"알림 확인 중 오류: {e}")
    
    def _process_notification(self, notification: Dict[str, Any]) -> None:
        """
        개별 알림 처리
        
        Args:
            notification: 마스토돈 알림 데이터
        """
        try:
            self.stats['total_notifications'] += 1
            
            # 알림 정보 추출
            notif_id = str(notification.get('id', ''))
            account = notification.get('account', {})
            status = notification.get('status', {})
            
            if not account or not status:
                logger.debug(f"알림 {notif_id}: 계정 또는 상태 정보 없음")
                return
            
            sender_username = account.get('username', '')
            sender_id = str(account.get('id', ''))
            toot_id = str(status.get('id', ''))
            content = status.get('content', '')
            visibility = status.get('visibility', '')
            created_at = status.get('created_at', '')
            
            # HTML 태그 제거
            import html
            clean_content = html.unescape(re.sub(r'<[^>]+>', '', content)).strip()
            
            # Direct 메시지만 처리
            if visibility != 'direct':
                logger.debug(f"알림 {notif_id}: Direct 메시지가 아님 ({visibility})")
                return
            
            # STORY 계정에게 온 메시지인지 확인 (멘션을 통해)
            if not self.story_account_username:
                logger.error(f"알림 {notif_id}: STORY 계정 사용자명이 설정되지 않았습니다")
                return
                
            # 메시지 내용에서 STORY 계정이 멘션되었는지 확인
            story_mention = f"@{self.story_account_username}"
            if story_mention.lower() not in clean_content.lower():
                logger.debug(f"알림 {notif_id}: STORY 계정({story_mention})이 멘션되지 않음")
                return
            
            logger.debug(f"알림 {notif_id}: @{sender_username}에서 {story_mention}에게 메시지 수신")
            
            logger.info(f"알림 처리: @{sender_username} -> '{clean_content}'")
            
            # 명령어 파싱
            command = self._parse_command(clean_content, sender_username, sender_id, notif_id, toot_id)
            
            if command:
                logger.info(f"스토리 명령어 발견: {command}")
                self._execute_command(command)
            else:
                logger.debug(f"알림 {notif_id}: 스토리 명령어가 아님")
            
        except Exception as e:
            logger.error(f"알림 처리 중 오류: {e}")
    
    def _parse_command(self, content: str, sender_username: str, sender_id: str, 
                      notif_id: str, toot_id: str) -> Optional[StoryCommand]:
        """
        메시지 내용에서 스토리 명령어 파싱
        
        Args:
            content: 메시지 내용
            sender_username: 발신자 사용자명
            sender_id: 발신자 ID
            notif_id: 알림 ID
            toot_id: 툿 ID
        
        Returns:
            Optional[StoryCommand]: 파싱된 명령어, 없으면 None
        """
        try:
            # 각 명령어 패턴 확인
            for command_type, pattern in self.command_patterns.items():
                match = pattern.search(content)
                if match:
                    worksheet_name = match.group(1).strip()
                    
                    return StoryCommand(
                        command_type=command_type,
                        worksheet_name=worksheet_name,
                        sender_username=sender_username,
                        sender_id=sender_id,
                        notification_id=notif_id,
                        toot_id=toot_id,
                        timestamp=datetime.now(pytz.timezone('Asia/Seoul')),
                        is_direct=True
                    )
            
            return None
            
        except Exception as e:
            logger.error(f"명령어 파싱 중 오류: {e}")
            return None
    
    def _execute_command(self, command: StoryCommand) -> None:
        """
        스토리 명령어 실행
        
        Args:
            command: 실행할 명령어
        """
        try:
            self.stats['processed_commands'] += 1
            
            logger.info(f"명령어 실행 시작: {command}")
            
            # 명령어 타입별 처리
            if command.command_type in ['story', 'script', 'story_progress']:
                # 워크시트 검증 및 스토리 세션 시작
                success, error_message = self._start_story_session_with_validation(command.worksheet_name)
                
                if success:
                    self.stats['successful_commands'] += 1
                    logger.info(f"✅ 스토리 세션 시작 성공: {command.worksheet_name}")
                    
                else:
                    self.stats['failed_commands'] += 1
                    logger.error(f"❌ 스토리 세션 시작 실패: {command.worksheet_name}")
                    
                    # 실패 알림 전송 (멘션 포함)
                    if error_message:
                        self._send_command_response(command, error_message)
            
            else:
                logger.warning(f"알 수 없는 명령어 타입: {command.command_type}")
                self.stats['failed_commands'] += 1
            
        except Exception as e:
            logger.error(f"명령어 실행 중 오류: {e}")
            self.stats['failed_commands'] += 1
    
    def _start_story_session_with_validation(self, worksheet_name: str) -> tuple[bool, Optional[str]]:
        """
        워크시트 검증을 포함한 스토리 세션 시작
        
        Args:
            worksheet_name: 워크시트 이름
        
        Returns:
            tuple[bool, Optional[str]]: (성공 여부, 에러 메시지)
        """
        try:
            # sheets_client는 별도로 접근해야 함
            from core.sheets_client import get_sheets_manager
            sheets_client = get_sheets_manager()
            
            # 워크시트에서 스크립트 데이터 조회
            scripts = sheets_client.fetch_story_scripts_from_worksheet(worksheet_name)
            
            if not scripts:
                error_msg = f"❌ 워크시트 '{worksheet_name}'에서 스크립트를 찾을 수 없습니다. 워크시트 이름을 확인해주세요."
                return False, error_msg
            
            # 유효한 스크립트 확인
            valid_scripts = [script for script in scripts if script.is_valid]
            invalid_scripts = [script for script in scripts if not script.is_valid]
            
            if not valid_scripts:
                # 무효한 스크립트들의 문제점 요약
                error_details = []
                for script in invalid_scripts[:3]:  # 처음 3개만 표시
                    error_details.append(f"행 {script.row_index}: {script.validation_error}")
                
                error_msg = (f"❌ 워크시트 '{worksheet_name}'에 유효한 스크립트가 없습니다.\n"
                           f"문제점:\n" + "\n".join(f"  - {detail}" for detail in error_details))
                
                if len(invalid_scripts) > 3:
                    error_msg += f"\n  - ... 및 {len(invalid_scripts) - 3}개 추가 오류"
                
                return False, error_msg
            
            # 스토리 세션 시작
            success = self.story_loop_manager.start_story_session(worksheet_name)
            
            if success:
                return True, None
            else:
                error_msg = f"❌ 워크시트 '{worksheet_name}' 스토리 세션 시작에 실패했습니다."
                return False, error_msg
                
        except Exception as e:
            error_msg = f"❌ 워크시트 '{worksheet_name}' 처리 중 오류가 발생했습니다: {str(e)}"
            logger.error(f"워크시트 검증 중 오류: {e}")
            return False, error_msg

    def _send_command_response(self, command: StoryCommand, message: str) -> None:
        """
        명령어 실행 결과를 발신자에게 알림 (선택사항)
        
        Args:
            command: 원본 명령어
            message: 응답 메시지
        """
        try:
            # NOTICE 계정으로 DM 전송
            response_content = f"@{command.sender_username} {message}"
            
            result = self.mastodon_manager.post_toot(
                content=response_content,
                visibility='direct',
                account_name='NOTICE'
            )
            
            if result.success:
                logger.info(f"명령어 응답 전송 성공: {message}")
            else:
                logger.error(f"명령어 응답 전송 실패: {result.error_message}")
                
        except Exception as e:
            logger.error(f"명령어 응답 전송 중 오류: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 정보 반환"""
        return {
            **self.stats,
            'is_monitoring': self.is_monitoring,
            'processed_notifications_count': len(self.processed_notifications)
        }
    
    def get_status(self) -> str:
        """상태 문자열 반환"""
        status_lines = [
            f"📢 알림 처리기 상태",
            f"   모니터링: {'✅ 실행 중' if self.is_monitoring else '❌ 중지'}",
            f"   처리된 알림: {self.stats['total_notifications']}개",
            f"   실행된 명령어: {self.stats['processed_commands']}개",
            f"   성공/실패: {self.stats['successful_commands']}/{self.stats['failed_commands']}"
        ]
        
        if self.stats['last_check_time']:
            last_check = datetime.fromisoformat(self.stats['last_check_time'].replace('Z', '+00:00'))
            status_lines.append(f"   최근 확인: {format_datetime_korean(last_check)}")
        
        return "\n".join(status_lines)


# 전역 핸들러 인스턴스
_notification_handler: Optional[NotificationHandler] = None


def get_notification_handler() -> NotificationHandler:
    """전역 알림 처리기 반환"""
    global _notification_handler
    
    if _notification_handler is None:
        _notification_handler = NotificationHandler()
    
    return _notification_handler


if __name__ == "__main__":
    """알림 처리기 테스트"""
    print("🧪 알림 처리기 테스트 시작...")
    
    try:
        from core.mastodon_client import get_mastodon_manager
        from core.story_loop_manager import get_story_loop_manager
        from core.sheets_client import get_sheets_manager
        
        # 매니저들 초기화
        mastodon_manager = get_mastodon_manager()
        story_loop_manager = get_story_loop_manager()
        sheets_client = get_sheets_manager()
        
        # 스토리 루프 매니저 초기화
        if not story_loop_manager.initialize(sheets_client, mastodon_manager):
            print("❌ 스토리 루프 매니저 초기화 실패")
            sys.exit(1)
        
        # 알림 처리기 초기화
        handler = NotificationHandler()
        if not handler.initialize(mastodon_manager, story_loop_manager):
            print("❌ 알림 처리기 초기화 실패")
            sys.exit(1)
        
        print("✅ 알림 처리기 초기화 성공")
        
        # 모니터링 시작
        if handler.start_monitoring():
            print("✅ 알림 모니터링 시작됨")
            
            # 잠시 실행
            print("⏱️ 10초 동안 테스트 실행...")
            time.sleep(10)
            
            # 상태 확인
            print(f"📊 통계: {handler.get_stats()}")
            
            # 모니터링 중지
            handler.stop_monitoring()
            print("🛑 알림 모니터링 중지됨")
        else:
            print("❌ 알림 모니터링 시작 실패")
        
        print("🎉 테스트 완료!")
        
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
"""
스토리 스크립트 자동 출력 루프 매니저
워크시트의 스크립트를 순차적으로 자동 송출합니다.
"""

import os
import sys
import time
import asyncio
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass
import pytz

# 프로젝트 루트 경로 설정
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(current_dir)

try:
    from config.settings import config
    from utils.logging_config import get_logger
    from utils.datetime_utils import format_datetime_korean
    from core.sheets_client import GoogleSheetsClient, StoryScriptData
    from core.mastodon_client import MultiMastodonManager, TootResult
except ImportError as e:
    print(f"❌ 필수 모듈 임포트 실패: {e}")
    sys.exit(1)

logger = get_logger(__name__)


@dataclass
class StorySession:
    """
    스토리 진행 세션 정보
    """
    worksheet_name: str
    scripts: List[StoryScriptData]
    current_index: int = 0
    start_time: Optional[datetime] = None
    last_post_time: Optional[datetime] = None
    total_posts: int = 0
    is_active: bool = False
    
    def get_current_script(self) -> Optional[StoryScriptData]:
        """현재 송출할 스크립트 반환"""
        if 0 <= self.current_index < len(self.scripts):
            return self.scripts[self.current_index]
        return None
    
    def advance_to_next(self) -> bool:
        """다음 스크립트로 이동, 끝에 도달하면 False 반환"""
        self.current_index += 1
        return self.current_index < len(self.scripts)
    
    def get_progress(self) -> Dict[str, Any]:
        """진행 상황 반환"""
        return {
            'worksheet_name': self.worksheet_name,
            'current_index': self.current_index,
            'total_scripts': len(self.scripts),
            'progress_percent': (self.current_index / max(1, len(self.scripts))) * 100,
            'is_active': self.is_active,
            'total_posts': self.total_posts,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'last_post_time': self.last_post_time.isoformat() if self.last_post_time else None
        }


class StoryLoopManager:
    """
    스토리 스크립트 자동 출력 루프 매니저
    """
    
    def __init__(self):
        """StoryLoopManager 초기화"""
        self.sheets_client: Optional[GoogleSheetsClient] = None
        self.mastodon_manager: Optional[MultiMastodonManager] = None
        
        # 세션 관리
        self.active_sessions: Dict[str, StorySession] = {}
        self.session_threads: Dict[str, threading.Thread] = {}
        
        # 상태 관리
        self.is_running = False
        self._stop_event = threading.Event()
        
        # 통계
        self.stats = {
            'total_sessions': 0,
            'completed_sessions': 0,
            'total_posts': 0,
            'successful_posts': 0,
            'failed_posts': 0,
            'start_time': None
        }
        
        logger.info("스토리 루프 매니저 초기화 완료")
    
    def initialize(self, sheets_client: GoogleSheetsClient, mastodon_manager: MultiMastodonManager) -> bool:
        """
        매니저 초기화
        
        Args:
            sheets_client: Google Sheets 클라이언트
            mastodon_manager: 마스토돈 매니저
        
        Returns:
            bool: 초기화 성공 여부
        """
        try:
            self.sheets_client = sheets_client
            self.mastodon_manager = mastodon_manager
            
            # 연결 테스트
            if not self.sheets_client.service:
                if not self.sheets_client.authenticate():
                    logger.error("Google Sheets 인증 실패")
                    return False
            
            if not self.mastodon_manager.check_connection():
                logger.error("마스토돈 연결 확인 실패")
                return False
            
            logger.info("스토리 루프 매니저 초기화 성공")
            return True
            
        except Exception as e:
            logger.error(f"스토리 루프 매니저 초기화 실패: {e}")
            return False
    
    def start_story_session(self, worksheet_name: str) -> bool:
        """
        스토리 세션 시작
        
        Args:
            worksheet_name: 워크시트 이름
        
        Returns:
            bool: 세션 시작 성공 여부
        """
        try:
            # 이미 진행 중인 세션이 있는지 확인
            if worksheet_name in self.active_sessions:
                logger.warning(f"워크시트 '{worksheet_name}' 세션이 이미 진행 중입니다")
                return False
            
            logger.info(f"워크시트 '{worksheet_name}' 스토리 세션 시작...")
            
            # 워크시트에서 스크립트 데이터 조회
            scripts = self.sheets_client.fetch_story_scripts_from_worksheet(worksheet_name)
            if not scripts:
                logger.error(f"워크시트 '{worksheet_name}'에서 스크립트를 찾을 수 없습니다")
                return False
            
            # 유효한 스크립트만 필터링
            valid_scripts = [script for script in scripts if script.is_valid]
            if not valid_scripts:
                logger.error(f"워크시트 '{worksheet_name}'에 유효한 스크립트가 없습니다")
                return False
            
            logger.info(f"워크시트 '{worksheet_name}'에서 유효한 스크립트 {len(valid_scripts)}개 발견")
            
            # 세션 생성
            session = StorySession(
                worksheet_name=worksheet_name,
                scripts=valid_scripts,
                start_time=datetime.now(pytz.timezone('Asia/Seoul')),
                is_active=True
            )
            
            self.active_sessions[worksheet_name] = session
            self.stats['total_sessions'] += 1
            
            # 세션 스레드 시작
            thread = threading.Thread(
                target=self._run_story_session,
                args=(session,),
                name=f"StorySession-{worksheet_name}",
                daemon=True
            )
            
            self.session_threads[worksheet_name] = thread
            thread.start()
            
            logger.info(f"워크시트 '{worksheet_name}' 스토리 세션 시작됨")
            return True
            
        except Exception as e:
            logger.error(f"스토리 세션 시작 실패: {e}")
            return False
    
    def _run_story_session(self, session: StorySession) -> None:
        """
        스토리 세션 실행 (스레드에서 실행됨)
        
        Args:
            session: 스토리 세션
        """
        try:
            logger.info(f"스토리 세션 '{session.worksheet_name}' 실행 시작")
            
            while session.is_active and not self._stop_event.is_set():
                current_script = session.get_current_script()
                if not current_script:
                    # 모든 스크립트 송출 완료
                    logger.info(f"워크시트 '{session.worksheet_name}' 모든 스크립트 송출 완료")
                    break
                
                # 첫 번째 스크립트가 아닌 경우 현재 스크립트의 간격만큼 대기
                if session.current_index > 0 and not self._stop_event.is_set():
                    wait_time = current_script.interval
                    logger.info(f"이전 문구 송출 후 현재 문구까지 {wait_time}초 대기...")
                    
                    # 중단 신호 확인하면서 대기
                    for _ in range(wait_time):
                        if self._stop_event.is_set():
                            break
                        time.sleep(1)
                
                # 스크립트 송출
                success = self._send_script(session, current_script)
                
                if success:
                    session.total_posts += 1
                    session.last_post_time = datetime.now(pytz.timezone('Asia/Seoul'))
                    self.stats['successful_posts'] += 1
                    logger.info(f"스크립트 송출 성공: {current_script.account} - '{current_script.script[:50]}...'")
                else:
                    self.stats['failed_posts'] += 1
                    logger.error(f"스크립트 송출 실패: {current_script.account} - '{current_script.script[:50]}...'")
                
                self.stats['total_posts'] += 1
                
                # 다음 스크립트로 이동
                if not session.advance_to_next():
                    break
            
            # 세션 완료 처리
            session.is_active = False
            self.stats['completed_sessions'] += 1
            
            logger.info(f"스토리 세션 '{session.worksheet_name}' 완료 - 총 {session.total_posts}개 송출")
            
        except Exception as e:
            logger.error(f"스토리 세션 '{session.worksheet_name}' 실행 중 오류: {e}")
            session.is_active = False
        finally:
            # 세션 정리
            if session.worksheet_name in self.active_sessions:
                del self.active_sessions[session.worksheet_name]
            if session.worksheet_name in self.session_threads:
                del self.session_threads[session.worksheet_name]
    
    def _send_script(self, session: StorySession, script: StoryScriptData) -> bool:
        """
        스크립트 송출
        
        Args:
            session: 스토리 세션
            script: 송출할 스크립트
        
        Returns:
            bool: 송출 성공 여부
        """
        try:
            # 마스토돈에 툿 포스팅 (unlisted로)
            result = self.mastodon_manager.post_scheduled_toot(
                content=script.script,
                account_name=script.account,
                visibility='unlisted'  # 요구사항에 따라 unlisted로 설정
            )
            
            if result.success:
                logger.info(f"✅ {script.account} 계정으로 툿 송출 성공: {result.toot_url}")
                return True
            else:
                logger.error(f"❌ {script.account} 계정 툿 송출 실패: {result.error_message}")
                return False
                
        except Exception as e:
            logger.error(f"스크립트 송출 중 오류: {e}")
            return False
    
    def stop_story_session(self, worksheet_name: str) -> bool:
        """
        특정 스토리 세션 중지
        
        Args:
            worksheet_name: 워크시트 이름
        
        Returns:
            bool: 중지 성공 여부
        """
        try:
            if worksheet_name not in self.active_sessions:
                logger.warning(f"워크시트 '{worksheet_name}' 세션을 찾을 수 없습니다")
                return False
            
            # 세션 비활성화
            session = self.active_sessions[worksheet_name]
            session.is_active = False
            
            logger.info(f"워크시트 '{worksheet_name}' 스토리 세션 중지됨")
            return True
            
        except Exception as e:
            logger.error(f"스토리 세션 중지 실패: {e}")
            return False
    
    def stop_all_sessions(self) -> None:
        """모든 스토리 세션 중지"""
        try:
            logger.info("모든 스토리 세션 중지 시작...")
            
            # 중지 신호 설정
            self._stop_event.set()
            
            # 모든 세션 비활성화
            for session in self.active_sessions.values():
                session.is_active = False
            
            # 스레드 종료 대기
            for worksheet_name, thread in list(self.session_threads.items()):
                if thread.is_alive():
                    logger.info(f"세션 '{worksheet_name}' 종료 대기...")
                    thread.join(timeout=5.0)  # 최대 5초 대기
            
            # 정리
            self.active_sessions.clear()
            self.session_threads.clear()
            
            logger.info("모든 스토리 세션 중지 완료")
            
        except Exception as e:
            logger.error(f"세션 중지 중 오류: {e}")
    
    def get_session_status(self, worksheet_name: str) -> Optional[Dict[str, Any]]:
        """
        특정 세션 상태 조회
        
        Args:
            worksheet_name: 워크시트 이름
        
        Returns:
            Optional[Dict[str, Any]]: 세션 상태 정보
        """
        if worksheet_name in self.active_sessions:
            return self.active_sessions[worksheet_name].get_progress()
        return None
    
    def get_all_sessions_status(self) -> Dict[str, Dict[str, Any]]:
        """모든 세션 상태 조회"""
        return {
            name: session.get_progress()
            for name, session in self.active_sessions.items()
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 정보 반환"""
        active_count = len(self.active_sessions)
        
        return {
            **self.stats,
            'active_sessions': active_count,
            'session_names': list(self.active_sessions.keys()),
            'is_running': self.is_running
        }
    
    def start(self) -> None:
        """매니저 시작"""
        self.is_running = True
        self.stats['start_time'] = datetime.now(pytz.timezone('Asia/Seoul')).isoformat()
        self._stop_event.clear()
        logger.info("스토리 루프 매니저 시작됨")
    
    def stop(self) -> None:
        """매니저 중지"""
        self.is_running = False
        self.stop_all_sessions()
        logger.info("스토리 루프 매니저 중지됨")
    
    def __del__(self):
        """소멸자 - 모든 세션 정리"""
        try:
            self.stop()
        except:
            pass


# 전역 매니저 인스턴스
_story_loop_manager: Optional[StoryLoopManager] = None


def get_story_loop_manager() -> StoryLoopManager:
    """전역 스토리 루프 매니저 반환"""
    global _story_loop_manager
    
    if _story_loop_manager is None:
        _story_loop_manager = StoryLoopManager()
    
    return _story_loop_manager


if __name__ == "__main__":
    """스토리 루프 매니저 테스트"""
    print("🧪 스토리 루프 매니저 테스트 시작...")
    
    try:
        from core.sheets_client import get_sheets_manager
        from core.mastodon_client import get_mastodon_manager
        
        # 매니저 초기화
        loop_manager = StoryLoopManager()
        sheets_client = get_sheets_manager()
        mastodon_manager = get_mastodon_manager()
        
        if not loop_manager.initialize(sheets_client, mastodon_manager):
            print("❌ 매니저 초기화 실패")
            sys.exit(1)
        
        print("✅ 매니저 초기화 성공")
        
        # 워크시트 목록 조회
        worksheets = sheets_client.get_worksheet_names()
        print(f"📋 사용 가능한 워크시트: {worksheets}")
        
        # 테스트용 세션 시작 (첫 번째 워크시트)
        if worksheets:
            test_worksheet = worksheets[0]
            print(f"🚀 테스트 세션 시작: {test_worksheet}")
            
            if loop_manager.start_story_session(test_worksheet):
                print("✅ 세션 시작 성공")
                
                # 잠시 대기
                time.sleep(10)
                
                # 상태 확인
                status = loop_manager.get_session_status(test_worksheet)
                if status:
                    print(f"📊 세션 상태: {status}")
                
                # 세션 중지
                loop_manager.stop_story_session(test_worksheet)
                print("🛑 세션 중지")
            else:
                print("❌ 세션 시작 실패")
        
        print("🎉 테스트 완료!")
        
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
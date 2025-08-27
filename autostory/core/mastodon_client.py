"""
마스토돈 예약 봇 다중 계정 마스토돈 API 클라이언트
6개 마스토돈 계정을 관리하여 계정별로 툿을 포스팅합니다.
"""

import os
import sys
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
from pathlib import Path
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
    from utils.logging_config import get_logger, log_api_call, log_performance, LogContext
    from utils.datetime_utils import format_datetime_korean, format_time_until
    from utils.validators import validate_toot_content
except ImportError as e:
    print(f"❌ 필수 모듈 임포트 실패: {e}")
    sys.exit(1)

logger = get_logger(__name__)


class TootResult:
    """
    툿 포스팅 결과를 나타내는 클래스
    """
    
    def __init__(self, success: bool, account_name: str, toot_id: Optional[str] = None,
                 toot_url: Optional[str] = None, error_message: Optional[str] = None,
                 response_data: Optional[Dict] = None):
        """
        TootResult 초기화
        
        Args:
            success: 성공 여부
            account_name: 계정 이름
            toot_id: 툿 ID
            toot_url: 툿 URL
            error_message: 오류 메시지
            response_data: API 응답 데이터
        """
        self.success = success
        self.account_name = account_name
        self.toot_id = toot_id
        self.toot_url = toot_url
        self.error_message = error_message
        self.response_data = response_data
        self.timestamp = datetime.now(pytz.timezone('Asia/Seoul'))
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'success': self.success,
            'account_name': self.account_name,
            'toot_id': self.toot_id,
            'toot_url': self.toot_url,
            'error_message': self.error_message,
            'timestamp': self.timestamp.isoformat(),
            'response_data': self.response_data
        }
    
    def __str__(self) -> str:
        """문자열 표현"""
        if self.success:
            return f"✅ {self.account_name} 툿 포스팅 성공: {self.toot_url or self.toot_id}"
        else:
            return f"❌ {self.account_name} 툿 포스팅 실패: {self.error_message}"


class MastodonAccountClient:
    """
    개별 마스토돈 계정 클라이언트
    """
    
    def __init__(self, account_name: str, account_config: Dict[str, str]):
        """
        MastodonAccountClient 초기화
        
        Args:
            account_name: 계정 이름 (동적으로 설정된 계정)
            account_config: 계정 설정 (access_token)
        """
        self.account_name = account_name
        self.account_config = account_config
        self.instance_url = config.MASTODON_INSTANCE_URL
        
        # API 클라이언트
        self.mastodon = None
        self.last_request_time = 0
        self.min_interval = 1.0  # 최소 요청 간격 (초)
        
        # 봇 정보 캐시
        self._bot_info = None
        self._bot_info_cache_time = None
        self._bot_info_cache_duration = 3600  # 1시간
        
        logger.info(f"마스토돈 계정 클라이언트 초기화: {account_name}")
    
    def _initialize_client(self) -> bool:
        """마스토돈 클라이언트 초기화"""
        try:
            if self.mastodon is not None:
                return True
            
            self.mastodon = Mastodon(
                access_token=self.account_config['access_token'],
                api_base_url=self.instance_url,
                request_timeout=30
            )
            
            logger.debug(f"{self.account_name} 마스토돈 클라이언트 초기화 완료")
            return True
            
        except Exception as e:
            logger.error(f"{self.account_name} 마스토돈 클라이언트 초기화 실패: {e}")
            return False
    
    def _wait_if_needed(self) -> None:
        """필요시 대기하여 API 제한 준수"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_interval:
            wait_time = self.min_interval - time_since_last
            logger.debug(f"{self.account_name} API 제한으로 {wait_time:.1f}초 대기 중...")
            time.sleep(wait_time)
        
        self.last_request_time = time.time()
    
    def check_connection(self) -> bool:
        """마스토돈 연결 상태 확인"""
        try:
            if not self._initialize_client():
                return False
            
            self._wait_if_needed()
            
            # 계정 정보 조회로 연결 테스트
            account_info = self.mastodon.me()
            logger.debug(f"{self.account_name} 연결 확인 성공: @{account_info.get('username', 'unknown')}")
            return True
            
        except Exception as e:
            logger.error(f"{self.account_name} 연결 확인 실패: {e}")
            return False
    
    def get_bot_info(self) -> Optional[Dict[str, Any]]:
        """봇 정보 조회 (캐시 지원)"""
        try:
            current_time = time.time()
            
            # 캐시된 정보가 유효한지 확인
            if (self._bot_info and self._bot_info_cache_time and 
                current_time - self._bot_info_cache_time < self._bot_info_cache_duration):
                return self._bot_info
            
            if not self._initialize_client():
                return None
            
            self._wait_if_needed()
            
            # 계정 정보 조회
            account_info = self.mastodon.me()
            
            self._bot_info = {
                'account_name': self.account_name,
                'id': account_info.get('id'),
                'username': account_info.get('username'),
                'display_name': account_info.get('display_name'),
                'followers_count': account_info.get('followers_count', 0),
                'following_count': account_info.get('following_count', 0),
                'statuses_count': account_info.get('statuses_count', 0),
                'created_at': account_info.get('created_at'),
                'note': account_info.get('note', ''),
                'url': account_info.get('url'),
                'avatar': account_info.get('avatar'),
                'header': account_info.get('header'),
                'locked': account_info.get('locked', False),
                'bot': account_info.get('bot', False)
            }
            
            self._bot_info_cache_time = current_time
            logger.debug(f"{self.account_name} 봇 정보 조회 성공")
            
            return self._bot_info
            
        except Exception as e:
            logger.error(f"{self.account_name} 봇 정보 조회 실패: {e}")
            return None
    
    @log_api_call
    def post_toot(self, content: str, visibility: str = 'public', 
                  validate_content: bool = True) -> TootResult:
        """
        툿 포스팅
        
        Args:
            content: 툿 내용
            visibility: 가시성 ('public', 'direct', 'private', 'direct')
            validate_content: 내용 검증 여부
        
        Returns:
            TootResult: 포스팅 결과
        """
        try:
            # 내용 검증
            if validate_content:
                validation_result = validate_toot_content(content)
                if not validation_result.is_valid:
                    return TootResult(
                        success=False,
                        account_name=self.account_name,
                        error_message=f"내용 검증 실패: {validation_result.error_message}"
                    )
            
            if not self._initialize_client():
                return TootResult(
                    success=False,
                    account_name=self.account_name,
                    error_message="마스토돈 클라이언트 초기화 실패"
                )
            
            self._wait_if_needed()
            
            # 툿 포스팅
            result = self.mastodon.status_post(
                status=content,
                visibility=visibility
            )
            
            # 결과 처리
            toot_id = result.get('id')
            toot_url = result.get('url')
            
            logger.info(f"{self.account_name} 툿 포스팅 성공: {toot_id}")
            
            return TootResult(
                success=True,
                account_name=self.account_name,
                toot_id=str(toot_id),
                toot_url=toot_url,
                response_data=result
            )
            
        except MastodonAPIError as e:
            error_msg = f"API 오류: {e}"
            logger.error(f"{self.account_name} {error_msg}")
            return TootResult(
                success=False,
                account_name=self.account_name,
                error_message=error_msg
            )
            
        except MastodonNetworkError as e:
            error_msg = f"네트워크 오류: {e}"
            logger.error(f"{self.account_name} {error_msg}")
            return TootResult(
                success=False,
                account_name=self.account_name,
                error_message=error_msg
            )
            
        except Exception as e:
            error_msg = f"예상치 못한 오류: {e}"
            logger.error(f"{self.account_name} {error_msg}")
            return TootResult(
                success=False,
                account_name=self.account_name,
                error_message=error_msg
            )


class MultiMastodonManager:
    """
    다중 마스토돈 계정 관리자
    6개 계정을 관리하여 계정별로 툿을 포스팅합니다.
    """
    
    def __init__(self):
        """MultiMastodonManager 초기화"""
        self.clients: Dict[str, MastodonAccountClient] = {}
        self.stats = {
            'total_posts': 0,
            'successful_posts': 0,
            'failed_posts': 0,
            'posts_by_account': {},
            'last_post_time': None
        }
        
        # 계정별 클라이언트 초기화
        for account_name, account_config in config.MASTODON_ACCOUNTS.items():
            self.clients[account_name] = MastodonAccountClient(account_name, account_config)
            self.stats['posts_by_account'][account_name] = {
                'total': 0,
                'successful': 0,
                'failed': 0,
                'last_post': None
            }
        
        logger.info(f"다중 마스토돈 매니저 초기화: {len(self.clients)}개 계정")
    
    def get_available_accounts(self) -> List[str]:
        """사용 가능한 계정 목록 반환"""
        return list(self.clients.keys())
    
    def check_account_connection(self, account_name: str) -> bool:
        """특정 계정 연결 상태 확인"""
        if account_name not in self.clients:
            logger.error(f"존재하지 않는 계정: {account_name}")
            return False
        
        return self.clients[account_name].check_connection()
    
    def check_all_connections(self) -> Dict[str, bool]:
        """모든 계정 연결 상태 확인"""
        results = {}
        for account_name in self.clients:
            results[account_name] = self.check_account_connection(account_name)
        return results
    
    def get_account_info(self, account_name: str) -> Optional[Dict[str, Any]]:
        """특정 계정 정보 조회"""
        if account_name not in self.clients:
            logger.error(f"존재하지 않는 계정: {account_name}")
            return None
        
        return self.clients[account_name].get_bot_info()
    
    def get_all_account_info(self) -> Dict[str, Optional[Dict[str, Any]]]:
        """모든 계정 정보 조회"""
        results = {}
        for account_name in self.clients:
            results[account_name] = self.get_account_info(account_name)
        return results
    
    def post_scheduled_toot(self, content: str, account_name: str, 
                           scheduled_at: Optional[datetime] = None,
                           visibility: str = 'public') -> TootResult:
        """
        예약 툿 포스팅 (지정된 계정으로)
        
        Args:
            content: 툿 내용
            account_name: 계정 이름
            scheduled_at: 예약 시간 (현재는 무시됨 - 즉시 포스팅)
            visibility: 가시성
        
        Returns:
            TootResult: 포스팅 결과
        """
        if account_name not in self.clients:
            error_msg = f"존재하지 않는 계정: {account_name}. 사용 가능한 계정: {list(self.clients.keys())}"
            logger.error(error_msg)
            return TootResult(
                success=False,
                account_name=account_name,
                error_message=error_msg
            )
        
        # 통계 업데이트
        self.stats['total_posts'] += 1
        self.stats['posts_by_account'][account_name]['total'] += 1
        
        # 툿 포스팅
        result = self.clients[account_name].post_toot(
            content=content,
            visibility=visibility
        )
        
        # 결과에 따른 통계 업데이트
        current_time = datetime.now(pytz.timezone('Asia/Seoul'))
        
        if result.success:
            self.stats['successful_posts'] += 1
            self.stats['posts_by_account'][account_name]['successful'] += 1
            self.stats['last_post_time'] = current_time.isoformat()
            self.stats['posts_by_account'][account_name]['last_post'] = current_time.isoformat()
            
            logger.info(f"✅ {account_name} 계정으로 툿 포스팅 성공")
        else:
            self.stats['failed_posts'] += 1
            self.stats['posts_by_account'][account_name]['failed'] += 1
            
            logger.error(f"❌ {account_name} 계정 툿 포스팅 실패: {result.error_message}")
        
        return result
    
    def post_toot(self, content: str, visibility: str = 'direct', 
                  validate_content: bool = False, account_name: Optional[str] = None) -> TootResult:
        """
        일반 툿 포스팅 (시스템 알림용, 기본적으로 DEFAULT_ACCOUNT 사용)
        
        Args:
            content: 툿 내용
            visibility: 가시성
            validate_content: 내용 검증 여부
            account_name: 계정 이름 (동적으로 설정된 계정)
        
        Returns:
            TootResult: 포스팅 결과
        """
        # 기본 계정 사용
        if account_name is None:
            account_name = config.DEFAULT_ACCOUNT
            
        return self.post_scheduled_toot(
            content=content,
            account_name=account_name,
            visibility=visibility
        )
    
    def get_bot_info(self) -> Optional[Dict[str, Any]]:
        """기본 계정 정보 반환 (하위 호환성)"""
        return self.get_account_info(config.DEFAULT_ACCOUNT)
    
    def check_connection(self) -> bool:
        """하나 이상의 계정이 연결되어 있는지 확인 (하위 호환성)"""
        connections = self.check_all_connections()
        return any(connections.values())
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 정보 반환"""
        return {
            **self.stats,
            'accounts': list(self.clients.keys()),
            'connections': self.check_all_connections()
        }
    
    def get_status_summary(self) -> str:
        """상태 요약 문자열 반환"""
        connections = self.check_all_connections()
        connected_count = sum(connections.values())
        total_count = len(connections)
        
        summary_lines = [
            f"📊 다중 마스토돈 매니저 상태",
            f"   연결된 계정: {connected_count}/{total_count}",
            f"   총 포스팅: {self.stats['total_posts']}개",
            f"   성공률: {(self.stats['successful_posts']/max(1, self.stats['total_posts'])*100):.1f}%"
        ]
        
        if self.stats['last_post_time']:
            last_post = datetime.fromisoformat(self.stats['last_post_time'].replace('Z', '+00:00'))
            summary_lines.append(f"   최근 포스팅: {format_datetime_korean(last_post)}")
        
        return "\n".join(summary_lines)


# 전역 매니저 인스턴스
_mastodon_manager: Optional[MultiMastodonManager] = None


def get_mastodon_manager() -> MultiMastodonManager:
    """전역 마스토돈 매니저 반환"""
    global _mastodon_manager
    
    if _mastodon_manager is None:
        _mastodon_manager = MultiMastodonManager()
    
    return _mastodon_manager


def check_mastodon_connection() -> bool:
    """마스토돈 연결 상태 확인"""
    manager = get_mastodon_manager()
    return manager.check_connection()


def send_system_notification(message: str, visibility: str = 'direct') -> TootResult:
    """시스템 알림 전송 (기본 계정 사용)"""
    manager = get_mastodon_manager()
    return manager.post_toot(
        content=message,
        visibility=visibility,
        validate_content=False,
        account_name=config.DEFAULT_ACCOUNT
    )


if __name__ == "__main__":
    """다중 마스토돈 클라이언트 테스트"""
    print("🧪 다중 마스토돈 클라이언트 테스트 시작...")
    
    try:
        # 매니저 초기화
        manager = MultiMastodonManager()
        print(f"✅ 매니저 초기화 완료: {len(manager.clients)}개 계정")
        
        # 연결 테스트
        print("\n📡 계정별 연결 테스트...")
        connections = manager.check_all_connections()
        for account_name, is_connected in connections.items():
            status = "✅ 연결됨" if is_connected else "❌ 연결 실패"
            print(f"   {account_name}: {status}")
        
        # 계정 정보 조회
        print("\n👤 계정 정보 조회...")
        all_info = manager.get_all_account_info()
        for account_name, info in all_info.items():
            if info:
                print(f"   {account_name}: @{info['username']} ({info['statuses_count']}툿)")
            else:
                print(f"   {account_name}: 정보 조회 실패")
        
        # 상태 요약
        print(f"\n{manager.get_status_summary()}")
        
        print("\n🎉 테스트 완료!")
        
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
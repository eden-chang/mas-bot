"""
스트림 핸들러 - 개선된 버전 (사용자 멘션 포함)
마스토돈 스트리밍 이벤트를 처리하고 명령어 라우터와 연동하는 모듈입니다.
모든 응답에 사용자 멘션(@사용자명)을 포함합니다.
과제 명령어를 위한 답글 컨텍스트 지원 추가.
"""

import os
import sys
import time
from typing import Optional, Tuple, Any, List, Dict
from bs4 import BeautifulSoup
from utils.dm_sender import DMSender, initialize_dm_sender

# 경로 설정 (VM 환경 대응)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    import mastodon
    from config.settings import config
    from utils.logging_config import logger, bot_logger, LogContext
    from utils.sheets_operations import SheetsManager
    from handlers.command_router import ModernCommandRouter, parse_command_from_text, validate_command_format
    from models.command_result import CommandResult, CommandType
    from utils.api_retry import api_retry
    IMPORTS_AVAILABLE = True
except ImportError as e:
    # VM 환경에서 임포트 실패 시 폴백
    import logging
    logger = logging.getLogger('stream_handler')
    logger.warning(f"모듈 임포트 실패: {e}")
    
    # 마스토돈 더미 클래스
    class StreamListener:
        pass
    
    IMPORTS_AVAILABLE = False


class HTMLCleaner:
    """HTML 처리 유틸리티 (중복 제거)"""
    
    @staticmethod
    def extract_text(html_content: str) -> str:
        """
        HTML 태그 제거하여 텍스트 추출
        
        Args:
            html_content: HTML 콘텐츠
            
        Returns:
            str: 순수 텍스트
        """
        if not html_content:
            return ""
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            return soup.get_text(separator=' ', strip=True)
        except Exception as e:
            logger.warning(f"HTML 파싱 오류: {e}")
            return html_content
    
    @staticmethod
    def extract_mentions(html_content: str) -> List[str]:
        """
        HTML에서 멘션 사용자 추출
        
        Args:
            html_content: HTML 콘텐츠
            
        Returns:
            List[str]: 추출된 사용자 ID 목록
        """
        mentions = []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            mention_links = soup.find_all('a', class_='mention')
            
            for link in mention_links:
                href = link.get('href', '')
                # href에서 사용자 ID 추출 (예: https://instance.com/@username)
                if '@' in href:
                    user_id = href.split('@')[-1]
                    if user_id:
                        mentions.append(user_id)
        except Exception as e:
            logger.warning(f"HTML 멘션 추출 실패: {e}")
        
        return mentions


class MentionManager:
    """멘션 관리 유틸리티 (길이 초과 방지)"""
    
    MAX_MENTION_LENGTH = 100  # 멘션 문자열 최대 길이
    MAX_USERS_TO_MENTION = 5  # 최대 멘션할 사용자 수
    
    @staticmethod
    def format_mentions(mentioned_users: List[str]) -> str:
        """
        멘션 문자열 포맷 (길이 초과 방지)
        
        Args:
            mentioned_users: 멘션할 사용자 목록
            
        Returns:
            str: 포맷된 멘션 문자열
        """
        if not mentioned_users:
            return ""
        
        # 사용자 수 제한
        users_to_mention = mentioned_users[:MentionManager.MAX_USERS_TO_MENTION]
        mentions = ' '.join([f"@{user}" for user in users_to_mention])
        
        # 길이 제한 확인
        if len(mentions) > MentionManager.MAX_MENTION_LENGTH:
            # 길이 초과 시 사용자 수 줄이기
            truncated_users = []
            current_length = 0
            
            for user in users_to_mention:
                mention = f"@{user}"
                if current_length + len(mention) + 1 > MentionManager.MAX_MENTION_LENGTH - 10:  # 여유 공간
                    break
                truncated_users.append(user)
                current_length += len(mention) + 1
            
            if truncated_users:
                mentions = ' '.join([f"@{user}" for user in truncated_users])
                excluded_count = len(mentioned_users) - len(truncated_users)
                if excluded_count > 0:
                    mentions += f" 외 {excluded_count}명"
            else:
                # 한 명도 포함할 수 없는 경우
                mentions = f"@{mentioned_users[0][:10]}... 외 {len(mentioned_users)-1}명"
        
        return mentions


class BotStreamHandler(mastodon.StreamListener):
    """
    마스토돈 스트리밍 이벤트를 처리하는 핸들러 - 개선된 버전
    
    개선된 기능:
    - ModernCommandRouter 사용
    - 통계 기능 제거 (불필요한 복잡성 제거)
    - HTML 처리 통합
    - 멘션 길이 초과 방지
    - 구조화된 에러 처리
    - 모든 응답에 사용자 멘션 포함
    - 과제 명령어를 위한 답글 컨텍스트 지원
    """
    
    def __init__(self, api: mastodon.Mastodon, sheets_manager: SheetsManager):
        """
        BotStreamHandler 초기화
        
        Args:
            api: 마스토돈 API 객체
            sheets_manager: Google Sheets 관리자
        """
        super().__init__()
        self.api = api
        self.sheets_manager = sheets_manager
        
        # 의존성 확인
        if not IMPORTS_AVAILABLE:
            logger.error("필수 의존성 임포트 실패 - 제한된 모드로 실행")
            self.command_router = None
            self.dm_sender = None
        else:
            # ModernCommandRouter 사용 (기존 CommandRouter 대신)
            self.command_router = ModernCommandRouter(sheets_manager, api)
            # DM 전송기 초기화
            self.dm_sender = initialize_dm_sender(api)
        
        logger.info("BotStreamHandler 초기화 완료 (DM 전송기 포함, 멘션 응답, 과제 컨텍스트 지원)")
    
    def on_notification(self, notification) -> None:
        """
        알림 이벤트 처리
        
        Args:
            notification: 마스토돈 알림 객체
        """
        try:
            # 멘션만 처리
            if notification.type != 'mention':
                return
            
            with LogContext("멘션 처리", notification_id=notification.id):
                self._process_mention(notification)
                
        except Exception as e:
            logger.error(f"알림 처리 중 예상치 못한 오류: {e}", exc_info=True)
            
            # 사용자에게 오류 메시지 전송 시도
            try:
                self._send_error_response(notification, "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")
            except Exception as send_error:
                logger.error(f"오류 응답 전송 실패: {send_error}")
    
    def _process_mention(self, notification) -> None:
        """
        멘션 처리 (과제 컨텍스트 지원 추가)
        
        Args:
            notification: 마스토돈 알림 객체
        """
        # 기본 정보 추출
        status = notification.status
        user_id = status.account.acct
        visibility = getattr(status, 'visibility', 'public')
        content = status.content
        
        # HTML 태그 제거하여 텍스트 추출
        text_content = HTMLCleaner.extract_text(content)
        
        # 명령어 형식 검증
        if not self._has_command_format(text_content):
            logger.debug(f"명령어 형식 없음: {user_id}")
            return
        
        # 명령어 추출
        keywords = parse_command_from_text(text_content)
        if not keywords:
            logger.debug(f"명령어 추출 실패: {user_id}")
            return
        
        # 대화 참여자 추출 (봇 제외)
        mentioned_users = self._extract_mentioned_users(status)
        
        # 답글 컨텍스트 생성 (과제 명령어용)
        context = self._create_command_context(status, notification)
        
        # 명령어 실행 (컨텍스트 포함)
        command_result = self._execute_command(user_id, keywords, context)
        
        # 응답 전송 (모든 참여자 멘션 포함)
        self._send_response(notification, command_result, visibility, mentioned_users)
    
    def _create_command_context(self, status, notification) -> Dict[str, Any]:
        """
        명령어 실행을 위한 컨텍스트 생성
        
        Args:
            status: 마스토돈 status 객체
            notification: 마스토돈 notification 객체
            
        Returns:
            Dict[str, Any]: 명령어 컨텍스트
        """
        # 원본 텍스트 추출
        content = status.content
        original_text = HTMLCleaner.extract_text(content)
        
        context = {
            'status_id': status.id,
            'user_id': status.account.acct,
            'user_name': getattr(status.account, 'display_name', status.account.acct),
            'visibility': getattr(status, 'visibility', 'public'),
            'notification': notification,
            'original_status': status,
            'original_text': original_text
        }
        
        # 답글인 경우 원본 툿 ID 추가
        if hasattr(status, 'in_reply_to_id') and status.in_reply_to_id:
            context['reply_to_id'] = status.in_reply_to_id
            context['is_reply'] = True
            logger.debug(f"답글 컨텍스트 생성: {status.id} -> {status.in_reply_to_id}")
        else:
            context['is_reply'] = False
        
        return context
    
    def _extract_mentioned_users(self, status) -> List[str]:
        """
        툿에서 멘션된 사용자들 추출 (봇 제외, 개선된 버전)
        
        Args:
            status: 마스토돈 status 객체
            
        Returns:
            List[str]: 멘션된 사용자 ID 목록 (봇 제외)
        """
        mentioned_users = []
        
        try:
            # 1. mentions 속성에서 추출 (가장 정확함)
            if hasattr(status, 'mentions') and status.mentions:
                for mention in status.mentions:
                    user_acct = mention.get('acct', '')
                    if user_acct and not self._is_bot_account(user_acct):
                        mentioned_users.append(user_acct)
            
            # 2. mentions가 없는 경우 HTML에서 파싱 (통합된 방식 사용)
            else:
                html_mentions = HTMLCleaner.extract_mentions(status.content)
                for user_id in html_mentions:
                    if user_id and not self._is_bot_account(user_id):
                        mentioned_users.append(user_id)
            
            # 3. 원작성자도 포함 (자신이 아닌 경우)
            author_acct = status.account.acct
            if author_acct and not self._is_bot_account(author_acct) and author_acct not in mentioned_users:
                mentioned_users.append(author_acct)
            
            # 중복 제거 및 정렬
            mentioned_users = list(set(mentioned_users))
            mentioned_users.sort()
            
            logger.debug(f"추출된 멘션 사용자: {mentioned_users}")
            
        except Exception as e:
            logger.warning(f"멘션 사용자 추출 실패: {e}")
            # 실패 시 최소한 원작성자는 포함
            author_acct = status.account.acct
            if author_acct and not self._is_bot_account(author_acct):
                mentioned_users = [author_acct]
        
        return mentioned_users
    
    @api_retry(max_retries=3, delay_seconds=60)
    def _is_bot_account(self, user_acct: str) -> bool:
        """
        봇 계정 여부 확인
        
        Args:
            user_acct: 사용자 계정명
            
        Returns:
            bool: 봇 계정 여부
        """
        try:
            # 현재 봇의 계정 정보 가져오기
            bot_info = self.api.me()
            bot_acct = bot_info.get('acct', bot_info.get('username', ''))
            
            return user_acct == bot_acct
        except Exception as e:
            logger.warning(f"봇 계정 확인 실패: {e}")
            # 실패 시 안전하게 False 반환
            return False
    
    def _has_command_format(self, text: str) -> bool:
        """
        텍스트에 명령어 형식이 있는지 확인
        
        Args:
            text: 확인할 텍스트
            
        Returns:
            bool: 명령어 형식 포함 여부
        """
        if not text:
            return False
        
        # [] 패턴 확인
        if '[' not in text or ']' not in text:
            return False
        
        # [] 위치 확인
        start_pos = text.find('[')
        end_pos = text.find(']')
        
        return start_pos < end_pos
    
    def _execute_command(self, user_id: str, keywords: list, context: Dict[str, Any] = None) -> 'CommandResult':
        """
        명령어 실행 (컨텍스트 지원)
        
        Args:
            user_id: 사용자 ID
            keywords: 키워드 리스트
            context: 명령어 실행 컨텍스트
            
        Returns:
            CommandResult: 실행 결과
        """
        start_time = time.time()
        
        try:
            # 의존성 확인
            if not self.command_router:
                return self._create_fallback_error_result(
                    user_id, keywords, "명령어 시스템이 초기화되지 않았습니다. 관리자에게 문의해주세요."
                )
            
            # 명령어 라우터를 통한 실행 (컨텍스트 포함)
            result = self.command_router.route_command(user_id, keywords, context)
            
            execution_time = time.time() - start_time
            
            # 실행 시간 로깅 (bot_logger가 있는 경우만)
            try:
                bot_logger.log_command_execution(
                    user_id=user_id,
                    command=f"[{'/'.join(keywords)}]",
                    result=result.get_user_message(),
                    success=result.is_successful()
                )
            except:
                pass  # bot_logger 실패 시 무시
            
            # 과제 명령어인 경우 추가 로깅
            if keywords and keywords[0] == '과제참여':
                reply_info = ""
                if context and context.get('is_reply'):
                    reply_info = f" (답글: {context.get('reply_to_id')})"
                logger.info(f"과제 명령어 실행: {user_id} | {keywords}{reply_info}")
            
            if execution_time > 5.0:  # 5초 이상 걸린 경우 경고
                logger.warning(f"느린 명령어 실행: {keywords} - {execution_time:.2f}초")
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"명령어 실행 중 오류: {keywords} - {e}")
            
            # 오류 결과 생성
            return self._create_fallback_error_result(user_id, keywords, str(e), execution_time)
    
    def _create_fallback_error_result(self, user_id: str, keywords: list, error_msg: str, execution_time: float = 0.0):
        """폴백 에러 결과 생성"""
        if IMPORTS_AVAILABLE:
            try:
                return CommandResult.error(
                    command_type=CommandType.UNKNOWN,
                    user_id=user_id,
                    user_name=user_id,
                    original_command=f"[{'/'.join(keywords)}]",
                    error=Exception(error_msg),
                    execution_time=execution_time
                )
            except:
                pass
        
        # 완전 폴백
        class FallbackErrorResult:
            def __init__(self, message: str):
                self.message = message
            
            def is_successful(self):
                return False
            
            def get_user_message(self):
                return self.message
        
        return FallbackErrorResult(f"명령어 처리 중 오류: {error_msg}")
    
    def _send_response(self, notification, command_result, visibility: str, mentioned_users: List[str]) -> None:
        """
        명령어 결과에 따른 응답 전송 (모든 참여자 멘션 포함, 길이 초과 방지)
        
        Args:
            notification: 마스토돈 알림 객체
            command_result: 명령어 실행 결과
            visibility: 공개 범위
            mentioned_users: 멘션할 사용자 목록
        """
        try:
            original_status_id = notification.status.id
            
            # 모든 참여자 멘션 생성 (길이 초과 방지)
            mentions = MentionManager.format_mentions(mentioned_users)
            
            # 실패한 경우 단순 오류 메시지 전송
            if not command_result.is_successful():
                formatted_message = config.format_response(command_result.get_user_message())
                full_message = f"{mentions} {formatted_message}"
                self._send_status_with_retry(
                    status=full_message,
                    in_reply_to_id=original_status_id,
                    visibility=visibility
                )
                logger.info(f"오류 응답 전송: {mentioned_users}")
                return
            
            # 성공한 경우 메시지 길이에 따라 처리
            formatted_message = config.format_response(command_result.get_user_message())
            full_message = f"{mentions} {formatted_message}"
            message_length = len(full_message)
            
            if message_length <= 490:
                # 짧은 메시지: 단일 답장
                self._send_status_with_retry(
                    status=full_message,
                    in_reply_to_id=original_status_id,
                    visibility=visibility
                )
                logger.info(f"단일 응답 전송: {mentioned_users} ({message_length}자)")
                
            else:
                # 긴 메시지: 스레드 답장
                logger.info(f"긴 메시지 감지: {mentioned_users} ({message_length}자), 스레드로 전송")
                
                # 메시지 분할 및 전송
                sent_statuses = self._send_threaded_response(
                    original_status_id, 
                    command_result, 
                    visibility,
                    mentions
                )
                
                logger.info(f"스레드 응답 완료: {mentioned_users}, {len(sent_statuses)}개 툿 전송")
        
        except Exception as e:
            logger.error(f"응답 전송 실패: {mentioned_users} - {e}")
            
            try:
                mentions = MentionManager.format_mentions(mentioned_users)
                formatted_error = config.format_response("응답 처리 중 오류가 발생했습니다.")
                self.api.status_post(
                    in_reply_to_id=notification.status.id,
                    status=f"{mentions} {formatted_error}",
                    visibility=visibility
                )
            except Exception as fallback_error:
                logger.error(f"오류 메시지 전송도 실패: {fallback_error}")
    
    def _send_threaded_response(self, original_status_id: str, command_result, visibility: str, mentions: str) -> List[Dict]:
        """
        스레드 형태로 긴 응답 전송 (첫 번째 툿에만 멘션 포함)
        
        Args:
            original_status_id: 원본 툿 ID
            command_result: 명령어 결과
            visibility: 공개 범위
            mentions: 멘션 문자열 (@user1 @user2 ...)
            
        Returns:
            List[Dict]: 전송된 툿들의 정보
        """
        try:
            # 메시지 분할기 import
            from utils.message_chunking import MessageChunker
            
            chunker = MessageChunker(max_length=430)
            chunks = []
            
            # 결과 타입별 특별 처리
            if hasattr(command_result, 'result_data') and command_result.result_data:
                result_data = command_result.result_data
                
                # 상점 결과
                if hasattr(result_data, 'items') and hasattr(result_data, 'currency_unit'):
                    chunks = chunker.split_shop_items(result_data.items, result_data.currency_unit)
                
                # 인벤토리 결과
                elif hasattr(result_data, 'inventory') and hasattr(result_data, 'user_name'):
                    chunks = chunker.split_inventory_items(
                        result_data.inventory, 
                        result_data.user_name, 
                        getattr(result_data, 'suffix', '')
                    )
                
                # 기타 결과
                else:
                    chunks = chunker.split_message(command_result.get_user_message())
            else:
                # 기본 메시지 분할
                chunks = chunker.split_message(command_result.get_user_message())
            
            # 청크들을 순차적으로 전송
            sent_statuses = []
            reply_to_id = original_status_id
            
            for i, chunk in enumerate(chunks):
                try:
                    logger.debug(f"청크 {i+1}/{len(chunks)} 전송 중... ({len(chunk)}자)")
                    
                    formatted_chunk = config.format_response(chunk)
                    # 첫 번째 청크에만 멘션 포함
                    if i == 0:
                        full_chunk = f"{mentions} {formatted_chunk}"
                    else:
                        full_chunk = formatted_chunk
                    
                    status = self._send_status_with_retry(
                        status=full_chunk,
                        in_reply_to_id=reply_to_id,
                        visibility=visibility
                    )
                    
                    sent_statuses.append(status)
                    reply_to_id = status['id']  # 다음 답장은 방금 보낸 툿에 연결
                    
                    # API 제한 고려하여 대기 (마지막 제외)
                    if i < len(chunks) - 1:
                        time.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"청크 {i+1} 전송 실패: {e}")
                    break
            
            return sent_statuses
            
        except Exception as e:
            logger.error(f"스레드 응답 전송 실패: {e}")
            return []
    
    def process_pending_dms(self) -> Dict[str, int]:
        """
        대기 중인 DM들을 처리
        
        Returns:
            Dict: 처리 결과
        """
        try:
            if self.dm_sender:
                return self.dm_sender.process_pending_dms()
            return {'processed': 0, 'success': 0, 'failed': 0, 'retries': 0}
        except Exception as e:
            logger.error(f"DM 처리 실패: {e}")
            return {'processed': 0, 'success': 0, 'failed': 0, 'retries': 0}
    
    def _send_error_response(self, notification, error_message: str) -> None:
        """
        오류 응답 전송 (모든 참여자 멘션 포함)
        
        Args:
            notification: 원본 알림
            error_message: 오류 메시지
        """
        try:
            status = notification.status
            visibility = getattr(status, 'visibility', 'public')
            
            # 모든 참여자 추출
            mentioned_users = self._extract_mentioned_users(status)
            mentions = MentionManager.format_mentions(mentioned_users)
            
            formatted_message = config.format_response(error_message)
            self._send_status_with_retry(
                status=f"{mentions} {formatted_message}",
                in_reply_to_id=status.id,
                visibility=visibility
            )
            
        except Exception as e:
            logger.error(f"오류 응답 전송 실패: {e}")
    
    def health_check(self) -> dict:
        """
        핸들러 상태 확인 (통계 기능 제거, DM 상태 포함)
        
        Returns:
            dict: 상태 정보
        """
        health_status = {
            'status': 'healthy',
            'errors': [],
            'warnings': []
        }
        
        try:
            # 기본 의존성 확인
            if not IMPORTS_AVAILABLE:
                health_status['errors'].append("필수 의존성 임포트 실패")
                health_status['status'] = 'error'
                return health_status
            
            # API 연결 상태 확인
            if not self.api:
                health_status['errors'].append("마스토돈 API 객체 없음")
                health_status['status'] = 'error'
            
            # Sheets 관리자 상태 확인
            if not self.sheets_manager:
                health_status['errors'].append("Sheets 관리자 없음")
                health_status['status'] = 'error'
            
            # 명령어 라우터 상태 확인
            if not self.command_router:
                health_status['errors'].append("명령어 라우터 없음")
                health_status['status'] = 'error'
            else:
                # 라우터 검증
                try:
                    validation = self.command_router.validate_all_systems()
                    if not validation.get('overall_valid', True):
                        health_status['warnings'].append("일부 명령어에 문제가 있습니다")
                        if health_status['status'] == 'healthy':
                            health_status['status'] = 'warning'
                except Exception as e:
                    health_status['warnings'].append(f"명령어 검증 실패: {str(e)}")
            
            # DM 전송기 상태 확인
            if not self.dm_sender:
                health_status['warnings'].append("DM 전송기 없음")
                if health_status['status'] == 'healthy':
                    health_status['status'] = 'warning'
            else:
                # DM 전송기 상세 상태 확인
                try:
                    dm_health = self.dm_sender.health_check()
                    if dm_health['status'] != 'healthy':
                        health_status['warnings'].extend(dm_health.get('warnings', []))
                        health_status['errors'].extend(dm_health.get('errors', []))
                        
                        if dm_health['status'] == 'error':
                            health_status['status'] = 'error'
                        elif dm_health['status'] == 'warning' and health_status['status'] == 'healthy':
                            health_status['status'] = 'warning'
                except Exception as e:
                    health_status['warnings'].append(f"DM 전송기 상태 확인 실패: {str(e)}")
            
            # DM 관련 경고 확인
            if self.dm_sender:
                try:
                    pending_dms = self.dm_sender.get_pending_count()
                    if pending_dms > 10:  # 대기 중인 DM이 10개 이상
                        health_status['warnings'].append(f"대기 중인 DM이 많습니다: {pending_dms}개")
                        if health_status['status'] == 'healthy':
                            health_status['status'] = 'warning'
                    
                    # DM 실패율 확인
                    dm_stats = self.dm_sender.get_stats()
                    if dm_stats.get('total_sent', 0) > 5:  # 최소 5개 이상 전송한 경우
                        dm_failure_rate = (dm_stats.get('failed_sent', 0) / dm_stats.get('total_sent', 1)) * 100
                        if dm_failure_rate > 30:  # 30% 이상 실패율
                            health_status['warnings'].append(f"DM 높은 실패율: {dm_failure_rate:.1f}%")
                            if health_status['status'] == 'healthy':
                                health_status['status'] = 'warning'
                except Exception as e:
                    health_status['warnings'].append(f"DM 상태 확인 실패: {str(e)}")
            
        except Exception as e:
            health_status['errors'].append(f"상태 확인 중 오류: {str(e)}")
            health_status['status'] = 'error'
        
        return health_status
    
    @api_retry(max_retries=3, delay_seconds=60)
    def _send_status_with_retry(self, status: str, in_reply_to_id: str = None, visibility: str = 'public'):
        """
        재시도 로직이 적용된 status_post 메서드
        
        Args:
            status: 게시할 내용
            in_reply_to_id: 답글 대상 ID
            visibility: 공개 범위
            
        Returns:
            마스토돈 status 객체
        """
        return self.api.status_post(
            status=status,
            in_reply_to_id=in_reply_to_id,
            visibility=visibility
        )


class StreamManager:
    """
    스트림 매니저 - 스트리밍 연결 관리 (통계 기능 제거, DM 처리 포함)
    """
    
    def __init__(self, api: mastodon.Mastodon, sheets_manager: SheetsManager):
        """
        StreamManager 초기화
        
        Args:
            api: 마스토돈 API 객체
            sheets_manager: Google Sheets 관리자
        """
        self.api = api
        self.sheets_manager = sheets_manager
        self.handler = None
        self.is_running = False
        self.dm_process_interval = 30  # 30초마다 DM 처리
        self.last_dm_process = 0
        
        logger.info("StreamManager 초기화 완료 (통계 기능 제거됨)")
    
    def start_streaming(self, max_retries: int = None, use_polling_fallback: bool = True) -> bool:
        """
        스트리밍 시작 (DM 처리 포함)
        
        Args:
            max_retries: 최대 재시도 횟수
            
        Returns:
            bool: 시작 성공 여부
        """
        if not IMPORTS_AVAILABLE:
            logger.error("필수 의존성이 없어 스트리밍을 시작할 수 없습니다")
            return False
        
        max_retries = max_retries or getattr(config, 'MAX_RETRIES', 10)
        
        # 핸들러 생성
        self.handler = BotStreamHandler(self.api, self.sheets_manager)
        
        attempt = 0
        while attempt < max_retries:
            try:
                logger.info(f"마스토돈 스트리밍 시작 시도 {attempt + 1}/{max_retries}")
                
                # 스트리밍 시작 (DM 처리 루프 포함)
                self.is_running = True
                self._start_streaming_with_dm_processing()
                
                # 정상 종료된 경우
                self.is_running = False
                logger.info("마스토돈 스트리밍 정상 종료")
                return True
                
            except Exception as e:
                attempt += 1
                self.is_running = False
                
                # 상세한 오류 정보 로깅
                error_details = {
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'attempt': attempt,
                    'max_retries': max_retries
                }
                
                # HTTP 응답 정보 포함
                if hasattr(e, 'response'):
                    error_details['http_status'] = getattr(e.response, 'status_code', 'N/A')
                    error_details['http_content'] = str(getattr(e.response, 'content', 'N/A'))[:200]
                
                logger.error(f"스트리밍 연결 실패 상세 정보: {error_details}")
                
                # 서버 오류 (502, 503) 시 재시도
                if (('503' in str(e) or 'Bad Gateway' in str(e) or '502' in str(e) or 
                     'MastodonNetworkError' in str(type(e))) and attempt < max_retries):
                    wait_time = min(getattr(config, 'BASE_WAIT_TIME', 5) * (attempt + 1), 30)
                    logger.warning(f"서버/네트워크 오류 감지, {wait_time}초 후 재시도 ({attempt}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    if attempt >= max_retries:
                        logger.error("❌ 최대 재시도 횟수 초과 - 스트리밍 시작 실패")
                        break
                    else:
                        # 다른 종류의 오류도 잠시 대기 후 재시도
                        wait_time = getattr(config, 'BASE_WAIT_TIME', 5)
                        logger.warning(f"일반 연결 오류, {wait_time}초 후 재시도")
                        time.sleep(wait_time)
        
        # 스트리밍 연결이 모두 실패했을 때 폴링 백업 시도
        if use_polling_fallback:
            logger.warning("⚠️ 스트리밍 연결 실패 - HTTP 폴링 방식으로 전환 시도")
            return self._start_polling_fallback()
        
        return False
    
    def _start_streaming_with_dm_processing(self):
        """DM 처리가 포함된 스트리밍 시작"""
        import threading
        
        # DM 처리를 위한 별도 스레드 시작
        dm_thread = threading.Thread(target=self._dm_processing_loop, daemon=True)
        dm_thread.start()
        logger.info("DM 처리 스레드 시작")
        
        try:
            # 메인 스트리밍 시작 (연결 파라미터 최적화)
            logger.debug("스트리밍 연결 파라미터 설정 중...")
            self.api.stream_user(
                listener=self.handler,
                timeout=60,  # 타임아웃 설정 (초)
                reconnect_async=True,  # 자동 재연결 활성화
                reconnect_async_wait_sec=10,  # 재연결 대기 시간
                run_async=False  # 동기 실행
            )
        finally:
            # 스트리밍 종료 시 DM 처리도 정리
            self.is_running = False
            logger.info("DM 처리 스레드 종료 요청")
    
    def _dm_processing_loop(self):
        """DM 처리 루프 (별도 스레드에서 실행)"""
        while self.is_running:
            try:
                current_time = time.time()
                
                # 일정 간격마다 DM 처리
                if current_time - self.last_dm_process >= self.dm_process_interval:
                    if self.handler:
                        results = self.handler.process_pending_dms()
                        if results['processed'] > 0:
                            logger.info(f"DM 처리 완료: {results}")
                    
                    self.last_dm_process = current_time
                
                # 1초 대기
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"DM 처리 루프 오류: {e}")
                time.sleep(5)  # 오류 시 잠시 대기
    
    def _start_polling_fallback(self) -> bool:
        """
        HTTP 폴링 방식 백업 시스템
        스트리밍이 실패할 때 대안으로 사용
        """
        logger.info("🔄 HTTP 폴링 방식으로 알림 확인 시작")
        
        try:
            import threading
            import time
            
            # 폴링을 위한 변수들
            self.is_running = True
            self.last_notification_id = None
            self.polling_interval = getattr(config, 'POLLING_INTERVAL', 30)  # 30초마다 확인
            
            # DM 처리 스레드 시작
            dm_thread = threading.Thread(target=self._dm_processing_loop, daemon=True)
            dm_thread.start()
            logger.info("DM 처리 스레드 시작 (폴링 모드)")
            
            # 폴링 루프 시작
            self._polling_loop()
            
            return True
            
        except Exception as e:
            logger.error(f"폴링 백업 시작 실패: {e}")
            self.is_running = False
            return False
    
    def _polling_loop(self):
        """폴링 기반 알림 확인 루프"""
        logger.info(f"📡 폴링 루프 시작 (간격: {self.polling_interval}초)")
        
        while self.is_running:
            try:
                # 새로운 알림 확인
                self._check_new_notifications()
                
                # 대기
                for _ in range(self.polling_interval):
                    if not self.is_running:
                        break
                    time.sleep(1)
                    
            except KeyboardInterrupt:
                logger.info("폴링 중단 요청")
                break
            except Exception as e:
                logger.error(f"폴링 루프 오류: {e}")
                time.sleep(10)  # 오류 시 잠시 대기
        
        logger.info("📡 폴링 루프 종료")
    
    def _check_new_notifications(self):
        """새로운 알림 확인 및 처리"""
        try:
            # 최신 알림 가져오기 (API 호출)
            notifications = self.api.notifications(
                limit=20,  # 최대 20개
                since_id=self.last_notification_id
            )
            
            if not notifications:
                logger.debug("새로운 알림 없음")
                return
            
            logger.info(f"📬 새로운 알림 {len(notifications)}개 발견")
            
            # 가장 최신 알림 ID 업데이트
            if notifications:
                self.last_notification_id = notifications[0].id
            
            # 각 알림 처리 (최신순이므로 역순으로)
            for notification in reversed(notifications):
                try:
                    # 멘션만 처리
                    if notification.type == 'mention':
                        logger.debug(f"멘션 알림 처리: @{notification.account.acct}")
                        self.handler.on_notification(notification)
                    else:
                        logger.debug(f"스킵된 알림 타입: {notification.type}")
                        
                except Exception as e:
                    logger.error(f"알림 처리 오류 (ID: {notification.id}): {e}")
                    
        except Exception as e:
            logger.error(f"알림 확인 실패: {e}")
            # API 오류 시 간격을 늘림
            time.sleep(5)
    
    def get_dm_stats(self) -> dict:
        """DM 전송 통계만 반환"""
        if self.handler and self.handler.dm_sender:
            return self.handler.dm_sender.get_stats()
        return {}
    
    def process_pending_dms_manually(self) -> dict:
        """수동으로 대기 중인 DM 처리"""
        if self.handler:
            return self.handler.process_pending_dms()
        return {'processed': 0, 'success': 0, 'failed': 0, 'retries': 0}
    
    def get_status(self) -> dict:
        """매니저 상태 반환 (통계 제거, DM 상태 포함)"""
        status = {
            'is_running': self.is_running,
            'handler_initialized': self.handler is not None,
            'api_connected': self.api is not None,
            'sheets_connected': self.sheets_manager is not None,
            'imports_available': IMPORTS_AVAILABLE,
            'dm_sender_initialized': False,
            'pending_dms': 0
        }
        
        if self.handler and self.handler.dm_sender:
            status['dm_sender_initialized'] = True
            try:
                status['pending_dms'] = self.handler.dm_sender.get_pending_count()
            except:
                status['pending_dms'] = 0
        
        return status
    
    def get_health_status(self) -> dict:
        """핸들러 상태 확인"""
        if self.handler:
            return self.handler.health_check()
        
        return {
            'status': 'error',
            'errors': ['핸들러가 초기화되지 않았습니다'],
            'warnings': []
        }
    
    def stop_streaming(self) -> None:
        """스트리밍 중지"""
        self.is_running = False
        logger.info("스트리밍 중지 요청")
    
    @api_retry(max_retries=3, delay_seconds=60)
    def _get_notifications_with_retry(self, limit: int = 20, since_id: str = None):
        """
        재시도 로직이 적용된 notifications 메서드
        
        Args:
            limit: 최대 알림 개수
            since_id: 마지막 확인한 알림 ID
            
        Returns:
            알림 리스트
        """
        return self.api.notifications(
            limit=limit,
            since_id=since_id
        )


def initialize_stream_with_dm(api: mastodon.Mastodon, sheets_manager: SheetsManager) -> StreamManager:
    """
    DM 지원이 포함된 스트림 매니저 초기화
    
    Args:
        api: 마스토돈 API 객체
        sheets_manager: Google Sheets 관리자
        
    Returns:
        StreamManager: 초기화된 스트림 매니저
    """
    if not IMPORTS_AVAILABLE:
        logger.error("필수 의존성이 없어 스트림 매니저를 초기화할 수 없습니다")
        return None
    
    # DM 전송기 전역 초기화
    try:
        from utils.dm_sender import initialize_dm_sender
        initialize_dm_sender(api)
    except Exception as e:
        logger.warning(f"DM 전송기 초기화 실패: {e}")
    
    # 스트림 매니저 생성
    manager = StreamManager(api, sheets_manager)
    logger.info("DM 지원 스트림 매니저 초기화 완료 (멘션 응답, 과제 컨텍스트 지원)")
    
    return manager


# 편의 함수들
def create_stream_handler(api: mastodon.Mastodon, sheets_manager: SheetsManager) -> Optional[BotStreamHandler]:
    """스트림 핸들러 생성 (멘션 응답, 과제 컨텍스트 지원)"""
    if not IMPORTS_AVAILABLE:
        logger.error("필수 의존성이 없어 스트림 핸들러를 생성할 수 없습니다")
        return None
    
    return BotStreamHandler(api, sheets_manager)


def create_stream_manager(api: mastodon.Mastodon, sheets_manager: SheetsManager) -> Optional[StreamManager]:
    """스트림 매니저 생성 (멘션 응답, 과제 컨텍스트 지원)"""
    if not IMPORTS_AVAILABLE:
        logger.error("필수 의존성이 없어 스트림 매니저를 생성할 수 없습니다")
        return None
    
    return StreamManager(api, sheets_manager)


def validate_stream_dependencies() -> Tuple[bool, list]:
    """
    스트리밍 의존성 검증
    
    Returns:
        Tuple[bool, list]: (유효성, 오류 목록)
    """
    errors = []
    
    # 라이브러리 확인
    try:
        import mastodon
    except ImportError:
        errors.append("mastodon.py 라이브러리가 설치되지 않았습니다")
    
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        errors.append("beautifulsoup4 라이브러리가 설치되지 않았습니다")
    
    # 환경 변수 확인 (config 모듈이 있는 경우만)
    if IMPORTS_AVAILABLE:
        try:
            required_env = ['MASTODON_ACCESS_TOKEN']
            for env_var in required_env:
                if not hasattr(config, env_var) or not getattr(config, env_var, None):
                    errors.append(f"환경 변수 {env_var}가 설정되지 않았습니다")
        except Exception as e:
            errors.append(f"환경 변수 검증 실패: {e}")
    
    return len(errors) == 0, errors


# 개발자를 위한 유틸리티
def show_stream_info() -> None:
    """
    스트림 핸들러 기본 정보 출력 (개발용)
    """
    try:
        print("=== Stream Handler 정보 ===")
        print(f"의존성 상태: {'✅ 정상' if IMPORTS_AVAILABLE else '❌ 실패'}")
        
        # 의존성 검증
        is_valid, errors = validate_stream_dependencies()
        print(f"의존성 검증: {'✅ 통과' if is_valid else '❌ 실패'}")
        
        if errors:
            print("오류:")
            for error in errors[:3]:  # 최대 3개만
                print(f"  - {error}")
            if len(errors) > 3:
                print(f"  ... 외 {len(errors) - 3}개")
        
        # 주요 기능
        print("\n주요 기능:")
        print("  ✅ ModernCommandRouter 연동")
        print("  ✅ HTML 처리 통합 (HTMLCleaner)")
        print("  ✅ 멘션 길이 초과 방지 (MentionManager)")
        print("  ✅ DM 전송 지원")
        print("  ✅ 과제 컨텍스트 지원")
        print("  ❌ 통계 기능 (제거됨)")
        
        print("\n=== 정보 출력 완료 ===")
        
    except Exception as e:
        print(f"스트림 정보 출력 실패: {e}")


# 마이그레이션 가이드
def get_stream_migration_guide() -> str:
    """
    스트림 핸들러 마이그레이션 가이드 반환
    
    Returns:
        str: 마이그레이션 가이드 텍스트
    """
    return """
    === Stream Handler 마이그레이션 가이드 ===
    
    주요 변경사항:
    1. CommandRouter → ModernCommandRouter 교체
    2. 통계 기능 완전 제거 (get_statistics, reset_statistics 등)
    3. HTML 처리 통합 (HTMLCleaner 클래스)
    4. 멘션 길이 초과 방지 (MentionManager 클래스)
    5. 의존성 임포트 실패 시 안전한 폴백 처리
    
    기존 사용법:
    handler = BotStreamHandler(api, sheets_manager)
    stats = handler.get_statistics()  # ❌ 더 이상 지원되지 않음
    
    새로운 사용법:
    handler = BotStreamHandler(api, sheets_manager)
    health = handler.health_check()  # ✅ 상태 확인만 지원
    
    제거된 기능:
    - get_statistics() 메서드
    - reset_statistics() 메서드  
    - 모든 내부 통계 수집 로직
    - get_handler_statistics() (StreamManager에서)
    
    새로운 기능:
    - HTMLCleaner: 통합된 HTML 처리
    - MentionManager: 멘션 길이 관리
    - 개선된 에러 처리 및 폴백
    - ModernCommandRouter 연동
    
    === 마이그레이션 완료 ===
    """
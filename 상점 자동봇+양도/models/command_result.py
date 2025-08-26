"""
명령어 결과 데이터 모델 - 개선된 버전
명령어 실행 결과를 관리하는 데이터 클래스들을 정의합니다.
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timedelta
from enum import Enum
import pytz

try:
    from models.dynamic_command_types import DynamicCommandType as CommandType
except ImportError:
    # 폴백: 기존 enum (임시)
    class CommandType(Enum):
        DICE = "dice"
        HELP = "help"
        UNKNOWN = "unknown"

# 경로 설정 (VM 환경 대응)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    from config.settings import config
    from utils.error_handling import CommandError
    from utils.message_chunking import MessageChunker
    IMPORTS_AVAILABLE = True
except ImportError:
    # VM 환경에서 임포트 실패 시 폴백
    IMPORTS_AVAILABLE = False
    
    # 기본 예외 클래스
    class CommandError(Exception):
        pass
    
    # 기본 설정
    class Config:
        SYSTEM_KEYWORDS = []
    
    config = Config()


class CommandStatus(Enum):
    """명령어 실행 상태"""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    ERROR = "error"


class MessageChunker:
    """텍스트 분할 유틸리티 (명시적 분리)"""
    
    @staticmethod
    def split_text_into_chunks(text: str, max_length: int = 400) -> List[str]:
        """
        텍스트를 청크로 분할
        
        Args:
            text: 분할할 텍스트
            max_length: 최대 길이
            
        Returns:
            List[str]: 분할된 청크들
        """
        if not text:
            return []
        
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        current_chunk = ""
        lines = text.split('\n')
        
        for line in lines:
            # 한 줄이 너무 긴 경우
            if len(line) > max_length:
                # 현재 청크가 있으면 먼저 저장
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                
                # 긴 줄을 강제로 분할
                while len(line) > max_length:
                    chunks.append(line[:max_length])
                    line = line[max_length:]
                
                if line:
                    current_chunk = line
            else:
                # 현재 청크에 추가했을 때 길이 초과하는지 확인
                test_chunk = current_chunk + ('\n' if current_chunk else '') + line
                if len(test_chunk) > max_length:
                    # 현재 청크 저장하고 새로 시작
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = line
                else:
                    current_chunk = test_chunk
        
        # 마지막 청크 저장
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return [chunk for chunk in chunks if chunk]


# 명령어 결과 데이터 클래스들

@dataclass(frozen=True)
class DiceResult:
    """다이스 굴리기 결과 (불변 객체)"""
    
    expression: str                          # 다이스 표현식 (예: "2d6", "1d20+5")
    rolls: tuple                            # 각 주사위 결과 (불변 tuple)
    total: int                              # 총합
    modifier: int = 0                       # 보정값
    threshold: Optional[int] = None         # 성공/실패 임계값
    threshold_type: Optional[str] = None    # 임계값 타입 ('<' 또는 '>')
    success_count: Optional[int] = None     # 성공한 주사위 개수
    fail_count: Optional[int] = None        # 실패한 주사위 개수
    
    def __post_init__(self):
        # rolls를 tuple로 변환 (불변성 보장)
        if not isinstance(self.rolls, tuple):
            object.__setattr__(self, 'rolls', tuple(self.rolls))
    
    @property
    def base_total(self) -> int:
        """보정값 제외한 주사위 합계"""
        return sum(self.rolls)
    
    @property
    def has_threshold(self) -> bool:
        """성공/실패 조건 여부"""
        return self.threshold is not None and self.threshold_type is not None
    
    @property
    def is_success(self) -> Optional[bool]:
        """성공 여부 (단일 주사위 + 임계값인 경우)"""
        if not self.has_threshold or len(self.rolls) != 1:
            return None
        
        roll_value = self.rolls[0]
        if self.threshold_type == '<':
            return roll_value <= self.threshold
        elif self.threshold_type == '>':
            return roll_value >= self.threshold
        return None
    
    def get_detailed_result(self) -> str:
        """상세한 결과 문자열 반환"""
        if len(self.rolls) == 1:
            # 단일 주사위
            if self.has_threshold:
                success = self.is_success
                if success is not None:
                    result_text = "성공" if success else "실패"
                    return f"{self.rolls[0]} ({result_text})"
            return str(self.total)
        else:
            # 복수 주사위
            rolls_str = ", ".join(str(roll) for roll in self.rolls)
            if self.has_threshold:
                return f"{rolls_str}\n성공: {self.success_count}개, 실패: {self.fail_count}개"
            else:
                return f"{rolls_str}\n합계: {self.total}"
    
    def get_simple_result(self) -> str:
        """간단한 결과 문자열 반환"""
        if len(self.rolls) == 1:
            return str(self.rolls[0])
        return f"합계: {self.total}"
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'expression': self.expression,
            'rolls': list(self.rolls),
            'total': self.total,
            'modifier': self.modifier,
            'threshold': self.threshold,
            'threshold_type': self.threshold_type,
            'success_count': self.success_count,
            'fail_count': self.fail_count,
            'base_total': self.base_total,
            'has_threshold': self.has_threshold,
            'is_success': self.is_success
        }


@dataclass(frozen=True)
class CardResult:
    """카드 뽑기 결과 (불변 객체)"""
    
    cards: tuple                            # 뽑힌 카드들 (불변 tuple)
    count: int                              # 요청한 카드 개수
    
    def __post_init__(self):
        # cards를 tuple로 변환 (불변성 보장)
        if not isinstance(self.cards, tuple):
            object.__setattr__(self, 'cards', tuple(self.cards))
    
    def get_result_text(self) -> str:
        """결과 텍스트 반환"""
        return ", ".join(self.cards)
    
    def get_suits_summary(self) -> Dict[str, int]:
        """무늬별 개수 요약"""
        suits = {'♠': 0, '♥': 0, '♦': 0, '♣': 0}
        for card in self.cards:
            if card and len(card) > 0:
                suit = card[0]
                if suit in suits:
                    suits[suit] += 1
        return suits
    
    def get_ranks_summary(self) -> Dict[str, int]:
        """숫자별 개수 요약"""
        ranks = {}
        for card in self.cards:
            if card and len(card) > 1:
                rank = card[1:]
                ranks[rank] = ranks.get(rank, 0) + 1
        return ranks
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'cards': list(self.cards),
            'count': self.count,
            'suits_summary': self.get_suits_summary(),
            'ranks_summary': self.get_ranks_summary()
        }


@dataclass(frozen=True)
class FortuneResult:
    """운세 결과 (불변 객체)"""
    
    fortune_text: str                       # 운세 문구
    user_name: str                          # 사용자 이름
    
    def get_result_text(self) -> str:
        """결과 텍스트 반환"""
        return f"{self.user_name}의 오늘의 운세:\n{self.fortune_text}"
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'fortune_text': self.fortune_text,
            'user_name': self.user_name
        }


@dataclass(frozen=True)
class CustomResult:
    """커스텀 명령어 결과 (불변 객체)"""
    
    command: str                            # 명령어
    original_phrase: str                    # 원본 문구
    processed_phrase: str                   # 처리된 문구 (다이스 치환 후)
    dice_results: tuple = field(default_factory=tuple)  # 포함된 다이스 결과들 (불변)
    
    def __post_init__(self):
        # dice_results를 tuple로 변환 (불변성 보장)
        if not isinstance(self.dice_results, tuple):
            object.__setattr__(self, 'dice_results', tuple(self.dice_results))
    
    def get_result_text(self) -> str:
        """결과 텍스트 반환"""
        return self.processed_phrase
    
    def has_dice(self) -> bool:
        """다이스가 포함되어 있는지 확인"""
        return len(self.dice_results) > 0
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'command': self.command,
            'original_phrase': self.original_phrase,
            'processed_phrase': self.processed_phrase,
            'dice_results': [dice.to_dict() for dice in self.dice_results],
            'has_dice': self.has_dice()
        }


@dataclass(frozen=True)
class HelpResult:
    """도움말 결과 (불변 객체)"""
    
    help_text: str                          # 도움말 텍스트
    command_count: int                      # 총 명령어 개수
    
    def get_result_text(self) -> str:
        """결과 텍스트 반환"""
        return self.help_text
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'help_text': self.help_text,
            'command_count': self.command_count
        }



@dataclass
class CommandResultGroup:
    """명령어 결과 그룹 (multiple 결과 전용 클래스)"""
    
    results: List['CommandResult'] = field(default_factory=list)
    group_title: str = ""
    
    def add_result(self, result: 'CommandResult') -> None:
        """결과 추가"""
        self.results.append(result)
    
    def get_combined_text(self) -> str:
        """모든 결과를 결합한 텍스트 반환"""
        if not self.results:
            return ""
        
        combined_texts = []
        if self.group_title:
            combined_texts.append(self.group_title)
        
        for i, result in enumerate(self.results, 1):
            if len(self.results) > 1:
                combined_texts.append(f"{i}. {result.get_user_message()}")
            else:
                combined_texts.append(result.get_user_message())
        
        return "\n".join(combined_texts)
    
    @property
    def is_all_successful(self) -> bool:
        """모든 결과가 성공인지 확인"""
        return all(result.is_successful() for result in self.results)
    
    @property
    def has_any_error(self) -> bool:
        """하나라도 오류가 있는지 확인"""
        return any(result.has_error() for result in self.results)
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'group_title': self.group_title,
            'results_count': len(self.results),
            'results': [result.to_dict() for result in self.results],
            'is_all_successful': self.is_all_successful,
            'has_any_error': self.has_any_error
        }


@dataclass(frozen=True)
class CommandResult:
    """명령어 실행 결과 통합 클래스 (개선된 불변 객체)"""
    
    command_type: CommandType               # 명령어 타입
    status: CommandStatus                   # 실행 상태
    user_id: str                           # 실행한 사용자 ID
    user_name: str                         # 사용자 이름
    original_command: str                  # 원본 명령어
    message: str                           # 결과 메시지
    result_data: Optional[Union[DiceResult, CardResult, FortuneResult, CustomResult, HelpResult,]] = None
    error: Optional[Exception] = None      # 오류 (있는 경우)
    execution_time: Optional[float] = None # 실행 시간 (초)
    timestamp: datetime = field(default_factory=lambda: datetime.now(pytz.timezone('Asia/Seoul')))
    metadata: Dict[str, Any] = field(default_factory=dict)  # 추가 메타데이터
    
    # 기본 오류 메시지 상수
    DEFAULT_ERROR_MESSAGE = "명령어 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
    
    def __post_init__(self):
        # 에러인데 메시지가 없는 경우 기본 메시지 설정
        if self.status == CommandStatus.ERROR and not self.message:
            object.__setattr__(self, 'message', self.DEFAULT_ERROR_MESSAGE)
        
        # metadata를 딕셔너리로 변환 (불변성 보장을 위해)
        if not isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', dict(self.metadata))
    
    @classmethod
    def success(cls, command_type: CommandType, user_id: str, user_name: str, 
                original_command: str, message: str, result_data: Any = None,
                execution_time: float = None, **metadata) -> 'CommandResult':
        """
        성공 결과 생성 (팩토리 메서드)
        
        Args:
            command_type: 명령어 타입
            user_id: 사용자 ID
            user_name: 사용자 이름
            original_command: 원본 명령어
            message: 결과 메시지
            result_data: 결과 데이터
            execution_time: 실행 시간
            **metadata: 추가 메타데이터
            
        Returns:
            CommandResult: 성공 결과 객체
        """
        return cls(
            command_type=command_type,
            status=CommandStatus.SUCCESS,
            user_id=user_id,
            user_name=user_name,
            original_command=original_command,
            message=message,
            result_data=result_data,
            execution_time=execution_time,
            metadata=metadata
        )
    
    @classmethod
    def failure(cls, command_type: CommandType, user_id: str, user_name: str,
                original_command: str, error: Exception, execution_time: float = None,
                **metadata) -> 'CommandResult':
        """
        실패 결과 생성 (팩토리 메서드)
        
        Args:
            command_type: 명령어 타입
            user_id: 사용자 ID
            user_name: 사용자 이름
            original_command: 원본 명령어
            error: 발생한 오류
            execution_time: 실행 시간
            **metadata: 추가 메타데이터
            
        Returns:
            CommandResult: 실패 결과 객체
        """
        return cls(
            command_type=command_type,
            status=CommandStatus.FAILED,
            user_id=user_id,
            user_name=user_name,
            original_command=original_command,
            message=str(error) or cls.DEFAULT_ERROR_MESSAGE,
            error=error,
            execution_time=execution_time,
            metadata=metadata
        )
    
    @classmethod
    def error(cls, command_type: CommandType, user_id: str, user_name: str,
              original_command: str, error: Exception, execution_time: float = None,
              **metadata) -> 'CommandResult':
        """
        오류 결과 생성 (팩토리 메서드)
        
        Args:
            command_type: 명령어 타입
            user_id: 사용자 ID
            user_name: 사용자 이름
            original_command: 원본 명령어
            error: 발생한 오류
            execution_time: 실행 시간
            **metadata: 추가 메타데이터
            
        Returns:
            CommandResult: 오류 결과 객체
        """
        error_message = str(error) if error else cls.DEFAULT_ERROR_MESSAGE
        
        return cls(
            command_type=command_type,
            status=CommandStatus.ERROR,
            user_id=user_id,
            user_name=user_name,
            original_command=original_command,
            message=error_message,
            error=error,
            execution_time=execution_time,
            metadata=metadata
        )
    
    @classmethod
    def long_text(cls, command_type: CommandType, user_id: str, user_name: str,
                  original_command: str, text: str, max_length: int = 400,
                  execution_time: float = None, **metadata) -> 'CommandResultGroup':
        """
        긴 텍스트 결과 생성 (그룹으로 반환)
        
        Args:
            command_type: 명령어 타입
            user_id: 사용자 ID
            user_name: 사용자 이름
            original_command: 원본 명령어
            text: 긴 텍스트
            max_length: 최대 길이
            execution_time: 실행 시간
            **metadata: 추가 메타데이터
            
        Returns:
            CommandResultGroup: 결과 그룹 (여러 CommandResult 포함)
        """
        # 텍스트 분할
        if IMPORTS_AVAILABLE:
            try:
                from utils.message_chunking import MessageChunker
                chunks = MessageChunker.split_text_into_chunks(text, max_length)
            except ImportError:
                chunks = MessageChunker.split_text_into_chunks(text, max_length)
        else:
            chunks = MessageChunker.split_text_into_chunks(text, max_length)
        
        # 각 청크를 개별 CommandResult로 생성
        group = CommandResultGroup(group_title=f"{user_name}의 {original_command} 결과")
        
        for i, chunk in enumerate(chunks):
            chunk_result = cls.success(
                command_type=command_type,
                user_id=user_id,
                user_name=user_name,
                original_command=f"{original_command} ({i+1}/{len(chunks)})",
                message=chunk,
                execution_time=execution_time if i == 0 else None,  # 첫 번째만 실행 시간 포함
                **metadata
            )
            group.add_result(chunk_result)
        
        return group
    
    def is_successful(self) -> bool:
        """성공 여부 확인"""
        return self.status == CommandStatus.SUCCESS
    
    def has_error(self) -> bool:
        """오류 여부 확인"""
        return self.error is not None
    
    def get_log_message(self) -> str:
        """로그용 메시지 반환"""
        status_text = "성공" if self.is_successful() else "실패"
        execution_info = f" ({self.execution_time:.3f}초)" if self.execution_time else ""
        return f"[{self.command_type.value}] {self.user_name} | {self.original_command} | {status_text}{execution_info}"
    
    def get_user_message(self) -> str:
        """사용자에게 표시할 메시지 반환"""
        return self.message
    
    def get_result_summary(self) -> Dict[str, Any]:
        """결과 요약 정보 반환"""
        summary = {
            'command_type': self.command_type.value,
            'status': self.status.value,
            'user_id': self.user_id,
            'user_name': self.user_name,
            'command': self.original_command,
            'success': self.is_successful(),
            'has_error': self.has_error(),
            'execution_time': self.execution_time,
            'timestamp': self.timestamp.isoformat()
        }
        
        if self.result_data:
            if hasattr(self.result_data, 'to_dict'):
                summary['result_data'] = self.result_data.to_dict()
            else:
                summary['result_data'] = str(self.result_data)
        
        if self.error:
            summary['error_type'] = type(self.error).__name__
            summary['error_message'] = str(self.error)
        
        summary.update(self.metadata)
        
        return summary
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환 (직렬화용)"""
        data = {
            'command_type': self.command_type.value,
            'status': self.status.value,
            'user_id': self.user_id,
            'user_name': self.user_name,
            'original_command': self.original_command,
            'message': self.message,
            'execution_time': self.execution_time,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata.copy()  # 복사본 반환
        }
        
        if self.result_data and hasattr(self.result_data, 'to_dict'):
            data['result_data'] = self.result_data.to_dict()
        
        if self.error:
            data['error'] = {
                'type': type(self.error).__name__,
                'message': str(self.error)
            }
        
        return data
    
    def add_metadata(self, key: str, value: Any) -> 'CommandResult':
        """
        메타데이터 추가 (불변 객체이므로 새 객체 반환)
        
        Args:
            key: 메타데이터 키
            value: 메타데이터 값
            
        Returns:
            CommandResult: 메타데이터가 추가된 새 객체
        """
        new_metadata = self.metadata.copy()
        new_metadata[key] = value
        
        return CommandResult(
            command_type=self.command_type,
            status=self.status,
            user_id=self.user_id,
            user_name=self.user_name,
            original_command=self.original_command,
            message=self.message,
            result_data=self.result_data,
            error=self.error,
            execution_time=self.execution_time,
            timestamp=self.timestamp,
            metadata=new_metadata
        )
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """메타데이터 조회"""
        return self.metadata.get(key, default)
    
    def __str__(self) -> str:
        """문자열 표현 (사용자 메시지)"""
        return self.message
    
    def __repr__(self) -> str:
        """개발자용 문자열 표현 (디버깅용)"""
        return (f"CommandResult(type={self.command_type.value}, "
                f"status={self.status.value}, user={self.user_name!r}, "
                f"command={self.original_command!r}, success={self.is_successful()})")


@dataclass
class CommandStats:
    """명령어 실행 통계 (통계 기능 유지)"""
    
    total_commands: int = 0
    successful_commands: int = 0
    failed_commands: int = 0
    error_commands: int = 0
    command_type_counts: Dict[str, int] = field(default_factory=dict)
    user_command_counts: Dict[str, int] = field(default_factory=dict)
    average_execution_time: float = 0.0
    total_execution_time: float = 0.0
    
    @classmethod
    def from_results(cls, results: List[CommandResult]) -> 'CommandStats':
        """
        명령어 결과 리스트에서 통계 생성
        
        Args:
            results: 명령어 결과 리스트
            
        Returns:
            CommandStats: 통계 객체
        """
        if not results:
            return cls()
        
        stats = cls()
        execution_times = []
        
        for result in results:
            stats.total_commands += 1
            
            # 상태별 카운트
            if result.status == CommandStatus.SUCCESS:
                stats.successful_commands += 1
            elif result.status == CommandStatus.FAILED:
                stats.failed_commands += 1
            elif result.status == CommandStatus.ERROR:
                stats.error_commands += 1
            
            # 명령어 타입별 카운트
            cmd_type = result.command_type.value
            stats.command_type_counts[cmd_type] = stats.command_type_counts.get(cmd_type, 0) + 1
            
            # 사용자별 카운트
            stats.user_command_counts[result.user_name] = stats.user_command_counts.get(result.user_name, 0) + 1
            
            # 실행 시간 수집
            if result.execution_time:
                execution_times.append(result.execution_time)
                stats.total_execution_time += result.execution_time
        
        # 평균 실행 시간 계산
        if execution_times:
            stats.average_execution_time = sum(execution_times) / len(execution_times)
        
        return stats
    
    @property
    def success_rate(self) -> float:
        """성공률 (퍼센트)"""
        if self.total_commands == 0:
            return 0.0
        return (self.successful_commands / self.total_commands) * 100
    
    @property
    def error_rate(self) -> float:
        """오류율 (퍼센트)"""
        if self.total_commands == 0:
            return 0.0
        return (self.error_commands / self.total_commands) * 100
    
    def get_top_users(self, limit: int = 5) -> List[tuple]:
        """
        상위 사용자 목록 반환
        
        Args:
            limit: 반환할 사용자 수
            
        Returns:
            List[tuple]: (사용자명, 명령어수) 튜플 리스트
        """
        sorted_users = sorted(
            self.user_command_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_users[:limit]
    
    def get_top_commands(self, limit: int = 5) -> List[tuple]:
        """
        상위 명령어 타입 목록 반환
        
        Args:
            limit: 반환할 명령어 타입 수
            
        Returns:
            List[tuple]: (명령어타입, 사용횟수) 튜플 리스트
        """
        sorted_commands = sorted(
            self.command_type_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_commands[:limit]
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'total_commands': self.total_commands,
            'successful_commands': self.successful_commands,
            'failed_commands': self.failed_commands,
            'error_commands': self.error_commands,
            'success_rate': round(self.success_rate, 2),
            'error_rate': round(self.error_rate, 2),
            'command_type_counts': self.command_type_counts,
            'user_command_counts': self.user_command_counts,
            'average_execution_time': round(self.average_execution_time, 3),
            'total_execution_time': round(self.total_execution_time, 3),
            'top_users': self.get_top_users(),
            'top_commands': self.get_top_commands()
        }
    
    def get_summary_text(self) -> str:
        """
        통계 요약 텍스트 반환
        
        Returns:
            str: 통계 요약
        """
        lines = [
            f"📈 명령어 실행 통계",
            f"총 실행: {self.total_commands:,}회",
            f"성공: {self.successful_commands:,}회 ({self.success_rate:.1f}%)",
            f"실패: {self.failed_commands:,}회",
            f"오류: {self.error_commands:,}회 ({self.error_rate:.1f}%)"
        ]
        
        if self.average_execution_time > 0:
            lines.append(f"평균 실행시간: {self.average_execution_time:.3f}초")
        
        top_commands = self.get_top_commands(3)
        if top_commands:
            lines.append(f"인기 명령어: {', '.join([f'{cmd}({cnt})' for cmd, cnt in top_commands])}")
        
        top_users = self.get_top_users(3)
        if top_users:
            lines.append(f"활성 사용자: {', '.join([f'{user}({cnt})' for user, cnt in top_users])}")
        
        return "\n".join(lines)


# 결과 생성 헬퍼 함수들 (개선된 버전)

def create_dice_result(expression: str, rolls: List[int], modifier: int = 0,
                      threshold: int = None, threshold_type: str = None) -> DiceResult:
    """다이스 결과 생성 헬퍼"""
    total = sum(rolls) + modifier
    success_count = None
    fail_count = None
    
    if threshold is not None and threshold_type:
        if threshold_type == '<':
            success_count = sum(1 for roll in rolls if roll <= threshold)
        elif threshold_type == '>':
            success_count = sum(1 for roll in rolls if roll >= threshold)
        
        if success_count is not None:
            fail_count = len(rolls) - success_count
    
    return DiceResult(
        expression=expression,
        rolls=tuple(rolls),  # tuple로 생성
        total=total,
        modifier=modifier,
        threshold=threshold,
        threshold_type=threshold_type,
        success_count=success_count,
        fail_count=fail_count
    )


def create_card_result(cards: List[str]) -> CardResult:
    """카드 결과 생성 헬퍼"""
    return CardResult(cards=tuple(cards), count=len(cards))  # tuple로 생성


def create_fortune_result(fortune_text: str, user_name: str) -> FortuneResult:
    """운세 결과 생성 헬퍼"""
    return FortuneResult(fortune_text=fortune_text, user_name=user_name)


def create_custom_result(command: str, original_phrase: str, 
                        processed_phrase: str, dice_results: List[DiceResult] = None) -> CustomResult:
    """커스텀 결과 생성 헬퍼"""
    return CustomResult(
        command=command,
        original_phrase=original_phrase,
        processed_phrase=processed_phrase,
        dice_results=tuple(dice_results or [])  # tuple로 생성
    )


def create_help_result(help_text: str, command_count: int = 0) -> HelpResult:
    """도움말 결과 생성 헬퍼"""
    return HelpResult(help_text=help_text, command_count=command_count)



def determine_command_type(command: str) -> CommandType:
    """명령어 문자열에서 타입 결정"""
    command = command.lower().strip()
    
    # 키워드 매핑 테이블
    keyword_mappings = {
        ('다이스', 'd'): CommandType.DICE,
        ('도움말', 'help'): CommandType.HELP,
    }
    
    # 키워드 포함 여부 확인
    for keywords, cmd_type in keyword_mappings.items():
        if any(keyword in command for keyword in keywords):
            return cmd_type
    
    # 시스템 키워드 확인 (config가 있는 경우)
    if IMPORTS_AVAILABLE and hasattr(config, 'SYSTEM_KEYWORDS'):
        if command in config.SYSTEM_KEYWORDS:
            # config에서 매핑 정보를 가져오는 방식으로 개선 가능
            pass
    
    return CommandType.CUSTOM


# 결과 검증 함수들 (개선된 버전)
def validate_dice_result(result: DiceResult) -> bool:
    """다이스 결과 유효성 검사"""
    if not result.rolls or not result.expression:
        return False
    
    if result.total != sum(result.rolls) + result.modifier:
        return False
    
    if result.has_threshold:
        if result.threshold_type not in ['<', '>']:
            return False
        if result.success_count is None or result.fail_count is None:
            return False
        if result.success_count + result.fail_count != len(result.rolls):
            return False
    
    return True


def validate_command_result(result: CommandResult) -> bool:
    """명령어 결과 유효성 검사"""
    if not result.user_id or not result.original_command:
        return False
    
    if result.status not in CommandStatus:
        return False
    
    if result.command_type not in CommandType:
        return False
    
    if result.is_successful() and not result.message:
        return False
    
    return True


def validate_command_result_group(group: CommandResultGroup) -> bool:
    """명령어 결과 그룹 유효성 검사"""
    if not group.results:
        return False
    
    return all(validate_command_result(result) for result in group.results)


# 전역 통계 관리자 (CommandStats 기능만 유지, 통계 저장은 제거)
class GlobalCommandStats:
    """전역 명령어 통계 관리자 (경량화된 버전)"""
    
    def __init__(self):
        self._results: List[CommandResult] = []
        self._max_results = 1000  # 최대 저장할 결과 수
    
    def add_result(self, result: CommandResult) -> None:
        """결과 추가"""
        self._results.append(result)
        
        # 최대 개수 초과 시 오래된 결과 제거
        if len(self._results) > self._max_results:
            self._results = self._results[-self._max_results:]
    
    def get_stats(self, hours: int = 24) -> CommandStats:
        """
        최근 N시간 통계 반환
        
        Args:
            hours: 조회할 시간 범위
            
        Returns:
            CommandStats: 통계 객체
        """
        cutoff_time = datetime.now(pytz.timezone('Asia/Seoul')) - timedelta(hours=hours)
        recent_results = [
            result for result in self._results
            if result.timestamp >= cutoff_time
        ]
        return CommandStats.from_results(recent_results)
    
    def clear_old_results(self, days: int = 7) -> int:
        """
        오래된 결과 정리
        
        Args:
            days: 보관할 일수
            
        Returns:
            int: 정리된 결과 수
        """
        cutoff_time = datetime.now(pytz.timezone('Asia/Seoul')) - timedelta(days=days)
        old_count = len(self._results)
        self._results = [
            result for result in self._results
            if result.timestamp >= cutoff_time
        ]
        return old_count - len(self._results)
    
    def get_result_count(self) -> int:
        """저장된 결과 수 반환"""
        return len(self._results)


# 전역 통계 인스턴스
global_stats = GlobalCommandStats()


# 마이그레이션 가이드
def get_command_result_migration_guide() -> str:
    """
    CommandResult 마이그레이션 가이드 반환
    
    Returns:
        str: 마이그레이션 가이드 텍스트
    """
    return """
    === CommandResult 마이그레이션 가이드 ===
    
    주요 변경사항:
    1. @dataclass(frozen=True)로 불변 객체화
    2. CommandResultGroup 클래스 분리 (multiple 결과 전용)
    3. MessageChunker로 텍스트 분할 로직 명시화
    4. 기본 오류 메시지 자동 설정
    5. __repr__ 메서드 추가 (디버깅 편의)
    6. 모든 리스트 타입을 tuple로 변경 (불변성 보장)
    
    기존 사용법:
    result = CommandResult.multiple([result1, result2])  # ❌ 모호함
    
    새로운 사용법:
    group = CommandResult.long_text(...)  # ✅ 명확한 그룹 반환
    combined_text = group.get_combined_text()
    
    불변 객체 활용:
    result = CommandResult.success(...)
    new_result = result.add_metadata("key", "value")  # 새 객체 반환
    
    디버깅 개선:
    print(result)      # 사용자 메시지 출력
    print(repr(result)) # 개발자 정보 출력
    
    검증 기능:
    is_valid = validate_command_result(result)
    is_group_valid = validate_command_result_group(group)
    
    === 마이그레이션 완료 ===
    """